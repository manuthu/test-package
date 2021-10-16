from __future__ import unicode_literals

import frappe
import json
import re
import base64
import os
import time

from six import string_types
from frappe.utils import add_days, today, get_datetime, getdate, date_diff, get_datetime_str, call
from frappe.installer import update_site_config
from frappe.utils.file_manager import save_file
from frappe.utils import now_datetime
from erpnext_support.api.server_utils import get_attachments, is_date_between, chunk, bulk_insert
from frappe import _, enqueue
from erpnext_support.api.server_utils import is_new, is_server, get_hash_for_client
from frappe.frappeclient import FrappeClient

# Make Issue
@frappe.whitelist()
def create_issue_from_customer(client_issue_id, erpnext_support_user, subject, description, issue_found_in, issue_type,
	raised_by, recipients, bench_site, attachments=None):
	authenticate_erpnext_support_user(erpnext_support_user)

	issue = frappe.get_doc({
		"doctype": "Issue",
		"subject": subject,
		"raised_by": raised_by,
		"bench_site": bench_site,
		"client_issue_id": client_issue_id,
		"module": issue_found_in,
		"issue_type": issue_type,
		"owner": raised_by,
		"raised_via_support_app": 1
	}).insert(ignore_permissions=True)

	create_reply_from_customer(erpnext_support_user=erpnext_support_user, subject=subject, description=description, \
		raised_by=raised_by, recipients=recipients, bench_site=bench_site, frappe_issue_id=issue.name, attachments=attachments)

	return {
		"name": issue.get("name"),
		"last_sync_on": get_datetime_str(now_datetime()),
		"priority": issue.get("priority"),
		"resolution_by": get_datetime_str(issue.get("resolution_by")) if issue.get("resolution_by") else None,
		"release": issue.get("release")
	}

# Make and Sync Communication
@frappe.whitelist()
def create_reply_from_customer(erpnext_support_user, subject, description, raised_by, recipients, bench_site,
	frappe_issue_id, attachments=None):
	authenticate_erpnext_support_user(erpnext_support_user)

	comm = frappe.get_doc({
		"doctype":"Communication",
		"subject": subject,
		"content": description,
		"sent_or_received": "Received",
		"reference_doctype": "Issue",
		"communication_medium": "Email",
		"sender": raised_by,
		"recipients": recipients,
		"reference_name": frappe_issue_id,
		"has_attachment": 1 if attachments else 0
	}).insert(ignore_permissions=True)

	if attachments:
		attachments = json.loads(attachments)

		for d in attachments:
			save_file(d.get("filename"), d.get("content"), "Communication", comm.name, decode=True)

	frappe.db.set_value("Issue", frappe_issue_id, "status", "Open")

	return json.dumps({
		"last_sync_on": get_datetime_str(now_datetime())
	})

# Issue Status
@frappe.whitelist()
def change_issue_status(client_issue_id, status, erpnext_support_user, frappe_issue_id):
	authenticate_erpnext_support_user(erpnext_support_user)

	support_issue = frappe.get_doc("Issue", frappe_issue_id)
	support_issue.status = status
	support_issue.save(ignore_permissions=True)

	enqueue(method=send_notification_email_to_assignees, issue=support_issue)

def send_notification_email_to_assignees(issue):
	if not issue.status == "Closed":
		return

	assignees = ",".join([assignee for assignee in issue.get_assigned_users()])

	frappe.sendmail(
		subject=_("Issue {0} closed by Customer.").format(issue.name),
		recipients=assignees,
		message=_("Issue {0} - {1} has been closed by the Customer.").format(frappe.bold(issue.name), frappe.bold(issue.subject))
	)

@frappe.whitelist()
def serve_communications_and_statuses(erpnext_support_user, erpnext_support_issues, bench_site):
	"""
		returns a dict of support issue communications and statuses
		response = {
			"issue_name_1": {
				"communications": [],
				"status": "status",
				"last_sync_on": "last_sync_on"
			},
			"issue_name_2": {
				"communications": [],
				"status": "status",
				"last_sync_on": "last_sync_on"
			}
		}
	"""
	authenticate_erpnext_support_user(erpnext_support_user)
	sync_time = get_datetime_str(now_datetime())
	res = {}
	time.sleep(5)

	for erpnext_support_issue in json.loads(erpnext_support_issues):
		if not erpnext_support_issue.get("frappe_issue_id"):
			continue

		# Sync Communications for Issue
		fields = ["name", "subject", "content", "recipients", "has_attachment", "creation"]
		filters = [
			["reference_doctype", "=", "Issue"],
			["reference_name", "=", erpnext_support_issue.get("frappe_issue_id")],
			["communication_medium", "=", "Email"],
			["sent_or_received", "=", "Sent"],
			["creation", ">", get_datetime(erpnext_support_issue.get("last_sync_on"))]
		]
		communications = call(frappe.get_all, doctype="Communication", filters=filters, fields=fields, order_by="creation ASC")

		# Sync Attachments for Communications
		communications = get_attachments(communications)

		# Sync Status for Issue
		frappe_issue = frappe.get_doc("Issue", erpnext_support_issue.get("frappe_issue_id"))

		res[erpnext_support_issue.get("name")] = {
			"communications": communications,
			"status": "Open" if frappe_issue.get("status") not in ["Open", "Closed"] else frappe_issue.get("status"),
			"priority": frappe_issue.get("priority"),
			"resolution_by": get_datetime_str(frappe_issue.resolution_by) if frappe_issue.resolution_by else None,
			"last_sync_on": sync_time,
			"release": frappe_issue.get("release")
		}

	return json.dumps(res)

