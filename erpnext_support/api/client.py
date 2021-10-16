from __future__ import unicode_literals

import frappe
import json
import os
import base64

from frappe import _
from frappe.utils import now_datetime, getdate, get_datetime, get_datetime_str
from frappe.installer import update_site_config
from frappe.frappeclient import FrappeClient
from six import string_types
from frappe.utils.file_manager import add_attachments, save_url, save_file, get_file
from frappe.utils.user import get_enabled_system_users
from erpnext_support.api.client_utils import create_support_user, make_custom_field, validate_hash
from erpnext_support.notifications.notifications import notify_user
from frappe.utils.background_jobs import enqueue

@frappe.whitelist()
def sync(erpnext_support_issue=None):
	"""
		Syncs Support Issue with Server.
	"""
	fields = ["name", "frappe_issue_id", "status", "last_sync_on"]
	filters = [
		["status", "=", "Open"],
		["frappe_issue_id", "!=", ""],
		["last_sync_on", "!=", ""]
	]

	if erpnext_support_issue:
		filters.append(["name", "=", erpnext_support_issue])

	support_issues = frappe.get_all("ERPNext Support Issue", filters=filters, fields=fields)
	if not support_issues:
		return

	erpnext_support_issues = []

	# Batch issue sync requests to 10 per call
	for idx, issue in enumerate(support_issues):
		issue.last_sync_on = get_datetime_str(issue.last_sync_on)
		erpnext_support_issues.append(issue)

		if erpnext_support_issues and ((idx and idx%10 == 0) or idx == len(erpnext_support_issues)-1):
			params = {"erpnext_support_issues": json.dumps(erpnext_support_issues)}
			response = call_remote_method("serve_communications_and_statuses", params)
			if not response or (not isinstance(response, string_types) and response.get('failed')):
				continue

			update_erpnext_support_issue_status_and_communications(erpnext_support_issues, json.loads(response))
			erpnext_support_issues = []

def update_erpnext_support_issue_status_and_communications(erpnext_support_issues, response):
	"""
		Updates Communications and Status for Support Issue
	"""
	for erpnext_support_issue in erpnext_support_issues:
		communications = response.get(erpnext_support_issue.name).get("communications", [])
		status = response.get(erpnext_support_issue.name).get("status") or "Open"
		priority = response.get(erpnext_support_issue.name).get("priority")
		resolution_by = response.get(erpnext_support_issue.name).get("resolution_by")
		release = response.get(erpnext_support_issue.name).get("release")

		frappe.db.set_value("ERPNext Support Issue", erpnext_support_issue.name, "status", status)
		frappe.db.set_value("ERPNext Support Issue", erpnext_support_issue.name, "priority", priority)
		frappe.db.set_value("ERPNext Support Issue", erpnext_support_issue.name, "release", release)

		if resolution_by:
			frappe.db.set_value("ERPNext Support Issue", erpnext_support_issue.name, "resolution_by", get_datetime(resolution_by))

		for comm in communications:
			create_communications_for_sync(erpnext_support_issue=erpnext_support_issue.name, subject=comm.get("subject"), \
				description=comm.get("content"), raised_by="support@erpnext.com", recipients=comm.get("recipients"), \
				communication_id=comm.get("name"), attachments=comm.get("attachments"))

		if communications:
			frappe.db.set_value("ERPNext Support Issue", erpnext_support_issue.name, "last_sync_on", get_datetime(communications[-1].get('creation')))

		if communications:
			notify_user(erpnext_support_issue.name)

def create_communications_for_sync(erpnext_support_issue, subject, description, raised_by, recipients, communication_id, attachments=None):

	if frappe.db.exists("Communication", {
		"reference_doctype": "ERPNext Support Issue",
		"reference_name": erpnext_support_issue,
		"message_id": communication_id}):
		return

	comm = frappe.get_doc({
		"doctype": "Communication",
		"subject": subject,
		"content": description,
		"recipients": recipients,
		"sent_or_received": "Received",
		"reference_doctype": "ERPNext Support Issue",
		"communication_medium": "Email",
		"sender": raised_by,
		"reference_name": erpnext_support_issue,
		"message_id": communication_id,
		"has_attachment": 1 if attachments else 0
	}).insert(ignore_permissions=True)

	if attachments:
		attachments = json.loads(attachments)

		for d in attachments:
			save_file(d.get("filename"), d.get("content"), "Communication", comm.name, decode=True)

