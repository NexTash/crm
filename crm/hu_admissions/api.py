import frappe
from frappe import _


@frappe.whitelist()
def create_student_from_lead(lead_name: str) -> dict[str, str]:
	lead = frappe.get_doc("CRM Lead", lead_name)
	student = ensure_student_from_lead(lead)

	return {"name": student.name, "message": _("Student record created successfully.")}


def auto_create_student_on_approved(doc, _event=None) -> None:
	if doc.doctype != "CRM Lead":
		return

	if doc.status != "Approved":
		return

	if hasattr(doc, "hu_student") and doc.hu_student:
		return

	ensure_student_from_lead(doc)


def ensure_student_from_lead(lead):
	if isinstance(lead, str):
		lead = frappe.get_doc("CRM Lead", lead)

	if hasattr(lead, "hu_student") and lead.hu_student:
		return frappe.get_doc("HU Student", lead.hu_student)

	student = frappe.get_doc(
		{
			"doctype": "HU Student",
			"student_name": lead.lead_name or lead.first_name,
			"lead": lead.name,
			"source": lead.source,
			"email": lead.email,
			"mobile_no": lead.mobile_no or lead.phone,
			"admission_status": "Approved",
		}
	).insert(ignore_permissions=True)

	if frappe.get_meta("CRM Lead").has_field("hu_student"):
		lead.db_set("hu_student", student.name, update_modified=False)

	return student
