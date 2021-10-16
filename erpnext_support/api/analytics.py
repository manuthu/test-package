import frappe
import json

from frappe.utils import add_days, getdate, now, date_diff
from frappe.installer import update_site_config
from erpnext_support.api.client import call_remote_method

def get_weekly_module_analytics(doc=None, method=None):
	
	# if not frappe.conf.limits.get("subscription_status") == "Paid":
	# 	return

	if frappe.utils.get_url() == frappe.conf.erpnext_support_url:
		return

	to_date = getdate()
	activations_per_day = {}

	if not frappe.conf.activations_last_sync_date:
		from_date = getdate('01-01-2020')
	else:
		sync_date = getdate(frappe.conf.activations_last_sync_date)
		if sync_date == to_date:
			return

		from_date = add_days(to_date, date_diff(sync_date, to_date))

	analytics = []
	skip_modules = ["Core", "Email", "Regional", "Social"]
	skip_doctypes = ["GL Entry", "Stock Ledger Entry", "Leave Ledger Entry", "Journal Entry", "Payment Entry", "Property Setter", 
	"Notification Log", "Notification settings", "Route History"]
	
	doctype_filters={
		"name": ["not in", skip_doctypes], 
		"module": ["not in", skip_modules], 
		"issingle": 0, 
		"istable": 0, 
		"custom": 0
	}

	for doctype in frappe.get_all('DocType', filters=doctype_filters, fields=["name", "module"]):
		query = """
				SELECT COUNT(*) AS activation_count, DATE(creation) AS creation_date
				FROM `tab{doctype}`
				WHERE creation BETWEEN %s AND %s GROUP BY creation_date
			""".format(doctype=doctype.name)
		
		activations = frappe.db.sql(query, (from_date, to_date), as_dict=True)

		for activation in activations:
			if activation.activation_count:
				now_date = activation.creation_date.strftime("%Y-%m-%d")
				
				if activations_per_day.get(now_date):
					activations_per_day[now_date] += activation.activation_count
				else: 
					activations_per_day[now_date] = activation.activation_count

				analytics.append({
					"document_type": doctype.name,
					"module": doctype.module,
					"activations": activation.activation_count,
					"activation_date": activation.creation_date.strftime("%Y-%m-%d")
				})

	if not len(analytics):
		return

	params = {
		"from_date": from_date.strftime("%Y-%m-%d"),
		"to_date": to_date.strftime("%Y-%m-%d"),
		"analytics": json.dumps(analytics),
		"activations_per_day": json.dumps(activations_per_day)
	}
	
	result = call_remote_method("dump_analytics", params, False)

	if not (result and result.get("failed")):
		update_site_config("activations_last_sync_date", now())
