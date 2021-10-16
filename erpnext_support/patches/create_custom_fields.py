import frappe

def execute():
	if frappe.conf.erpnext_support_url == frappe.utils.get_url():
		make_custom_field("Issue", "Raised via Support App", "raised_via_support_app", "Check", "Customer", 1, 0)
		make_custom_field("Issue", "Support Rating", "support_rating", "Int", "Customer", 1, 0)
		make_custom_field("Issue", "Comment", "add_a_comment", "Text", "Customer", 1, 0)
		make_custom_field("Customer", "Self Hosted Details", "self_hosted_details", "Section Break", "Customer POS id", 0, 1)
		make_custom_field("Customer", "Bench Site", "bench_site", "Data", "Self Hosted Details", 0, 0)
		make_custom_field("Customer", "Self Hosted Users", "self_hosted_users", "Int", "Bench Site", 0, 0)
		make_custom_field("Customer", "Self Hosted Expiry", "self_hosted_expiry", "Date", "Self Hosted Users", 0, 0)

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