# Sync Split From Issues
@frappe.whitelist()
def serve_split_issues(erpnext_support_user, bench_site):
	"""
		returns a dict of support issue communications and statuses of split issues
		response = {
			"issue_name_1": "{
				"issue": [],
				"communications": [],
				"last_sync_on": "last_sync_on"
			}",
			"issue_name_2": "{
				"issue": [],
				"communications": [],
				"last_sync_on": "last_sync_on"
			}"
		}
	"""
	authenticate_erpnext_support_user(erpnext_support_user)

	res = {}
	sync_time = get_datetime_str(now_datetime())

	fields = ["name", "subject", "raised_by", "module", "issue_type", "owner", "status", "priority", "resolution_by"]
	filters = [
		["bench_site", "=", bench_site],
		["issue_split_from", "!=", ""],
		["client_issue_id", "=", ""],
		["split_issue_sync", "=", 0]
	]

	for split_issue in frappe.get_all("Issue", filters=filters, fields=fields):
		frappe.db.set_value("Issue", split_issue.name, "split_issue_sync", 1)

		fields = ["name", "subject", "content", "recipients", "sent_or_received", "has_attachment"]
		filters = [
			["reference_doctype", "=", "Issue"],
			["reference_name", "=", split_issue.name],
			["communication_medium", "=", "Email"]
		]

		# Sync Communications for Issue
		communications = frappe.get_all("Communication", filters=filters, fields=fields, order_by="creation ASC")

		# Sync Attachments for Communications
		communications = get_attachments(communications)

		res[split_issue.name] = {
			"frappe_issue_id": split_issue.get("name"),
			"subject": split_issue.get("subject"),
			"communications": communications,
			"last_sync_on": sync_time,
			"status": split_issue.get("status"),
			"priority": split_issue.get("priority"),
			"resolution_by": get_datetime_str(split_issue.resolution_by) if split_issue.resolution_by else None,
			"release": split_issue.get("release"),
			"raised_by": split_issue.get("raised_by"),
			"issue_type": split_issue.get("issue_type")
		}

	return json.dumps(res)

# Sets Associated issues for Split From Issues
@frappe.whitelist()
def set_corresponding_erpnext_support_issue(erpnext_support_user, erpnext_support_issue_mapping, bench_site):
	authenticate_erpnext_support_user(erpnext_support_user)

	erpnext_support_issue_mapping = json.loads(erpnext_support_issue_mapping)

	for erpnext_support_issue in erpnext_support_issue_mapping:
		frappe.db.set_value("Issue", erpnext_support_issue, "client_issue_id", erpnext_support_issue_mapping.get(erpnext_support_issue))

# Sync Rating
@frappe.whitelist()
def create_feedback_and_rating_from_customer(frappe_issue_id, erpnext_support_user, support_rating, bench_site, add_a_comment=None):
	authenticate_erpnext_support_user(erpnext_support_user)

	frappe.db.set_value("Issue", frappe_issue_id, "support_rating", support_rating)
	if add_a_comment:
		frappe.db.set_value("Issue", frappe_issue_id, "add_a_comment", add_a_comment)

def reset_client_issue_id(doc=None, method=None):
	if not doc.get("issue_split_from") or not doc.get("client_issue_id"):
		return

	doc.db_set("client_issue_id", "")
	doc.db_set("split_issue_sync", 0)

	call_client_remote_method("enqueue_split_issue_sync", doc.get("bench_site"), {})

def send_sync_request_to_client(doc=None, method=None):
	if not doc or is_new(doc) or not is_server() or not (doc.get("client_issue_id") and doc.get("bench_site")):
		return

	call_client_remote_method("enqueue_sync", doc.get("bench_site"), {"client_issue_id": doc.get("client_issue_id")})

def check_if_new_communication(doc=None, method=None):
	if not doc or not doc.get("reference_doctype") == "Issue" or doc.get("sent_or_received") == "Received":
		return

	send_sync_request_to_client(doc=frappe.get_doc(doc.get("reference_doctype"), doc.get("reference_name")))