def change_support_issue_status(status, frappe_issue_id, client_issue_id):
	params = {
		"status": status,
		"frappe_issue_id": frappe_issue_id,
		"client_issue_id": client_issue_id
	}

	call_remote_method("change_issue_status", params)

def sync_split_issues():
	"""
		Sync Issue Split from Server
	"""
	response = call_remote_method("serve_split_issues", {})
	if not response:
		return

	split_issues = json.loads(response)
	erpnext_support_issue_mapping = {}

	for split_issue in split_issues:
		if not split_issues.get(split_issue):
			continue

		issue = split_issues.get(split_issue)
		comms = split_issues.get(split_issue).get("communications")

		erpnext_support_issue = frappe.get_doc({
			"doctype": "ERPNext Support Issue",
			"subject": issue.get("subject"),
			"frappe_issue_id": issue.get("frappe_issue_id"),
			"issue_type": issue.get("issue_type"),
			"issue_found_in": issue.get("module"),
			"raised_by": issue.get("raised_by"),
			"description": issue.get("description"),
			"last_sync_on": get_datetime(issue.get("last_sync_on")) if issue.get("last_sync_on") else None,
			"release": issue.get("release"),
			"resolution_by": get_datetime(issue.get("resolution_by")) if issue.get("resolution_by") else None,
			"priority": issue.get("priority")
		}).insert(ignore_permissions=True)

		erpnext_support_issue_mapping.update({split_issue: erpnext_support_issue.name})

		for comm in comms:
			create_communications_for_sync(erpnext_support_issue=erpnext_support_issue.name, subject=comm.get("subject"),
				description=comm.get("content"), raised_by=comm.get("raised_by"), recipients=comm.get("recipients"),
				communication_id=comm.get("communication_id"), attachments=comm.get("attachments", []))

	# Set Associated Issue in Frappe
	erpnext_support_issue_mapping = json.dumps(erpnext_support_issue_mapping)
	call_remote_method("set_corresponding_erpnext_support_issue", {"erpnext_support_issue_mapping": erpnext_support_issue_mapping})

@frappe.whitelist()
def reply_to_support_issue(client_issue_id, subject, description, raised_by, recipients, frappe_issue_id, attachments=None):

	comm = frappe.get_doc({
		"doctype": "Communication",
		"subject": subject,
		"content": description,
		"recipients": recipients,
		"sent_or_received": "Sent",
		"reference_doctype": "ERPNext Support Issue",
		"communication_medium": "Email",
		"sender": raised_by,
		"reference_name": client_issue_id,
		"has_attachment": 1 if attachments else 0
	}).insert(ignore_permissions=True)

	if isinstance(attachments, string_types):
		attachments = json.loads(attachments)

	if attachments:
		add_attachments("Communication", comm.name, attachments)
		add_attachments("ERPNext Support Issue", client_issue_id, attachments)

	frappe.db.commit()

	file_attachments = []

	if attachments:
		for a in attachments:
			filename, content = get_file(a)
			if content and isinstance(content, string_types):
				content = content.encode("utf-8")
			file_attachments.append({
				"filename": filename,
				"content": base64.b64encode(content).decode("ascii")
			})

	file_attachments = json.dumps(file_attachments)

	params = {
		"subject": subject,
		"recipients": recipients,
		"description": description,
		"raised_by": raised_by,
		"frappe_issue_id": frappe_issue_id,
		"attachments": file_attachments
	}

	last_sync_on = json.loads(call_remote_method("create_reply_from_customer", params))
	frappe.db.set_value("ERPNext Support Issue", client_issue_id, "last_sync_on", get_datetime(last_sync_on.get("last_sync_on")))

