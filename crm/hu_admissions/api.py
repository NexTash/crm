import frappe
from frappe import _


@frappe.whitelist()
def create_student_from_lead(lead_name: str) -> dict[str, str]:
	lead = frappe.get_doc("CRM Lead", lead_name)

	if hasattr(lead, "hu_student") and lead.hu_student:
		return {"name": lead.hu_student, "message": _("Student record already exists.")}

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

	update_values = {"status": "Approved"}
	if frappe.get_meta("CRM Lead").has_field("hu_student"):
		update_values["hu_student"] = student.name
	lead.update(update_values)
	lead.save(ignore_permissions=True)

	return {"name": student.name, "message": _("Student record created successfully.")}