# Sync Expiry and No. of Users for Self Hosted with Client
@frappe.whitelist()
def sync_expiry_and_users_for_self_hosted(erpnext_support_user, bench_site):
	authenticate_erpnext_support_user(erpnext_support_user)

	return json.dumps({
		"self_hosted_users": str(frappe.db.get_value("Customer", {"bench_site": bench_site}, "self_hosted_users")),
		"self_hosted_expiry": str(frappe.db.get_value("Customer", {"bench_site": bench_site}, "self_hosted_expiry"))
	})

def call_client_remote_method(method, bench_site=None, params=None):
	if not bench_site:
		return

	if isinstance(params, frappe.string_types):
		params = json.loads(params)

	params.update({
		"client_hash": get_hash_for_client(bench_site),
		"cmd": "erpnext_support.api.client." + method
	})

	try:
		FrappeClient(bench_site).post_request(params)
	except Exception:
		frappe.log_error(frappe.get_traceback())

# Creation and Authentication of Support User
def authenticate_erpnext_support_user(erpnext_support_user, bench_site=None):
	user = frappe.get_doc("User", {"email": erpnext_support_user})
	roles = frappe.get_roles(erpnext_support_user)

	if frappe.conf.erpnext_support_user == erpnext_support_user and "Support Bot" in roles:
		return True
	frappe.throw(frappe.AuthenticationError)

@frappe.whitelist(allow_guest=True)
def make_support_user(user, password):
	if frappe.conf.erpnext_support_user and frappe.conf.erpnext_support_password:
		return json.dumps({
			"user": frappe.conf.erpnext_support_user,
			"password": frappe.conf.erpnext_support_password
		})

	role = frappe.db.exists("Role", "Support Bot")

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

	role = frappe.db.exists("Role", "Support Team")
	if role:
		support_user.add_roles(role)

	role = frappe.db.exists("Role", "System Manager")
	if role:
		support_user.add_roles(role)

	common_site_config_path = os.path.join(frappe.utils.get_bench_path(), "sites", "common_site_config.json")
	update_site_config("erpnext_support_user", user, site_config_path=common_site_config_path)
	update_site_config("erpnext_support_password", password, site_config_path=common_site_config_path)

	return json.dumps({
		"user": user,
		"password": password
	})

@frappe.whitelist()
def dump_analytics(erpnext_support_user, bench_site, from_date, to_date, analytics, activations_per_day):
	authenticate_erpnext_support_user(erpnext_support_user)

	analytics = json.loads(analytics)
	activations_per_day = json.loads(activations_per_day)

	time = frappe.utils.get_datetime()
	site_analytics = []
	sales_invoices = None
	customer_territory = None
	
	_from_date = getdate(from_date)
	_to_date = getdate(to_date)
	site_name = bench_site.rsplit("//", 1)[-1]

	customer = frappe.get_all('Customer', fields=["name", "territory"], filters={'account_id': ['like', site_name+'%']}, limit=1, order_by='`tabCustomer`.creation DESC')
	if customer:
		customer_territory = customer[0].territory
		sales_invoice_filters = {
			'customer': ['like', customer[0].name],
			'status': 'Paid'
		}

		sales_invoices = frappe.get_all('Sales Invoice', filters=sales_invoice_filters, 
			fields=["base_net_total", "posting_date", "account_expiry"], order_by='`tabSales Invoice`.creation DESC')

	
	fields = ["name", "bench_site", "document_type", "module", "activations", "activation_date", 
		"modified_by", "owner", "creation", "modified", "doctype_revenue", "territory"]

	for analytic in analytics:
		doctype_revenue = 0
		activation_date_time = getdate(analytic.get("activation_date"))

		if sales_invoices:

			sales_invoice = next((sales_invoice for sales_invoice in sales_invoices 
				if is_date_between(activation_date_time, sales_invoice.posting_date, sales_invoice.account_expiry)), None)

			if sales_invoice:
				total_activations_per_day = activations_per_day[analytic.get("activation_date")]
				revenue_per_day = sales_invoice.base_net_total / date_diff(sales_invoice.account_expiry, sales_invoice.posting_date)
				doctype_percent = (analytic.get('activations') / total_activations_per_day) * 100
				doctype_revenue = (revenue_per_day * doctype_percent) / 100


		name = frappe.generate_hash(bench_site + analytic.get("activation_date"))

		site_analytics.append((name, site_name, analytic.get("document_type"), analytic.get("module"), 
			analytic.get("activations"), activation_date_time, "Administrator", "Administrator", time, time, doctype_revenue, customer_territory))

	if len(site_analytics) > 10000:
		for chunked_site_analytics in list(chunk(site_analytics, 10000)):
			bulk_insert("Activation Record", fields=fields, values=chunked_site_analytics, ignore_duplicates=True)
	else:
		bulk_insert("Activation Record", fields=fields, values=site_analytics, ignore_duplicates=True)