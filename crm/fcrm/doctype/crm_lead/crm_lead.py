# Copyright (c) 2023, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import json
import re

import frappe
from frappe import _
from frappe.desk.form.assign_to import _add as assign
from frappe.model.document import Document
from frappe.utils import nowdate, validate_email_address

from crm.fcrm.doctype.crm_service_level_agreement.utils import get_sla
from crm.fcrm.doctype.crm_status_change_log.crm_status_change_log import (
	add_status_change_log,
)
from crm.fcrm.doctype.utils import add_or_remove_lost_reason_section_in_sidepanel


class CRMLead(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from crm.fcrm.doctype.crm_products.crm_products import CRMProducts
		from crm.fcrm.doctype.crm_rolling_response_time.crm_rolling_response_time import (
			CRMRollingResponseTime,
		)
		from crm.fcrm.doctype.crm_status_change_log.crm_status_change_log import CRMStatusChangeLog

		annual_revenue: DF.Currency
		communication_status: DF.Link | None
		converted: DF.Check
		email: DF.Data | None
		facebook_form_id: DF.Data | None
		facebook_lead_id: DF.Data | None
		first_name: DF.Data
		first_responded_on: DF.Datetime | None
		first_response_time: DF.Duration | None
		gender: DF.Link | None
		image: DF.AttachImage | None
		industry: DF.Link | None
		job_title: DF.Data | None
		last_name: DF.Data | None
		last_responded_on: DF.Datetime | None
		last_response_time: DF.Duration | None
		lead_name: DF.Data | None
		lead_owner: DF.Link | None
		lost_notes: DF.Text | None
		lost_reason: DF.Link | None
		middle_name: DF.Data | None
		mobile_no: DF.Data | None
		naming_series: DF.Literal["CRM-LEAD-.YYYY.-"]
		net_total: DF.Currency
		no_of_employees: DF.Literal["1-10", "11-50", "51-200", "201-500", "501-1000", "1000+"]
		organization: DF.Data | None
		phone: DF.Data | None
		products: DF.Table[CRMProducts]
		response_by: DF.Datetime | None
		rolling_responses: DF.Table[CRMRollingResponseTime]
		salutation: DF.Link | None
		sla: DF.Link | None
		sla_creation: DF.Datetime | None
		sla_status: DF.Literal["", "First Response Due", "Rolling Response Due", "Failed", "Fulfilled"]
		source: DF.Link | None
		status: DF.Link
		status_change_log: DF.Table[CRMStatusChangeLog]
		territory: DF.Link | None
		total: DF.Currency
		website: DF.Data | None
	# end: auto-generated types

	def before_validate(self):
		self.set_sla()

	def validate(self):
		self.validate_status()
		self.set_full_name()
		self.set_lead_name()
		self.set_title()
		self.validate_email()
		self.validate_lost_reason()
		if not self.is_new() and self.has_value_changed("lead_owner") and self.lead_owner:
			self.share_with_agent(self.lead_owner)
			self.assign_agent(self.lead_owner)
		if self.has_value_changed("status"):
			add_status_change_log(self)

	def after_insert(self):
		if self.lead_owner:
			if self.lead_owner != frappe.session.user:
				self.share_with_agent(self.lead_owner)
			self.assign_agent(self.lead_owner)

	def before_save(self):
		self.apply_sla()

	def validate_status(self):
		if self.is_new() and not self.status:
			if frappe.db.exists("CRM Lead Status", "New"):
				self.status = "New"
			else:
				self.status = frappe.get_all("CRM Lead Status", {"type": "Open"}, pluck="name")[0]

	def set_full_name(self):
		if self.first_name:
			self.lead_name = " ".join(
				name
				for name in [
					self.salutation,
					self.first_name,
					self.middle_name,
					self.last_name,
				]
				if name
			)

	def set_lead_name(self):
		if not self.lead_name:
			# Check for leads being created through data import
			if not self.organization and not self.email and not self.flags.ignore_mandatory:
				frappe.throw(_("A Lead requires either a person's name or an organization's name"))
			elif self.organization:
				self.lead_name = self.organization
			elif self.email:
				self.lead_name = self.email.split("@")[0]
			else:
				self.lead_name = "Unnamed Lead"

	def set_title(self):
		self.title = self.organization or self.lead_name

	def validate_email(self):
		if self.email:
			if not self.flags.ignore_email_validation:
				validate_email_address(self.email, throw=True)

			if self.email == self.lead_owner:
				frappe.throw(_("Lead Owner cannot be same as the Lead Email Address"))

	def validate_lost_reason(self):
		"""
		Validate the lost reason if the status is set to "Lost".
		"""
		if self.status and frappe.get_cached_value("CRM Lead Status", self.status, "type") == "Lost":
			if not self.lost_reason:
				frappe.throw(_("Please specify a reason for losing the lead."), frappe.ValidationError)
			elif self.lost_reason == "Other" and not self.lost_notes:
				frappe.throw(_("Please specify the reason for losing the lead."), frappe.ValidationError)
		if self.has_value_changed("status"):
			add_or_remove_lost_reason_section_in_sidepanel(self)

	def assign_agent(self, agent):
		if not agent:
			return

		assignees = self.get_assigned_users()
		if assignees:
			for assignee in assignees:
				if agent == assignee:
					# the agent is already set as an assignee
					return

		assign({"assign_to": [agent], "doctype": "CRM Lead", "name": self.name}, ignore_permissions=True)

	def share_with_agent(self, agent):
		if not agent:
			return

		docshares = frappe.get_all(
			"DocShare",
			filters={"share_name": self.name, "share_doctype": self.doctype},
			fields=["name", "user"],
		)

		shared_with = [d.user for d in docshares] + [agent]

		for user in shared_with:
			if user == agent and not frappe.db.exists(
				"DocShare",
				{"user": agent, "share_name": self.name, "share_doctype": self.doctype},
			):
				frappe.share.add_docshare(
					self.doctype,
					self.name,
					agent,
					write=1,
					flags={"ignore_share_permission": True},
				)
			elif user != agent:
				frappe.share.remove(
					self.doctype,
					self.name,
					user,
					flags={"ignore_share_permission": True, "ignore_permissions": True},
				)

	def create_contact(self, existing_contact=None, throw=True):
		if not self.lead_name:
			self.set_full_name()
			self.set_lead_name()

		existing_contact = existing_contact or self.contact_exists(throw)
		if existing_contact:
			self.update_lead_contact(existing_contact)
			return existing_contact

		contact = frappe.new_doc("Contact")
		contact.update(
			{
				"first_name": self.first_name or self.lead_name,
				"last_name": self.last_name,
				"salutation": self.salutation,
				"gender": self.gender,
				"designation": self.job_title,
				"company_name": self.organization,
				"image": self.image or "",
			}
		)

		if self.email:
			contact.append("email_ids", {"email_id": self.email, "is_primary": 1})

		if self.phone:
			contact.append("phone_nos", {"phone": self.phone, "is_primary_phone": 1})

		if self.mobile_no:
			contact.append("phone_nos", {"phone": self.mobile_no, "is_primary_mobile_no": 1})

		contact.insert(ignore_permissions=True)
		contact.reload()  # load changes by hooks on contact

		return contact.name

	def create_organization(self, existing_organization=None):
		if not self.organization and not existing_organization:
			return

		existing_organization = existing_organization or frappe.db.exists(
			"CRM Organization", {"organization_name": self.organization}
		)
		if existing_organization:
			self.db_set("organization", existing_organization)
			return existing_organization

		organization = frappe.new_doc("CRM Organization")
		organization.update(
			{
				"organization_name": self.organization,
				"website": self.website,
				"territory": self.territory,
				"industry": self.industry,
				"annual_revenue": self.annual_revenue,
			}
		)
		organization.insert(ignore_permissions=True)
		return organization.name

	def update_lead_contact(self, contact):
		contact = frappe.get_cached_doc("Contact", contact)
		frappe.db.set_value(
			"CRM Lead",
			self.name,
			{
				"salutation": contact.salutation,
				"first_name": contact.first_name,
				"last_name": contact.last_name,
				"email": contact.email_id,
				"mobile_no": contact.mobile_no,
			},
		)

	def contact_exists(self, throw=True):
		# Match only on email which uniquely identifies a person
		if not self.email:
			return False

		email_exist = frappe.db.exists("Contact Email", {"email_id": self.email})
		if not email_exist:
			return False

		contact = frappe.db.get_value("Contact Email", email_exist, "parent")

		if throw:
			frappe.throw(
				_("Contact already exists with Email: {0}").format(self.email),
				title=_("Contact Already Exists"),
			)

		return contact

	def create_deal(self, contact, organization, deal=None):
		new_deal = frappe.new_doc("CRM Deal")

		lead_deal_map = {
			"lead_owner": "deal_owner",
		}

		restricted_fieldtypes = [
			"Tab Break",
			"Section Break",
			"Column Break",
			"HTML",
			"Button",
			"Attach",
		]
		restricted_map_fields = [
			"name",
			"naming_series",
			"creation",
			"owner",
			"modified",
			"modified_by",
			"idx",
			"docstatus",
			"status",
			"email",
			"mobile_no",
			"phone",
			"sla",
			"sla_status",
			"response_by",
			"first_response_time",
			"first_responded_on",
			"communication_status",
			"sla_creation",
			"status_change_log",
		]

		for field in self.meta.fields:
			if field.fieldtype in restricted_fieldtypes:
				continue
			if field.fieldname in restricted_map_fields:
				continue

			fieldname = field.fieldname
			if field.fieldname in lead_deal_map:
				fieldname = lead_deal_map[field.fieldname]

			if hasattr(new_deal, fieldname):
				if fieldname == "organization":
					new_deal.update({fieldname: organization})
				else:
					new_deal.update({fieldname: self.get(field.fieldname)})

		new_deal.update(
			{
				"lead": self.name,
				"contacts": [{"contact": contact}],
			}
		)

		if self.first_responded_on:
			new_deal.update(
				{
					"sla_creation": self.sla_creation,
					"response_by": self.response_by,
					"sla_status": self.sla_status,
					"communication_status": self.communication_status,
					"first_response_time": self.first_response_time,
					"first_responded_on": self.first_responded_on,
				}
			)

		if deal:
			new_deal.update(deal)

		new_deal.insert(ignore_permissions=True)

		for user in self.get_assigned_users():
			if user and user != new_deal.deal_owner:
				new_deal.assign_agent(user)

		return new_deal.name

	def set_sla(self):
		"""
		Find an SLA to apply to the lead.
		"""
		if self.sla:
			return

		sla = get_sla(self)
		if not sla:
			self.first_responded_on = None
			self.first_response_time = None
			return
		self.sla = sla.name

	def apply_sla(self):
		"""
		Apply SLA if set.
		"""
		if not self.sla:
			return
		sla = frappe.get_last_doc("CRM Service Level Agreement", {"name": self.sla})
		if sla:
			sla.apply(self)

	def convert_to_deal(self, deal=None):
		return convert_to_deal(lead=self.name, doc=self, deal=deal)

	@staticmethod
	def get_non_filterable_fields():
		return ["converted"]

	@staticmethod
	def default_list_data():
		columns = [
			{
				"label": "Name",
				"type": "Data",
				"key": "lead_name",
				"width": "12rem",
			},
			{
				"label": "Organization",
				"type": "Link",
				"key": "organization",
				"options": "CRM Organization",
				"width": "10rem",
			},
			{
				"label": "Status",
				"type": "Link",
				"options": "CRM Lead Status",
				"key": "status",
				"width": "8rem",
			},
			{
				"label": "Email",
				"type": "Data",
				"key": "email",
				"width": "12rem",
			},
			{
				"label": "Mobile No.",
				"type": "Data",
				"key": "mobile_no",
				"width": "11rem",
			},
			{
				"label": "Assigned To",
				"type": "Text",
				"key": "_assign",
				"width": "10rem",
			},
			{
				"label": "Last Modified",
				"type": "Datetime",
				"key": "modified",
				"width": "8rem",
			},
		]
		rows = [
			"name",
			"lead_name",
			"organization",
			"status",
			"email",
			"mobile_no",
			"lead_owner",
			"first_name",
			"sla_status",
			"response_by",
			"first_response_time",
			"first_responded_on",
			"modified",
			"_assign",
			"image",
		]
		return {"columns": columns, "rows": rows}

	@staticmethod
	def default_kanban_settings():
		return {
			"column_field": "status",
			"title_field": "lead_name",
			"kanban_fields": '["organization", "email", "mobile_no", "_assign", "modified"]',
		}


@frappe.whitelist()
def convert_to_deal(
	lead: str,
	doc: Document | None = None,
	deal: str | dict | None = None,
	existing_contact: str | None = None,
	existing_organization: str | None = None,
):
	if not (doc and doc.flags.get("ignore_permissions")) and not frappe.has_permission(
		"CRM Lead", "write", lead
	):
		frappe.throw(_("Not allowed to convert Lead to Deal"), frappe.PermissionError)

	lead = frappe.get_cached_doc("CRM Lead", lead)
	if frappe.db.exists("CRM Lead Status", "Qualified"):
		lead.db_set("status", "Qualified")
	lead.db_set("converted", 1)
	if lead.sla and frappe.db.exists("CRM Communication Status", "Replied"):
		lead.db_set("communication_status", "Replied")
	contact = lead.create_contact(existing_contact, False)
	organization = lead.create_organization(existing_organization)
	_deal = lead.create_deal(contact, organization, deal)
	return _deal





# Code by ahmad

def _normalize_email(value: str | None) -> str:
	return (value or "").strip().lower()


def _normalize_phone(value: str | None) -> str:
	return re.sub(r"\D+", "", (value or "").strip())


def _set_student_applicant_link(lead: Document, applicant_name: str) -> None:
	if lead.get("custom_student_applicant") == applicant_name:
		return

	lead.db_set("custom_student_applicant", applicant_name, update_modified=False)
	lead.set("custom_student_applicant", applicant_name)


def _find_student_applicant_for_lead(lead: Document) -> str | None:
	if not frappe.db.exists("DocType", "Student Applicant"):
		return None

	linked_applicant = (lead.get("custom_student_applicant") or "").strip()
	if linked_applicant and frappe.db.exists("Student Applicant", linked_applicant):
		return linked_applicant

	email = lead.email

	if not email or not frappe.db.exists("Student Applicant", {"student_email_id": email}):
		return None

	candidates = frappe.db.get_all("Student Applicant", filters={"student_email_id": email})

	return candidates[0].get("name") if candidates else None


def _get_admission_campus(lead: Document) -> str:
	return "Lahore Campus"


def _get_lead_full_name(lead: Document) -> str:
	full_name = " ".join(
		part
		for part in [
			getattr(lead, "first_name", None),
			getattr(lead, "middle_name", None),
			getattr(lead, "last_name", None),
		]
		if part
	)
	return full_name or lead.get("lead_name") or lead.get("title") or lead.get("email")


def _get_registered_applicant_name(registration_result: dict) -> str | None:
	application = registration_result.get("application") or {}
	return (
		registration_result.get("active_application_name")
		or application.get("name")
		or registration_result.get("student_applicant")
	)


@frappe.whitelist()
def get_student_applicant_status(lead: str) -> dict:
	if not frappe.has_permission("CRM Lead", "read", lead):
		frappe.throw(_("Not allowed to access this lead"), frappe.PermissionError)

	lead_doc = frappe.get_cached_doc("CRM Lead", lead)
	applicant_name = _find_student_applicant_for_lead(lead_doc)

	if applicant_name:
		_set_student_applicant_link(lead_doc, applicant_name)

	return {
		"student_applicant": applicant_name,
		"exists": bool(applicant_name),
		"label": "View Application" if applicant_name else "Convert to Applicant",
	}


@frappe.whitelist()
def convert_to_applicant(lead: str) -> dict:
	lead_doc = frappe.get_cached_doc("CRM Lead", lead)
	selected_program = (getattr(lead_doc, "custom_system_programs", None) or "").strip()
	email = (getattr(lead_doc, "email", None) or "").strip()
	phone = (getattr(lead_doc, "mobile_no", None) or getattr(lead_doc, "phone", None) or "").strip()
	
	if not selected_program:
		frappe.throw(_("Please select the program"))
	if not email:
		frappe.throw(_("Please enter the email"))
	if not phone:
		frappe.throw(_("Please enter the phone"))

	existing_applicant = _find_student_applicant_for_lead(lead_doc)
	if existing_applicant:
		_set_student_applicant_link(lead_doc, existing_applicant)
		return {
			"student_applicant": existing_applicant,
			"created": False,
			"exists": True,
			"message": _("Already have registered"),
			"label": "View Application",
		}

	if frappe.db.exists("User", email):
		from admissions.api.admission import (
			_get_or_create_student_applicant,
			_normalize_program_level,
			_normalize_student_payload,
		)

		payload = _normalize_student_payload(
			{
				"full_name": _get_lead_full_name(lead_doc),
				"student_email_id": email,
				"student_mobile_number": phone,
				"program": selected_program,
				"program_level": _normalize_program_level("", selected_program),
				"campus": _get_admission_campus(lead_doc),
				"country": "Pakistan",
				"nationality": "Pakistan",
				"hu_wizard_step": 1,
				"hu_application_submitted": False,
				"qualifications": [],
			}
		)

		student_applicant, flag = _get_or_create_student_applicant(
			payload,
		)

		_set_student_applicant_link(
			lead_doc,
			student_applicant.name,
		)

		return {
			"student_applicant": student_applicant.name,
			"created": False,
			"exists": True,
			"message": _("Already have registered"),
			"label": "View Application",
		}
	from admissions.api.admission import register_admission_user_from_full_name

	registration_result = register_admission_user_from_full_name(
		full_name=_get_lead_full_name(lead_doc),
		email=email,
		password=frappe.generate_hash(length=12),
		mobile_number=phone,
		program=selected_program,
		campus=_get_admission_campus(lead_doc),
		crm_flag=True
	)

	applicant_name = _get_registered_applicant_name(registration_result)
	if not applicant_name:
		frappe.throw(_("Applicant was created but could not be linked. Please refresh and try again."))

	_set_student_applicant_link(lead_doc, applicant_name)

	return {
		"student_applicant": applicant_name,
		"created": True,
		"exists": True,
		"message": _("Applicant created successfully"),
		"label": "View Application",
	}
