import frappe
from frappe.utils import cint, now_datetime, today

from crm.api.bulk_email_campaign import IMMEDIATE_RECIPIENT_LIMIT, _rows, _valid_email, campaign_email_queues, update_statistics

BATCH_SIZE = IMMEDIATE_RECIPIENT_LIMIT


def _render(doc, source):
	return frappe.render_template(source or "", {"doc": doc})


def _is_complete(doc, queues):
	if any(queue.status in ("Not Sent", "Sending") for queue in queues):
		return False

	queued_emails = {
		str(queue.recipient).strip()
		for queue in queues
		if queue.recipient
	}
	return not any(
		_valid_email(row.get(doc.email_field))
		and str(row.get(doc.email_field)).strip().lower() not in queued_emails
		for row in _rows(doc)
	)


def process_campaign(campaign):
	doc = frappe.get_doc("Bulk Email Campaign", campaign)
	if doc.status != "Running":
		return
	limit = cint(doc.daily_sending_limit)
	queues = campaign_email_queues(campaign)
	sent_today = sum(queue.status == "Sent" and str(queue.modified.date()) == today() for queue in queues)
	reserved = sum(queue.status in ("Not Sent", "Sending") for queue in queues)
	capacity = max(0, limit - sent_today - reserved)
	if not capacity:
		update_statistics(campaign)
		if _is_complete(doc, queues):
			frappe.db.set_value("Bulk Email Campaign", campaign, {"status": "Completed", "completed_at": now_datetime()}, update_modified=False)
		return

	account = frappe.get_doc("Email Account", doc.sender_account)
	existing_emails = {str(queue.recipient).strip() for queue in queues if queue.recipient}
	rows = _rows(doc)
	seen_emails = set(existing_emails)
	processed = 0
	for row in rows:
		if processed >= min(BATCH_SIZE, capacity):
			break
		if frappe.db.get_value("Bulk Email Campaign", campaign, "status") != "Running":
			break
		email = str(row.get(doc.email_field) or "").strip()
		if not _valid_email(email) or email in seen_emails:
			continue
		try:
			reference = frappe.get_doc(doc.reference_doctype, row.name)
			subject = _render(reference, doc.subject)
			content = {"Rich Text": doc.rich_text_content, "HTML": doc.html_content, "Markdown": doc.markdown_content}[doc.content_type]
			queue_doc = frappe.sendmail(
				recipients=[email],
				sender=account.default_sender or account.email_id,
				subject=subject,
				content=_render(reference, content),
				as_markdown=doc.content_type == "Markdown",
				delayed=True,
				reference_doctype="Bulk Email Campaign",
				reference_name=campaign,
			)
			if queue_doc and queue_doc.name:
				seen_emails.add(email)
				processed += 1
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Bulk Email Campaign {campaign}")

	update_statistics(campaign)
	queues = campaign_email_queues(campaign)
	if _is_complete(doc, queues):
		frappe.db.set_value("Bulk Email Campaign", campaign, {"status": "Completed", "completed_at": now_datetime()}, update_modified=False)


def process_running_campaigns():
	for name in frappe.get_all("Bulk Email Campaign", filters={"status": "Running"}, pluck="name"):
		try:
			process_campaign(name)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Bulk Email Campaign scheduler: {name}")