# Sync Rating
@frappe.whitelist()
def sync_feedback_and_rating_from_client(support_rating, client_issue_id, frappe_issue_id, add_a_comment=None):
	params = {
		"support_rating": support_rating,
		"frappe_issue_id": frappe_issue_id
	}

	frappe.db.set_value("ERPNext Support Issue", client_issue_id, "support_rating", support_rating)
	if add_a_comment:
		frappe.db.set_value("ERPNext Support Issue", client_issue_id, "add_a_comment", add_a_comment)
		params.update({
			"add_a_comment": add_a_comment
		})

	call_remote_method("create_feedback_and_rating_from_customer", params)
	frappe.publish_realtime("refresh_erpnext_support_issue")

@frappe.whitelist(allow_guest=True)
def enqueue_sync(client_issue_id, client_hash):
	if not validate_hash(client_hash):
		return

	enqueue("erpnext_support.api.client.sync", erpnext_support_issue=client_issue_id)

@frappe.whitelist(allow_guest=True)
def enqueue_split_issue_sync(client_hash):
	if not validate_hash(client_hash):
		return

	enqueue("erpnext_support.api.client.sync_split_issues")

# Remote Connection to Server
def call_remote_method(method, params=None, validate_usage_limits=True):
	if validate_usage_limits:
		validate_limits()

	try:
		connection = get_remote_connection()
	except Exception:
		frappe.log_error(frappe.get_traceback())
		frappe.throw(_("Couldn't connect to ERPNext Support. Please try again in sometime."))

	if isinstance(params, frappe.string_types):
		params = json.loads(params)

	params.update({
		"erpnext_support_user": frappe.conf.erpnext_support_user,
		"bench_site": frappe.utils.get_url(),
		"cmd": "erpnext_support.api.server." + method
	})

	try:
		return connection.post_request(params)
	except Exception:
		frappe.log_error(frappe.get_traceback())
		return {"failed": True}

def get_remote_connection():
	if not (frappe.conf.erpnext_support_url and frappe.conf.erpnext_support_user and frappe.conf.erpnext_support_password):
		create_support_user()

	remote_connection = FrappeClient(frappe.conf.erpnext_support_url, frappe.conf.erpnext_support_user, \
		frappe.conf.erpnext_support_password)

	return remote_connection

# Validate Limits
@frappe.whitelist()
def validate_limits():
	if frappe.conf.erpnext_support_url == frappe.utils.get_url() or (frappe.conf.limits and \
		frappe.conf.limits.get("current_plan") == "Free"):

		return

	expiry, allocated_users	= get_expiry_and_users()

	if getdate(expiry) < now_datetime().date():
		frappe.throw(_("Your ERPNext Support Subscription has expired."))

	query = """
		select count(*) from tabUser where user_type="System User" and enabled=1 and name not in ("Administrator", "Guest")
	"""
	enabled_users = frappe.db.sql(query, as_dict=True)

	if int(allocated_users) < enabled_users[0].get("count(*)"):
		frappe.throw(_("ERPNext Support is only available for {0} Users.").format(allocated_users))

# Sync Expiry and No. of Users for Frappe Cloud as well as Self Hosted in Cache
def set_expiry_and_users(doc=None, method=None):
	if frappe.conf.limits and frappe.conf.limits.get("expiry") and frappe.conf.limits.get("users"):
		frappe.cache().hset("erpnext_support", "expiry", frappe.conf.limits.get("expiry"))
		frappe.cache().hset("erpnext_support", "users", frappe.conf.limits.get("users"))
	else:
		limits = json.loads(call_remote_method("sync_expiry_and_users_for_self_hosted", params={}, validate_usage_limits=False))
		frappe.cache().hset("erpnext_support", "expiry", limits.get("self_hosted_expiry"))
		frappe.cache().hset("erpnext_support", "users", limits.get("self_hosted_users"))

def get_expiry_and_users():
	if not (frappe.cache().hget("erpnext_support", "expiry") and frappe.cache().hget("erpnext_support", "users")):
		set_expiry_and_users()

	return frappe.cache().hget("erpnext_support", "expiry"), frappe.cache().hget("erpnext_support", "users")
