// Copyright (c) 2019, Frappe and contributors
// For license information, please see license.txt
frappe.provide("erpnext_support");

frappe.ui.form.on("ERPNext Support Issue", {
	setup: function(frm) {
		// Set Read Only for status if Closed
		set_status_read_only(frm);
	},
	refresh: function(frm) {
		// Set Frappe Issue Id in toolbar
		frm.page.set_title_sub(frm.doc.frappe_issue_id);

		// Hide Comment Button and disable Comment
		$(".btn-comment").addClass("hide");
		frm.timeline.comment_area.quill.disable();
		//Changes the Add a Comment Label
		$(".comment-input-header .small")[0].textContent = "Add a Comment (For internal communication purpose only)";

		// Set Read Only for status if Closed
		set_status_read_only(frm);

		// Show Contact Frappe Dashboard Alert if tried syncing 5 times
		if(frm.doc.sync_count >= 5 && !frm.doc.frappe_issue_id) {
			frm.dashboard.set_headline_alert('\
				<span class="indicator whitespace-nowrap red"> Issue has not been synchronised,\
				<a href="https://erpnext.com/contact-support/" target="_blank">click here</a>\
				to contact Frappe Technologies.</span>\
			');
		}

		// Redirect to List view and show ReplyComposer if Customer creates new Issue from Menu (Ctrl+B)
		if(frm.doc.__islocal === 1){
			frappe.set_route("List", "ERPNext Support Issue", "List")
			frappe.run_serially([
				() => erpnext_support.count_support_issues(frm),
				() => frm.events.validate_create_support_issue(frm)
			]);
		}

		// To refrain customer from attaching to form
		$(".add-attachment").addClass("hide");

		// Remove Reply and Reply All from Timeline Communications
		$("a[title='Reply']").addClass("hide");
		$("a[title='Reply All']").addClass("hide");

		// Show Feedback Dialog
		if (frm.doc.status === "Closed" && !frm.doc.support_rating
			&& !frm.doc.add_a_comment && frm.doc.frappe_issue_id) {
			get_feedback(frm);
		}

		// Hide New Email button from timeline
		$(".btn-new-email").addClass("hide");

		// Send sync request if then time diff is greater than 5 minutes
		if (frm.doc.status !== "Closed" && frm.doc.frappe_issue_id) {
			let now = new Date(frappe.datetime.get_datetime_as_string());
			let last_sync_on = new Date(frm.doc.last_sync_on);

			if (((now-last_sync_on)/60000) > 10) {
				frappe.xcall("erpnext_support.api.client.sync", {"erpnext_support_issue": frm.doc.name});
			}

			make_reply_button(frm);
		}

		// Refresh form after Frappe Issue Id is set
		frappe.realtime.on("refresh_erpnext_support_issue", function(){
			frm.reload_doc();
		})
	},

	validate_create_support_issue: function(frm) {
		if (frappe.boot.limits && frappe.boot.limits.subscription_status == 'Trial'
				&& frm.issue_count >= frappe.boot.limits.support_tickets_limit)
				frappe.msgprint({
					title: __("Trial Plan Limit Exceeded"),
					message: __('You have exhausted your quota for creating support issues. You need to upgrade you subscription to create more support tickets.'),
					indicator: 'red'
				})
			else {
				new frappe.views.ReplyComposer({doc: {}, is_new: 1});
		}
	}
});



function make_reply_button(frm) {
	$(".btn-new-reply").remove();
	$(".timeline-new-email").append("<button class='btn btn-default btn-new-reply btn-xs'>Reply to ERPNext Support</button>");

	let reply_button = $(".btn-new-reply");
	let args = {"erpnext_support_issue": frm.doc.name}

	reply_button.click(function(){
		reply_button.attr("disabled", true);

		frappe.show_alert({
			indicator: "orange",
			message: __("Synchronizing Communications")
		});

		frappe.xcall("erpnext_support.api.client.sync", args).then(()=>{
			frappe.show_alert({
				indicator: "green",
				message: __("Communications Synchronized")
			});

			reply_button.attr("disabled", false);
			new frappe.views.ReplyComposer({doc: frm.doc, frm: frm, is_new: 0});
		})
	})
};

function set_status_read_only(frm) {
	if (frm.doc.status === "Closed") {
		frm.set_df_property("status", "read_only", 1);
		refresh_field("status");
	}
}

function get_feedback(frm) {
	function get_fields() {
		let fields = [
			{
				"label": __("Suggestion"),
				"fieldtype": "Small Text",
				"fieldname": "add_a_comment",
			}
		];

		if (parseInt(frappe.versions.frappe.version) > 11) {
			fields.unshift({
				"label": __("Rating"),
				"fieldtype": "Rating",
				"fieldname": "support_rating",
				"reqd": 1
			})
		} else {
			fields.unshift({
				"label": __("Rating"),
				"fieldtype": "Select",
				"fieldname": "support_rating",
				"options": "\n1\n2\n3\n4\n5",
				"reqd": 1
			})
		}

		return fields
	}

	let feedback_dialog = new frappe.ui.Dialog({
		title: __("Support Feedback"),
		fields: get_fields(),
		primary_action_label: __("Submit"),
		primary_action: (values) => {
			let args = {
				"support_rating": values.support_rating,
				"add_a_comment": values.add_a_comment,
				"frappe_issue_id": frm.doc.frappe_issue_id,
				"client_issue_id": frm.doc.name
			}

			feedback_dialog.disable_primary_action();
			feedback_dialog.hide();
			feedback_dialog.clear();

			frappe.call("erpnext_support.api.client.sync_feedback_and_rating_from_client", args).then(() => {
				frappe.show_alert({
					indicator: "green",
					message: __("Feedback recorded.")
				});
			});
		}
	});

	feedback_dialog.show();
}