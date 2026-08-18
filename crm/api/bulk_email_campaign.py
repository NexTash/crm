import json

import frappe
from frappe import _
from frappe.utils import cint, get_datetime, now_datetime, validate_email_address

IMMEDIATE_RECIPIENT_LIMIT = 2000
ALLOWED_OPERATORS = {"=", "!=", "like", "not like", "in", "not in", ">", "<", ">=", "<=", "is", "between"}
DISALLOWED_TYPES = {"Section Break", "Column Break", "Tab Break", "HTML", "Button", "Table", "Table MultiSelect", "HTML Editor", "Text Editor", "Markdown Editor"}


def _field(meta, fieldname):
	return next((df for df in meta.fields if df.fieldname == fieldname), None)


def normalise_filters(doctype, filters):
	if not filters:
		return []
	if isinstance(filters, str):
		try:
			filters = json.loads(filters)
		except ValueError:
			frappe.throw(_("Filters must contain valid JSON."))
	if not isinstance(filters, list):
		frappe.throw(_("Filters must be a list."))
	meta = frappe.get_meta(doctype)
	result = []
	for item in filters:
		if not isinstance(item, (list, tuple)) or len(item) not in (3, 4):
			frappe.throw(_("Each filter must contain a field, operator, and value."))
		if len(item) == 4:
			filter_doctype, fieldname, operator, value = item
			if filter_doctype != doctype:
				frappe.throw(_("Invalid filter DocType."))
		else:
			fieldname, operator, value = item
		df = _field(meta, fieldname)
		if not df or df.fieldtype in DISALLOWED_TYPES:
			frappe.throw(_("Invalid filter field: {0}").format(fieldname))
		operator = (operator or "=").lower()
		if operator not in ALLOWED_OPERATORS:
			frappe.throw(_("Invalid filter operator: {0}").format(operator))
		if operator in {"in", "not in"} and isinstance(value, str):
			value = [v.strip() for v in value.split(",") if v.strip()]
		result.append([fieldname, operator, value])
	return result


def _email_fields(doctype):
	fields = []
	for df in frappe.get_meta(doctype).fields:
		if df.fieldtype not in {"Data", "Small Text", "Text", "Read Only"}:
			continue
		if (df.fieldtype == "Data" and df.options == "Email") or "email" in (df.fieldname or "").lower() or "email" in (df.label or "").lower():
			fields.append({"fieldname": df.fieldname, "label": df.label or df.fieldname})
	return fields


@frappe.whitelist()
def get_email_fields(reference_doctype):
	if not reference_doctype or not frappe.db.exists("DocType", reference_doctype):
		return []
	return _email_fields(reference_doctype)


def validate_campaign(doc):
	if not doc.reference_doctype or not frappe.db.exists("DocType", doc.reference_doctype):
		frappe.throw(_("Reference DocType does not exist."))
	df = _field(frappe.get_meta(doc.reference_doctype), doc.email_field)
	if not df or (df.fieldtype != "Data" and "email" not in (df.fieldname or "").lower() and "email" not in (df.label or "").lower()):
		frappe.throw(_("Email Field must be a suitable email field."))
	if cint(doc.daily_sending_limit) <= 0:
		frappe.throw(_("Daily Sending Limit must be greater than zero."))
	if not (doc.subject or "").strip():
		frappe.throw(_("Subject is required."))
	content = {"Rich Text": doc.rich_text_content, "HTML": doc.html_content, "Markdown": doc.markdown_content}.get(doc.content_type)
	if not (content or "").strip():
		frappe.throw(_("Content is required for the selected Content Type."))
	if not doc.sender_account or not frappe.db.exists("Email Account", {"name": doc.sender_account, "enable_outgoing": 1}):
		frappe.throw(_("Sender Account must be an outgoing-enabled Email Account."))
	normalise_filters(doc.reference_doctype, doc.filters_json)


def _valid_email(value):
	value = str(value or "").strip()
	return bool(value) and bool(validate_email_address(value, throw=False))


