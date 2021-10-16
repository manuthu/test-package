import frappe

def execute():
    frappe.installer.update_site_config("activations_last_sync_on", 0)