import json

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


LEAD_SOURCES = ["Website", "Referral", "Cold Call", "Email Campaign", "Social Media", "Walk In"]

LEAD_STATUSES = {
	"New Enquiry": {"color": "gray", "type": "Open", "position": 1},
	"Contacted": {"color": "orange", "type": "Ongoing", "position": 2},
	"Nurture": {"color": "blue", "type": "Ongoing", "position": 3},
	"Interested": {"color": "teal", "type": "Ongoing", "position": 4},
	"Qualified": {"color": "cyan", "type": "Ongoing", "position": 5},
	"Application Sent": {"color": "yellow", "type": "Ongoing", "position": 6},
	"Applied": {"color": "orange", "type": "Ongoing", "position": 7},
	"Enrolled": {"color": "green", "type": "Won", "position": 8},
	"Unqualified": {"color": "red", "type": "Lost", "position": 9},
	"Junk": {"color": "purple", "type": "Lost", "position": 10},
	"Not Interested": {"color": "red", "type": "Lost", "position": 11},
	"Application Submitted": {"color": "blue", "type": "Ongoing", "position": 12},
	"Admission Fee Pending": {"color": "amber", "type": "Ongoing", "position": 13},
	"Fee Submitted": {"color": "cyan", "type": "Ongoing", "position": 14},
	"Approved": {"color": "green", "type": "Won", "position": 15},
}

SOURCE_REMAP = {
	"Advertisement": "Social Media",
	"Facebook": "Social Media",
	"Instagram": "Social Media",
	"Google": "Social Media",
	"WhatsApp": "Social Media",
	"TikTok": "Social Media",
	"Campaign": "Email Campaign",
	"Mass Mailing": "Email Campaign",
	"Email Campaign": "Email Campaign",
	"Email": "Website",
	"Existing Customer": "Referral",
	"Customer's Vendor": "Referral",
	"Supplier Reference": "Referral",
	"Reference": "Referral",
	"Exhibition": "Walk In",
	"Walk-in": "Walk In",
	"Phone Enquiry": "Walk In",
	"Email Enquiry": "Walk In",
	"Cold Calling": "Cold Call",
}

STATUS_REMAP = {
	"New": "New Enquiry",
	"New Lead": "New Enquiry",
	"Lead Captured": "New Enquiry",
	"Converted": "Approved",
	"Student Created": "Approved",
}

KANBAN_FIELDS = ["lead_name", "mobile_no", "source", "lead_owner", "hu_student"]

OBSOLETE_LEAD_FIELDS = [
	"program_of_interest",
	"academic_intake",
	"qualification_type",
	"hu_admissions_section",
	"column_break_hu_academic",
	"matric_percentage",
	"fsc_percentage",
	"whatsapp_no",
	"parent_name",
	"parent_mobile",
	"lead_priority",
	"campaign_name",
	"ad_set_name",
	"utm_source",
	"utm_medium",
	"utm_campaign",
]


def execute() -> dict[str, list[str]]:
	mapped_sources = remap_lead_sources()
	mapped_statuses = remap_lead_statuses()
	created_sources = ensure_lead_sources()
	created_statuses = ensure_lead_statuses()
	cleanup_sources()
	cleanup_statuses()
	created_fields = ensure_custom_fields()
	removed_fields = cleanup_obsolete_custom_fields()
	created_views = ensure_views()
	created_layouts = ensure_layouts()
	frappe.clear_cache(doctype="CRM Lead")

	return {
		"mapped_sources": mapped_sources,
		"mapped_statuses": mapped_statuses,
		"created_sources": created_sources,
		"created_statuses": created_statuses,
		"created_fields": created_fields,
		"removed_fields": removed_fields,
		"created_views": created_views,
		"created_layouts": created_layouts,
	}