def _rows(doc):
	return frappe.get_all(doc.reference_doctype, filters=normalise_filters(doc.reference_doctype, doc.filters_json), fields=["name", doc.email_field], order_by="name asc")


def campaign_email_queues(name):
	queues = frappe.get_all("Email Queue", filters={"reference_doctype": "Bulk Email Campaign", "reference_name": name}, fields=["name", "status", "modified"])
	if not queues:
		return []
	queue_names = [queue.name for queue in queues]
	recipients = frappe.get_all("Email Queue Recipient", filters={"parent": ["in", queue_names]}, fields=["parent", "recipient"])
	recipients_by_queue = {recipient.parent: recipient.recipient for recipient in recipients}
	for queue in queues:
		queue.recipient = recipients_by_queue.get(queue.name)
	return queues


def enqueue_campaign(campaign, immediate=False):
	return frappe.enqueue(
		"crm.tasks.bulk_email.process_campaign",
		campaign=campaign,
		queue="long",
		now=immediate,
		enqueue_after_commit=not immediate,
	)


@frappe.whitelist()
def preview_recipients(name):
	doc = frappe.get_doc("Bulk Email Campaign", name)
	validate_campaign(doc)
	seen, valid, invalid, duplicates = set(), [], 0, 0
	rows = _rows(doc)
	for row in rows:
		email = str(row.get(doc.email_field) or "").strip()
		if not _valid_email(email):
			invalid += 1
		elif email in seen:
			duplicates += 1
		else:
			seen.add(email)
			valid.append({"email": email, "reference_name": row.name})
	return {"total": len(rows), "valid": len(valid), "invalid": invalid, "duplicates": duplicates, "sample": valid[:20]}


def update_statistics(name):
	queues = campaign_email_queues(name)
	counts = {status: sum(queue.status == status for queue in queues) for status in ("Not Sent", "Sending", "Sent", "Error")}
	today = get_datetime(now_datetime().date())
	sent_today = sum(queue.status == "Sent" and queue.modified >= today for queue in queues)
	frappe.db.set_value("Bulk Email Campaign", name, {"total_queued": counts["Not Sent"], "total_sent": counts["Sent"], "total_failed": counts["Error"], "total_remaining": counts["Not Sent"] + counts["Sending"], "sent_today": sent_today, "last_run_at": now_datetime()}, update_modified=False)


@frappe.whitelist()
def start_campaign(name):
	doc = frappe.get_doc("Bulk Email Campaign", name)
	validate_campaign(doc)
	if doc.status not in ("Draft", "Paused", "Failed"):
		frappe.throw(_("Campaign cannot be started from status {0}.").format(doc.status))
	if doc.status == "Draft":
		rows, seen = _rows(doc), set()
		valid = invalid = duplicates = 0
		for row in rows:
			email = str(row.get(doc.email_field) or "").strip()
			if not _valid_email(email):
				invalid += 1
			elif email in seen:
				duplicates += 1
			else:
				seen.add(email)
				valid += 1
		frappe.db.set_value("Bulk Email Campaign", name, {"total_matching_records": len(rows), "total_valid_recipients": valid, "total_invalid_emails": invalid, "total_duplicate_emails": duplicates})
	frappe.db.set_value("Bulk Email Campaign", name, "status", "Running")
	enqueue_campaign(name, immediate=valid <= IMMEDIATE_RECIPIENT_LIMIT)
	return {"status": "Running"}


@frappe.whitelist()
def set_campaign_status(name, status):
	doc = frappe.get_doc("Bulk Email Campaign", name)
	if status == "Paused" and doc.status == "Running":
		doc.db_set("status", "Paused")
	elif status == "Running" and doc.status in ("Paused", "Failed"):
		doc.db_set("status", "Running")
		enqueue_campaign(name)
	else:
		frappe.throw(_("Invalid campaign status transition."))
	return {"status": status}
