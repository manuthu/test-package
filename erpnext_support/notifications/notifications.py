# Copyright (c) 2019, Frappe Technologies Pvt. Ltd. and Contributors
# MIT License. See license.txt

from __future__ import unicode_literals
import frappe
from distutils.version import LooseVersion
from frappe.utils.change_log import get_versions

def get_notification_config():
	return {
		"for_doctype": {
			"ERPNext Support Issue": {"status": "Open"},
		},
	}

def notify_user(erpnext_support_issue):
	if frappe.db.exists("DocType", "Notification Log"):
		from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification

		erpnext_support_issue = frappe.get_doc("ERPNext Support Issue", erpnext_support_issue)
		notification_doc = {
			'type': 'Mention',
			'document_type': 'ERPNext Support Issue',
			'document_name': erpnext_support_issue.name,
			'subject': erpnext_support_issue.subject,
			'from_user': 'Administrator',
			'email_content': 'You have a new reply for support issue {0}'.format(erpnext_support_issue.name)
		}

		enqueue_create_notification(erpnext_support_issue.raised_by, notification_doc)