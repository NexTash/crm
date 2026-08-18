import frappe
from frappe import _
from frappe.model.document import Document

from crm.api.bulk_email_campaign import enqueue_campaign, validate_campaign


class BulkEmailCampaign(Document):
	def validate(self):
		validate_campaign(self)
		if not self.status:
			self.status = "Draft"
		if self.is_new() and self.status != "Draft":
			frappe.throw(_("A new campaign must be Draft."))

	def on_update(self):
		if self.has_value_changed("status") and self.status == "Running":
			enqueue_campaign(self.name)
