from __future__ import unicode_literals

import frappe
import json
import re
import base64
import os

from six import string_types
from frappe.utils import add_days, today
from frappe.installer import update_site_config
from frappe.utils.file_manager import save_file, get_file

# Issue Status
@frappe.whitelist()
def change_status_server(associated_issue, status, erpnext_support_user, issue):
	authenticate_erpnext_support_user(erpnext_support_user)

	support_issue = frappe.get_doc("Issue", issue)
	support_issue.status = status
	support_issue.save(ignore_permissions=True)

@frappe.whitelist()
def sync_issue_status_server(erpnext_support_user, erpnext_support_issues, bench_site):
	"""
		returns a dict of support issue statuses
		{
			"erpnext_support_issue_name_1": [{status}]
			"erpnext_support_issue_name_2": [{status}]
		}
	"""
	authenticate_erpnext_support_user(erpnext_support_user)

	issues = {}
	erpnext_support_issues = json.loads(erpnext_support_issues)

	for erpnext_support_issue in erpnext_support_issues:
		filters = {
			'name': erpnext_support_issue.get('associated_issue'),
			'client_issue_id': erpnext_support_issue.get('name'),
			'bench_site': bench_site
		}

		issue_status = frappe.db.get_value("Issue", filters, "status")
		if issue_status not in ['Open', 'Closed']:
			issue_status = 'Open'

		issues[erpnext_support_issue.get('name')] = [{"status": issue_status}]

	issues = json.dumps(issues)
	return issues

# Make Issue
@frappe.whitelist()
def make_issue(associated_issue, erpnext_support_user, subject, description, issue_found_in, issue_type,
	raised_by, recipients, bench_site, attachments=None):
	authenticate_erpnext_support_user(erpnext_support_user)

	issue = frappe.get_doc({
		'doctype': 'Issue',
		'subject': subject,
		'raised_by': raised_by,
		'bench_site': bench_site,
		'client_issue_id': associated_issue,
		"module": issue_found_in,
		"issue_type": issue_type,
		"owner": raised_by,
		"raised_via_support_app": 1
	}).insert(ignore_permissions=True)

	make_communication_server(erpnext_support_user=erpnext_support_user, subject=subject, description=description, \
		raised_by=raised_by, recipients=recipients, bench_site=bench_site, issue=issue.name, attachments=attachments)

	return issue.name

# Make and Sync Communication
@frappe.whitelist()
def make_communication_server(erpnext_support_user, subject, description, raised_by, recipients, bench_site, issue, attachments=None):
	authenticate_erpnext_support_user(erpnext_support_user)

	comm = frappe.get_doc({
		"doctype":"Communication",
		"subject": subject,
		"content": description,
		"sent_or_received": "Received",
		"reference_doctype": 'Issue',
		"communication_medium": "Email",
		"sender": raised_by,
		"recipients": recipients,
		"reference_name": issue,
		"has_attachment": 1 if attachments else 0
	}).insert(ignore_permissions=True)

	if attachments:
		attachments = json.loads(attachments)

		for d in attachments:
			save_file(d.get('filename'), base64.b64decode(d.get('content')), "Communication", comm.name)

@frappe.whitelist()
def sync_communication_server(erpnext_support_user, erpnext_support_issues, bench_site):
	"""
		returns a dict of support issues and associated communications in the format
		{
			"erpnext_support_issue_name_1": [{Communications}]
			"erpnext_support_issue_name_2": [{Communications}]
		}
	"""
	authenticate_erpnext_support_user(erpnext_support_user)

	communications = {}
	erpnext_support_issues = json.loads(erpnext_support_issues)

	for erpnext_support_issue in erpnext_support_issues:
		if erpnext_support_issue.get('associated_issue'):
			filters = {
				'reference_doctype': 'Issue',
				'reference_name': erpnext_support_issue.get('associated_issue'),
				'communication_medium': 'Email',
				'sent_or_received': 'Sent',
				'seen': 0
			}
			fields = ["name", "subject", "content", "recipients", "has_attachment"]
			comms = frappe.get_all("Communication", filters=filters, fields=fields, order_by="creation ASC")

			for comm in comms:
				frappe.db.set_value("Communication", comm.name, "seen", 1)
				comm['content'] = re.sub('src="', 'src="' + frappe.utils.get_url(), comm.get('content'))

				file_attachments = []
				if comm.get('has_attachment'):
					files = frappe.get_list("File", filters={"attached_to_doctype": "Communication", "attached_to_name": comm.get('name')})

					for d in files:
						filename, content = get_file(d.name)
						if content and isinstance(content, string_types):
							content = content.encode("utf-8")
						file_attachments.append({
							"filename": filename,
							"content": base64.b64encode(content).decode("ascii")
						})

				file_attachments = json.dumps(file_attachments)
				comm.update({"attachments": file_attachments})

			communications[erpnext_support_issue.get('name')] = comms

	communications = json.dumps(communications)
	return communications

