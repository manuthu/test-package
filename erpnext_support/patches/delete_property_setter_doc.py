import frappe

def execute():
	# Delete Property Setter for issue_type as it used to be synced and updated.
	if frappe.db.exists("Property Setter", {"doc_type": "ERPNext Support Issue", "field_name": "issue_type"}):
		frappe.db.sql("""delete from `tabProperty Setter`
			where `tabProperty Setter`.doc_type='ERPNext Support Issue'
			and `tabProperty Setter`.field_name='issue_type'""")