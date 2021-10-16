import frappe
from erpnext_support.api.server_utils import set_custom_field as server_fields

def execute():
	frappe.reload_doctype("ERPNext Support Issue")

	if frappe.db.has_column("ERPNext Support Issue", "associated_issue"):
		frappe.db.sql("UPDATE `tabERPNext Support Issue` SET frappe_issue_id=associated_issue")

	if frappe.conf.erpnext_support_url == frappe.utils.get_url():
		server_fields()

		if frappe.db.has_column("Issue", "associated_issue"):
			frappe.db.sql("UPDATE `tabIssue` SET client_issue_id=associated_issue")

		frappe.delete_doc_if_exists("Custom Field", "Issue-associated_issue")