# Sync Rating
@frappe.whitelist()
def sync_feedback_rating_server(associated_issue, erpnext_support_user, support_rating, add_a_comment, bench_site):
	authenticate_erpnext_support_user(erpnext_support_user)

	frappe.db.set_value("Issue", associated_issue, "support_rating", support_rating)
	frappe.db.set_value("Issue", associated_issue, "add_a_comment", add_a_comment)

# Sync Expiry and No. of Users for Self Hosted with client
@frappe.whitelist()
def sync_expiry_and_users(erpnext_support_user, bench_site):
	authenticate_erpnext_support_user(erpnext_support_user)

	return json.dumps({
		"self_hosted_users": str(frappe.db.get_value("Customer", {"bench_site": bench_site}, "self_hosted_users")),
		"self_hosted_expiry": str(frappe.db.get_value("Customer", {"bench_site": bench_site}, "self_hosted_expiry"))
	})

# Creation and Authentication of Support User
def authenticate_erpnext_support_user(erpnext_support_user, bench_site=None):
	if 'Support Bot' in frappe.get_roles(erpnext_support_user):
		return True
	frappe.throw(frappe.AuthenticationError)

@frappe.whitelist(allow_guest=True)
def make_support_user(user, password):
	if frappe.conf.erpnext_support_user and frappe.conf.erpnext_support_password:
		return json.dumps({
			"user": frappe.conf.erpnext_support_user,
			"password": frappe.conf.erpnext_support_password
		})

	role = frappe.db.exists('Role', 'Support Bot')

	if not role:
		role = frappe.get_doc({
			"doctype": "Role",
			"role_name": "Support Bot",
		}).insert(ignore_permissions=True)
		role = role.name

	support_user = frappe.get_doc({
		"doctype":"User",
		"email": user,
		"first_name": "Support Bot",
		"send_welcome_email": 0,
		"new_password": password
	}).insert(ignore_permissions=True)

	support_user.add_roles(role)

	role = frappe.db.exists('Role', 'Support Team')
	if role:
		support_user.add_roles(role)

	role = frappe.db.exists('Role', 'System Manager')
	if role:
		support_user.add_roles(role)

	common_site_config_path = os.path.join(frappe.utils.get_bench_path(), 'sites', 'common_site_config.json')
	update_site_config('erpnext_support_user', user, site_config_path=common_site_config_path)
	update_site_config('erpnext_support_password', password, site_config_path=common_site_config_path)

	make_custom_field("Issue", "Bench Site", "bench_site", "Data", "Customer", 1, 0)
	make_custom_field("Issue", "Associated Issue", "associated_issue", "Data", "Customer", 1, 0)
	make_custom_field("Issue", "Raised via Support App", "raised_via_support_app", "Check", "Customer", 1, 0)
	make_custom_field("Issue", "Support Rating", "support_rating", "Int", "Customer", 1, 0)
	make_custom_field("Issue", "Comment", "add_a_comment", "Text", "Customer", 1, 0)
	make_custom_field("Customer", "Self Hosted Details", "self_hosted_details", "Section Break", "Customer POS id", 0, 1)
	make_custom_field("Customer", "Bench Site", "bench_site", "Data", "Self Hosted Details", 0, 0)
	make_custom_field("Customer", "Self Hosted Users", "self_hosted_users", "Int", "Bench Site", 0, 0)
	make_custom_field("Customer", "Self Hosted Expiry", "self_hosted_expiry", "Date", "Self Hosted Users", 0, 0)

	return json.dumps({
		"user": user,
		"password": password
	})

# Custom Fields
def make_custom_field(doctype, label, fieldname, fieldtype, insert_after, read_only=0, collapsible=0):
	if not frappe.db.exists('Custom Field', '{0}-{1}'.format(doctype, fieldname)):
		custom_field_issue_bench_site = frappe.get_doc({
			'doctype': 'Custom Field',
			'dt': doctype,
			'label': label,
			'fieldname': fieldname,
			'fieldtype': fieldtype,
			'insert_after': insert_after,
			'read_only': read_only,
			'collapsible': collapsible
		}).insert(ignore_permissions=True)
