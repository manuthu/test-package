# -*- coding: utf-8 -*-
# Copyright (c) 2019, Frappe and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
import re
import json
import base64
import sys

from frappe.model.document import Document
from frappe import _
from frappe.utils import now_datetime
from erpnext_support.api.client import call_remote_method, change_support_issue_status
from six import string_types
from frappe.utils.file_manager import add_attachments, get_file
from erpnext_support.api.client import validate_limits

class ERPNextSupportIssue(Document):

	def validate(self):
		validate_limits()

		if self.is_new():
			return

		# Send a request to close Support Issue
		doc_before_save = self.get_doc_before_save()

		if self.status == "Closed" and not self.status == doc_before_save.status:
			change_support_issue_status(self.status, self.frappe_issue_id, self.name)

	def on_trash(self):
		frappe.throw(_("You are not allowed to delete a ERPNext Support Issue"),
			frappe.PermissionError)

@frappe.whitelist()
def create_erpnext_support_issue(subject, issue_type, issue_found_in, raised_by, description, attachments=None):

	erpnext_support_issue = frappe.get_doc({
		"doctype": "ERPNext Support Issue",
		"subject": subject,
		"issue_type": issue_type,
		"issue_found_in": issue_found_in,
		"raised_by": raised_by,
		"description": description,
	}).insert(ignore_permissions=True)

	comm = frappe.get_doc({
		"doctype": "Communication",
		"subject": subject,
		"content": description,
		"recipients": "support@erpnext.com",
		"sent_or_received": "Sent",
		"reference_doctype": "ERPNext Support Issue",
		"communication_medium": "Email",
		"sender": raised_by,
		"reference_name": erpnext_support_issue.name,
		"has_attachment": 1 if attachments else 0
	}).insert(ignore_permissions=True)

	if isinstance(attachments, string_types):
		attachments = json.loads(attachments)

	if attachments:
		add_attachments("Communication", comm.name, attachments)
		add_attachments("ERPNext Support Issue", erpnext_support_issue.name, attachments)

	frappe.db.commit()
	frappe.publish_realtime("erpnext_support_issue", erpnext_support_issue.name)

	file_attachments = []

	if attachments:
		for a in attachments:
			filename, content = get_file(a)
			if content and isinstance(content, string_types) \
				and sys.version_info[0] == '3':
				content = content.encode("utf-8")
			file_attachments.append({
				"filename": filename,
				"content": base64.b64encode(content).decode("ascii")
			})

	file_attachments = json.dumps(file_attachments)

	params = get_params(erpnext_support_issue, file_attachments)

	frappe_issue = call_remote_method("create_issue_from_customer", params)

	# If FrappeClient request fails, increment sync count
	if frappe_issue.get("failed"):
		erpnext_support_issue.db_set("sync_count", erpnext_support_issue.sync_count + 1)
		frappe.throw("Could not sync Issue with Frappe Technologies. Retrying in sometime.")

	set_corresponding_frappe_values(erpnext_support_issue, frappe_issue)
	frappe.publish_realtime("refresh_erpnext_support_issue")

	return erpnext_support_issue.name

def sync_erpnext_support_issue(doc=None, method=None):
	"""
		Sync Issue which arent synced with Server due to FrappeClient request failure
	"""
	filters = [
		["status", "=", "Open"],
		["frappe_issue_id", "=", ""],
		["sync_count", "<", 5]
	]

	for unsynced_issue in frappe.get_list("ERPNext Support Issue", filters=filters):
		erpnext_support_issue = frappe.get_doc("ERPNext Support Issue", unsynced_issue.name)

		comm = frappe.get_doc("Communication", {
			"reference_doctype": "ERPNext Support Issue",
			"reference_name": erpnext_support_issue.name
		})

		file_attachments = []

		if comm.has_attachment:
			files = frappe.get_list("File", filters={"attached_to_doctype": "Communication", "attached_to_name": comm.get("name")})

			for d in files:
				filename, content = get_file(d.name)

				if content and isinstance(content, string_types) and sys.version_info[0] == '3':
					content = content.encode("utf-8")
				file_attachments.append({
					"filename": filename,
					"content": base64.b64encode(content).decode("ascii")
				})

			file_attachments = json.dumps(file_attachments)

		params = get_params(erpnext_support_issue, file_attachments)

		frappe_issue = call_remote_method("create_issue_from_customer", params)

		# If FrappeClient request fails, increment sync count
		if frappe_issue.get("failed"):
			erpnext_support_issue.db_set("sync_count", erpnext_support_issue.sync_count + 1)
			continue

		set_corresponding_frappe_values(erpnext_support_issue, frappe_issue)

def get_params(erpnext_support_issue, file_attachments):
	return {
		"subject": erpnext_support_issue.subject,
		"raised_by": erpnext_support_issue.raised_by,
		"description": re.sub('src="', 'src="' + frappe.utils.get_url(), erpnext_support_issue.description),
		"client_issue_id": erpnext_support_issue.name,
		"recipients": "support@erpnext.com",
		"issue_found_in": erpnext_support_issue.issue_found_in,
		"issue_type": erpnext_support_issue.issue_type,
		"attachments": file_attachments
	}

def set_corresponding_frappe_values(erpnext_support_issue, frappe_issue):
	erpnext_support_issue.db_set("frappe_issue_id", frappe_issue.get("name"))
	erpnext_support_issue.db_set("priority", frappe_issue.get("priority"))
	erpnext_support_issue.db_set("release", frappe_issue.get("release"))

	if frappe_issue.get("resolution_by"):
		erpnext_support_issue.db_set("resolution_by", frappe.utils.get_datetime(frappe_issue.get("resolution_by")))

	if frappe_issue.get("last_sync_on"):
		erpnext_support_issue.db_set("last_sync_on", frappe.utils.get_datetime(frappe_issue.get("last_sync_on")))

@frappe.whitelist()
def count_support_issues():
	return frappe.db.count('ERPNext Support Issue', {'issue_type': ('!=', 'Error Report')})