def remap_lead_sources() -> list[str]:
	updated = []
	for from_source, to_source in SOURCE_REMAP.items():
		if frappe.db.count("CRM Lead", {"source": from_source}):
			frappe.db.set_value("CRM Lead", {"source": from_source}, "source", to_source, update_modified=False)
			updated.append(f"{from_source}->{to_source}")
	return updated


def remap_lead_statuses() -> list[str]:
	updated = []
	for from_status, to_status in STATUS_REMAP.items():
		if frappe.db.count("CRM Lead", {"status": from_status}):
			frappe.db.set_value("CRM Lead", {"status": from_status}, "status", to_status, update_modified=False)
			updated.append(f"{from_status}->{to_status}")
	return updated


def ensure_lead_sources() -> list[str]:
	created = []
	for source_name in LEAD_SOURCES:
		if frappe.db.exists("CRM Lead Source", source_name):
			continue
		frappe.get_doc({"doctype": "CRM Lead Source", "source_name": source_name}).insert(
			ignore_permissions=True
		)
		created.append(source_name)
	return created


def ensure_lead_statuses() -> list[str]:
	created = []
	for status_name, status_data in LEAD_STATUSES.items():
		if frappe.db.exists("CRM Lead Status", status_name):
			doc = frappe.get_doc("CRM Lead Status", status_name)
			doc.color = status_data["color"]
			doc.type = status_data["type"]
			doc.position = status_data["position"]
			doc.save(ignore_permissions=True)
		else:
			frappe.get_doc(
				{
					"doctype": "CRM Lead Status",
					"lead_status": status_name,
					"color": status_data["color"],
					"type": status_data["type"],
					"position": status_data["position"],
				}
			).insert(ignore_permissions=True)
			created.append(status_name)
	return created


def cleanup_sources() -> None:
	for source in frappe.get_all("CRM Lead Source", pluck="name"):
		if source in LEAD_SOURCES:
			continue
		if frappe.db.exists("CRM Lead", {"source": source}):
			continue
		frappe.delete_doc("CRM Lead Source", source, ignore_permissions=True, force=True)


def cleanup_statuses() -> None:
	for status in frappe.get_all("CRM Lead Status", pluck="name"):
		if status in LEAD_STATUSES:
			continue
		if frappe.db.exists("CRM Lead", {"status": status}):
			continue
		frappe.delete_doc("CRM Lead Status", status, ignore_permissions=True, force=True)


def ensure_custom_fields() -> list[str]:
	lead_fields = [
		{
			"fieldname": "hu_student",
			"label": "HU Student",
			"fieldtype": "Link",
			"options": "HU Student",
			"insert_after": "source",
		},
	]
	create_custom_fields({"CRM Lead": lead_fields}, ignore_validate=True)
	return [field["fieldname"] for field in lead_fields]


def cleanup_obsolete_custom_fields() -> list[str]:
	removed = []
	for fieldname in OBSOLETE_LEAD_FIELDS:
		custom_field_name = f"CRM Lead-{fieldname}"
		if not frappe.db.exists("Custom Field", custom_field_name):
			continue
		frappe.delete_doc("Custom Field", custom_field_name, ignore_permissions=True, force=True)
		removed.append(fieldname)
	return removed


def ensure_views() -> list[str]:
	created = []
	kanban_columns = [{"name": status_name} for status_name in LEAD_STATUSES]

	view_name = frappe.db.exists(
		"CRM View Settings",
		{"dt": "CRM Lead", "label": "HU Admissions Funnel", "type": "kanban", "public": 1},
	)
	if view_name:
		doc = frappe.get_doc("CRM View Settings", view_name)
	else:
		doc = frappe.new_doc("CRM View Settings")
		doc.label = "HU Admissions Funnel"
		doc.dt = "CRM Lead"
		doc.type = "kanban"
		doc.route_name = "Leads"
		doc.public = 1
		doc.pinned = 1
		doc.user = ""
		created.append("HU Admissions Funnel")

	doc.column_field = "status"
	doc.title_field = "lead_name"
	doc.filters = "[]"
	doc.order_by = "modified desc"
	doc.kanban_columns = frappe.as_json(kanban_columns)
	doc.kanban_fields = frappe.as_json(KANBAN_FIELDS)
	doc.columns = "[]"
	doc.rows = "[]"
	doc.save(ignore_permissions=True)

	return created


