import frappe
from frappe import _


@frappe.whitelist(allow_guest=True, methods=["POST"])
def capture_website_lead(
	name: str,
	phone: str,
	email: str,
) -> dict[str, str]:
	name = (name or "").strip()
	phone = (phone or "").strip()
	email = (email or "").strip()

	if not name or not phone or not email:
		frappe.throw(_("Name, phone, and email are required."))

	if not frappe.db.exists("CRM Lead Source", "Website"):
		frappe.get_doc({"doctype": "CRM Lead Source", "source_name": "Website"}).insert(
			ignore_permissions=True
		)

	lead_data = {
		"doctype": "CRM Lead",
		"first_name": name,
		"email": email,
		"mobile_no": phone,
		"phone": phone,
		"source": "Website",
		"status": "New Enquiry" if frappe.db.exists("CRM Lead Status", "New Enquiry") else "New",
	}

	lead = frappe.get_doc(lead_data).insert(ignore_permissions=True)

	return {
		"name": lead.name,
		"message": _("Thanks For Your Intrest in HU"),
	}
