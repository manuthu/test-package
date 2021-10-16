frappe.provide("erpnext_support");

frappe.listview_settings['ERPNext Support Issue'] = {
	hide_name_column: true,
	before_render: function() {
		erpnext_support.count_support_issues(this);
	},
	onload: function(listview) {
		frappe.route_options = {
			"status": "Open"
		};

		if (frappe.boot.limits && frappe.boot.limits.subscription_status == 'Trial') listview.page.clear_primary_action();

		$(".list-sidebar").prepend(`
			<ul class="list-unstyled sidebar-menu">
				<b><u><a href="https://erpnext.com/docs/user/manual" target="_blank">${__('ERPNext User Manual')}</a></u></b>
			</ul>
		`);
	},
	refresh: function(listview) {
		this.enforce_support_ticket_limit(listview);
	},
	primary_action: function() {
		if (this.disable_reply_composer) return;
		new frappe.views.ReplyComposer({doc: {}, is_new: 1});
	},

	enforce_support_ticket_limit: function(listview) {
		if (frappe.boot.limits && frappe.boot.limits.subscription_status == 'Trial'
			&& this.issue_count >= frappe.boot.limits.support_tickets_limit) {
			this.disable_reply_composer = true;
			listview.page.set_primary_action("Upgrade", ()=>{
				frappe.call({
					method: "journeys.journeys.config._get_upgrade_url",
					callback: function(r) {
						window.open(r.message, '_blank');
					}
				});
			});
		}
	}
};
