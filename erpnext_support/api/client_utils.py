from __future__ import unicode_literals

import frappe
import os
import json
from erpnext_support.api.server_utils import make_custom_field
from frappe import _
from frappe.frappeclient import FrappeClient
from frappe.installer import update_site_config
from frappe.utils import getdate, nowdate, get_datetime
from erpnext_support.api.server_utils import get_hash_for_client

# Create Support User for particular Bench
def create_support_user():
	url = frappe.conf.erpnext_support_url
	user = frappe.conf.erpnext_support_user
	password = frappe.conf.erpnext_support_password

	if not url:
		common_site_config_path = os.path.join(frappe.utils.get_bench_path(), "sites", "common_site_config.json")
		url = "https://frappe.io"
		update_site_config("erpnext_support_url", url, site_config_path=common_site_config_path)

	if not (user and password):
		user = "erpnext_support_"+ frappe.utils.random_string(8) +"@erpnext.com"
		password = frappe.utils.random_string(16)

		params = {
			"cmd": "erpnext_support.api.server.make_support_user",
			"user": user,
			"password": password
		}

		r = FrappeClient(url)
		res = json.loads(r.post_request(params))

		if res:
			common_site_config_path = os.path.join(frappe.utils.get_bench_path(), "sites", "common_site_config.json")
			update_site_config("erpnext_support_user", res.get("user"), site_config_path=common_site_config_path)
			update_site_config("erpnext_support_password", res.get("password"), site_config_path=common_site_config_path)

@frappe.whitelist()
def show_support_message():
	if getdate == getdate("2020-01-27") and not frappe.cache().hget("erpnext_support", frappe.session.user):
		frappe.cache().hset("erpnext_support", frappe.session.user, True)
		return True

	return False

def validate_hash(client_hash):
	if client_hash == get_hash_for_client(frappe.utils.get_url()):
		return True

	return False
