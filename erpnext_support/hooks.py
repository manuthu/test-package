# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from . import __version__ as app_version

app_name = "erpnext_support"
app_title = "ERPNext Support"
app_publisher = "Frappe"
app_description = "In App Support for ERPNext."
app_icon = "fa fa-ticket"
app_color = "grey"
app_email = "support@erpnext.com"
app_license = "MIT"

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/erpnext_support/css/erpnext_support.css"
app_include_js = "/assets/js/erpnext_support.js"

# include js, css files in header of web template
# web_include_css = "/assets/erpnext_support/css/erpnext_support.css"
# web_include_js = "/assets/erpnext_support/js/erpnext_support.js"

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
#	"Role": "home_page"
# }

# Website user home page (by function)
# get_website_user_home_page = "erpnext_support.utils.get_home_page"

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Installation
# ------------

# before_install = "erpnext_support.install.before_install"
# after_install = "erpnext_support.install.after_install"

# Setup Wizard
setup_wizard_stages = "erpnext_support.setup.setup_wizard.setup_wizard.get_setup_stages"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

notification_config = "erpnext_support.notifications.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Issue": {
		"after_insert": "erpnext_support.api.server.reset_client_issue_id",
		"on_update": "erpnext_support.api.server.send_sync_request_to_client"
	},
	"Communication": {
		"after_insert": "erpnext_support.api.server.check_if_new_communication"
	}
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	"hourly": [
		"erpnext_support.api.client.sync",
		"erpnext_support.erpnext_support.doctype.erpnext_support_issue.erpnext_support_issue.sync_erpnext_support_issue",
		"erpnext_support.api.client.set_expiry_and_users",
	],
	"weekly_long": [
		"erpnext_support.api.analytics.get_weekly_module_analytics"
	]
}

# Testing
# -------

# before_tests = "erpnext_support.install.before_tests"

# Overriding Whitelisted Methods
# ------------------------------
#
override_whitelisted_methods = {
	"erpnext_support.api.server.make_issue": "erpnext_support.api.server_old.make_issue",
	"erpnext_support.api.server.sync_issue_status_server": "erpnext_support.api.server_old.sync_issue_status_server",
	"erpnext_support.api.server.change_status_server": "erpnext_support.api.server_old.change_status_server",
	"erpnext_support.api.server.sync_communication_server": "erpnext_support.api.server_old.sync_communication_server",
	"erpnext_support.api.server.make_communication_server": "erpnext_support.api.server_old.make_communication_server",
	"erpnext_support.api.server.sync_feedback_rating_server": "erpnext_support.api.server_old.sync_feedback_rating_server",
	"erpnext_support.api.server.sync_expiry_and_users": "erpnext_support.api.server_old.sync_expiry_and_users"
}