def ensure_layouts() -> list[str]:
	lead_quick = [
		{
			"name": "lead_section",
			"columns": [
				{"name": "lead_column_1", "fields": ["first_name", "email"]},
				{"name": "lead_column_2", "fields": ["mobile_no", "source"]},
				{"name": "lead_column_3", "fields": ["status", "lead_owner"]},
			],
		},
	]
	lead_side = [
		{
			"label": "Admissions",
			"name": "admissions_section",
			"opened": True,
			"columns": [
				{"name": "admissions_column", "fields": ["status", "source", "lead_owner", "hu_student"]}
			],
		},
		{
			"label": "Contact",
			"name": "contact_section",
			"opened": True,
			"columns": [{"name": "contact_column", "fields": ["email", "mobile_no"]}],
		},
	]
	lead_data = [
		{
			"label": "Admissions",
			"name": "admissions_data_section",
			"opened": True,
			"columns": [
				{"name": "admissions_data_column_1", "fields": ["status", "source", "lead_owner"]},
				{"name": "admissions_data_column_2", "fields": ["hu_student"]},
			],
		},
		{
			"label": "Contact",
			"name": "contact_data_section",
			"opened": True,
			"columns": [
				{"name": "contact_data_column_1", "fields": ["first_name", "email"]},
				{"name": "contact_data_column_2", "fields": ["mobile_no"]},
			],
		},
	]
	deal_quick = [
		{
			"name": "deal_section",
			"columns": [
				{"name": "deal_column_1", "fields": ["organization", "lead"]},
				{"name": "deal_column_2", "fields": ["status", "source"]},
				{"name": "deal_column_3", "fields": ["deal_owner", "next_step"]},
			],
		},
	]
	deal_side = [
		{
			"label": "Admissions Deal",
			"name": "deal_side_section",
			"opened": True,
			"columns": [
				{
					"name": "deal_side_column",
					"fields": ["status", "lead", "source", "deal_owner", "organization", "next_step"],
				}
			],
		},
	]
	deal_data = [
		{
			"label": "Admissions Deal",
			"name": "deal_data_section",
			"opened": True,
			"columns": [
				{"name": "deal_data_column_1", "fields": ["organization", "lead"]},
				{"name": "deal_data_column_2", "fields": ["status", "source"]},
				{"name": "deal_data_column_3", "fields": ["deal_owner", "next_step"]},
			],
		},
	]

	upsert_fields_layout("CRM Lead", "Quick Entry", lead_quick)
	upsert_fields_layout("CRM Lead", "Side Panel", lead_side)
	upsert_fields_layout("CRM Lead", "Data Fields", lead_data)
	upsert_fields_layout("CRM Deal", "Quick Entry", deal_quick)
	upsert_fields_layout("CRM Deal", "Side Panel", deal_side)
	upsert_fields_layout("CRM Deal", "Data Fields", deal_data)
	return [
		"CRM Lead-Quick Entry",
		"CRM Lead-Side Panel",
		"CRM Lead-Data Fields",
		"CRM Deal-Quick Entry",
		"CRM Deal-Side Panel",
		"CRM Deal-Data Fields",
	]


def upsert_fields_layout(dt: str, type: str, layout: list[dict]) -> None:
	name = f"{dt}-{type}"
	if frappe.db.exists("CRM Fields Layout", name):
		doc = frappe.get_doc("CRM Fields Layout", name)
	else:
		doc = frappe.new_doc("CRM Fields Layout")
		doc.dt = dt
		doc.type = type

	doc.layout = json.dumps(layout)
	doc.save(ignore_permissions=True)
