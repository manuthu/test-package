frappe.provide("frappe.views");
frappe.provide('erpnext_support');
frappe.require("/assets/css/erpnext-support.css");
// add toolbar icon
$(document).bind('toolbar_setup', function() {
	// additional help links for erpnext
	let $help_menu = $('.dropdown-help #help-links');
	$('<li><a href="#List/ERPNext%20Support%20Issue/List">' + __("ERPNext Support") + '</a></li> \
		<li class="divider"></li>').insertBefore($help_menu);
	let report_issue = $('.dropdown-help ul > li:contains("Report an Issue")');
	if (report_issue.length > 0) {
		report_issue.remove();
	}
});

// Support Message
frappe.call("erpnext_support.api.client_utils.show_support_message").then((r) => {
	if (r.message) {
		let d = new frappe.ui.Dialog({
			"title": `<span class="indicator whitespace-nowrap green" style="color: #000; font-size: inherit;">${__("Introducing In-App Support")}</span>`,
			"fields": [
				{
					"fieldname": "description",
					"fieldtype": "HTML",
					"options": `<p>${__("Hello,")}</p>
								<p>${__("Now you can create, track and also check the resolution time of your tickets right from")} <b>${__("ERPNext.")}</b></p>
								<p>${__("We recommend you to start using <b>ERPNext Support</b> accessible from ")}<b>${__("Help")}</b>${__(" button in the top navigation bar.")}</p>
								<p>${__("To learn more, click ")}<u><b><a target="_blank" href="https://erpnext.com/frappe-in-app-support">${__(" here")}</a></b></u>.</p>`
				}
			]
		});
		d.show();
	}
});

// Set Frappe Framework and ERPNext Versions for attachment dialog
if(!frappe.versions) {
	frappe.call({
		method: "frappe.utils.change_log.get_versions",
		callback: function(r) {
			frappe.versions = r.message;
		}
	});
}

erpnext_support.count_support_issues = function(context) {
	if (!frappe.boot.limits
		|| (frappe.boot.limits
		&& frappe.boot.limits.subscription_status != 'Trial')) return;
	frappe.call({
		method: "erpnext_support.erpnext_support.doctype.erpnext_support_issue.erpnext_support_issue.count_support_issues",
		callback: function(r) {
			context.issue_count = r.message;
		},
		async: false
	});
}

// Reply Dialog with Attachments
frappe.views.ReplyComposer = Class.extend({
	init: function (opts) {
		$.extend(this, opts);

		frappe.run_serially([
			() => erpnext_support.count_support_issues(this),
			() => this.get_upgrade_url(),
			() => this.make()
		]);
	},
	get_upgrade_url: function() {
		if (!frappe.boot.limits
			|| (frappe.boot.limits
			&& frappe.boot.limits.subscription_status != 'Trial')) return;
		let me = this;
		frappe.call({
			method: "journeys.journeys.config._get_upgrade_url",
			callback: function(r) {
				me.upgrade_url = r.message;
			},
			async: false
		});
	},

	make: function () {
		var me = this;
		let dialog_title = "Reply";

		if(me.is_new === 1) {
			dialog_title = `New Support Issue`;
		}

		this.dialog = new frappe.ui.Dialog({
			title: __(dialog_title),
			fields: this.get_fields(),
			primary_action_label: __("Submit"),
			primary_action: (values) => {
				this.reply(values);
			}
		});

		// Only used for uplaoding attachments for v11
		$(document).on("upload_complete", function(event, attachment) {
			if(me.dialog.display) {
				var wrapper = $(me.dialog.fields_dict.select_attachments.wrapper);

				// find already checked items
				var checked_items = wrapper.find('[data-file-name]:checked').map(function() {
					return $(this).attr("data-file-name");
				});

				// reset attachment list
				me.render_attach();

				// check latest added
				checked_items.push(attachment.name);

				$.each(checked_items, function(i, filename) {
					wrapper.find('[data-file-name="'+ filename +'"]').prop("checked", true);
				});
			}
		})
		this.setup_fields_for_error_report();
		this.setup_attach();
		// this.restore_draft();
		this.dialog.show();
	},
	get_fields: function () {
		var me = this;
		let fields = [];

		// add a warning about support ticket limit on the pen ultimate issue creation.
		if (frappe.boot.limits
			&& me.is_new === 1
			&& frappe.boot.limits.subscription_status == 'Trial'
			&& frappe.boot.limits.support_tickets_limit
			&& me.issue_count > (frappe.boot.limits.support_tickets_limit - 2)) {
			fields.push(
				{
					fieldtype: "HTML",
					fieldname: "issue_warning",
					options: `<h6 class="notification-note warn">
						<i class="fa fa-info-circle" aria-hidden="True"></i>
						&nbsp;Trial subscribers can only raise a maximum of
						${frappe.boot.limits.support_tickets_limit} support tickets.
						<a href="${this.upgrade_url}" target="_blank">Upgrade now</a>.
					</h6>`
				}
			)
		}

		if(me.is_new === 1) {
			fields.push(
				{
					fieldtype: "Data",
					fieldname: "subject",
					label: __("Subject"),
					reqd: 1
				},
				{
					fieldtype: "Select",
					options: "\nBilling & Payment\nHow to\nBug\nPerformance\nFeature Request\nError Report",
					fieldname: "issue_type",
					label: __("Issue Type"),
					reqd: 1
				},
				{
					fieldtype: "Select",
					options: "\nAccounts\nAsset\nBuying\nCRM\nData Import\nEducation\nHealthcare\nHotels\nHR\nManufacturing\nPermissions\nPOS\nPrint Format\nProjects\nReports\nSelling\nSetup\nStock\nSupport\nWebsite",
					depends_on: "eval: doc.issue_type === \"How to\"",
					fieldname: "issue_found_in",
					label: __("Issue Found In")
				}
			)
		}

		fields.push(
			{
				fieldtype: "Text Editor",
				fieldname: "reply",
				label: __(me.is_new === 1 ? "Describe your Issue and add Screenshots/GIFs" : "Reply"),
				reqd: 1
			},
			{
				fieldtype:"HTML",
				fieldname:"select_attachments",
				label:__("Add Multiple Attachments"),
			}
		);

		return fields
	},
	setup_attach: function () {
		var fields = this.dialog.fields_dict;
		var attach = $(fields.select_attachments.wrapper);

		var me = this;
		if (!me.attachments){
			me.attachments = []
		}

		// Make attachments Frappe Framework v11 and v12 compatible
		if(parseInt(frappe.versions.frappe.version) > 11){
			//v12 Compatible attachments
			let args = {
				folder: 'Home/Attachments',
				on_success: attachment => {
					this.attachments.push(attachment);
					me.render_attach();
				}
			};

			$("<h6 class='text-muted add-attachment' style='margin-top: 12px; cursor:pointer;'>"
				+__("Select Attachments")+"</h6><div class='attach-list'></div>\
				<p class='add-more-attachments'>\
				<a class='text-muted small'><i class='octicon octicon-plus' style='font-size: 12px'></i> "
				+__("Add Attachment")+"</a></p>").appendTo(attach.empty())
			attach
				.find(".add-more-attachments a")
				.on('click',() => new frappe.ui.FileUploader(args));
			this.render_attach();
			this.select_attachments();
		} else {
			//v11 Compatible attachments
			var args = {
				args: {
					from_form: 1,
					folder:"Home/Attachments"
				},
				callback: function(attachment, r) {
					me.attachments.push(attachment);
				},
				max_width: null,
				max_height: null
			};

			$("<h6 class='text-muted add-attachment' style='margin-top: 12px; cursor:pointer;'>"
				+__("Attachments")+"</h6><div class='attach-list'></div>\
				<p class='add-more-attachments'>\
				<a class='text-muted small'><i class='octicon octicon-plus' style='font-size: 12px'></i> "
				+__("Add Attachment")+"</a></p>").appendTo(attach.empty())
			attach.find(".add-more-attachments a").on('click',this,function() {
				me.upload = frappe.ui.get_upload_dialog(args);
			})
			me.render_attach()
		}
	},
	render_attach: function () {
		var fields = this.dialog.fields_dict;
		var attach = $(fields.select_attachments.wrapper).find(".attach-list").empty();

		var files = [];
		if (this.attachments && this.attachments.length) {
			files = files.concat(this.attachments);
		}

		if(files.length) {
			$.each(files, function(i, f) {
				if (!f.file_name) return;
				f.file_url = frappe.urllib.get_full_url(f.file_url);

				$(repl('<p class="checkbox">'
					+	'<label><span><input type="checkbox" data-file-name="%(name)s" checked></input></span>'
					+		'<span class="small">%(file_name)s</span>'
					+	' <a href="%(file_url)s" target="_blank" class="text-muted small">'
					+		'<i class="fa fa-share" style="vertical-align: middle; margin-left: 3px;"></i>'
					+ '</label></p>', f))
					.appendTo(attach)
			});
		}
	},
	select_attachments: function () {
		let me = this;
		if(me.dialog.display) {
			let wrapper = $(me.dialog.fields_dict.select_attachments.wrapper);

			let checked_items = wrapper.find('[data-file-name]:not(:checked)').map(function() {
				return $(this).attr("data-file-name");
			});

			$.each(checked_items, function(i, filename) {
				wrapper.find('[data-file-name="'+ filename +'"]').prop("checked", true);
			});
		}
	},
	setup_fields_for_error_report: function () {
		if (this.subject && this.issue_type && this.description) {
			this.dialog.set_value("subject", this.subject);
			this.dialog.set_value("issue_type", this.issue_type);
			this.dialog.set_value("reply", this.description);
		}
	},
	reply: function (values) {
		var me = this;

		let selected_attachments = $.map($(me.dialog.wrapper).find("[data-file-name]:checked"), function (element) {
			return $(element).attr("data-file-name");
		});

		if (me.is_new === 1){
			if (values.issue_type === "How to" && !values.issue_found_in) {
				frappe.throw(__("Please select Issue Found In."));
			}

			me.clear_dialog();

			let issue = {
				"subject": values.subject,
				"issue_type": values.issue_type,
				"issue_found_in": values.issue_found_in ? values.issue_found_in : null,
				"raised_by": frappe.session.user_email,
				"description": values.reply,
				"attachments": selected_attachments
			};

			this.save_draft(issue);

			frappe.realtime.on("erpnext_support_issue", function(r){
				frappe.set_route("Form", "ERPNext Support Issue", r);
			})

			frappe
				.call('erpnext_support.erpnext_support.doctype.erpnext_support_issue.erpnext_support_issue.create_erpnext_support_issue', issue)
				.then( (r) => {
					me.dialog.enable_primary_action();
					this.delete_draft();
				});

		} else {
			me.clear_dialog();

			frappe.show_alert({
				indicator: 'green',
				message: __('Replying')
			});

			let issue_reply = {
				"client_issue_id": me.frm.doc.name,
				"description": values.reply,
				"subject": me.frm.doc.subject,
				"raised_by": frappe.session.user_email,
				"recipients": "support@erpnext.com",
				"frappe_issue_id": me.frm.doc.frappe_issue_id,
				"attachments": selected_attachments
			};

			frappe
				.call('erpnext_support.api.client.reply_to_support_issue', issue_reply)
				.then(() => {
					me.dialog.enable_primary_action();
				});
		}
	},
	clear_dialog: function () {
		this.dialog.disable_primary_action();
		this.dialog.hide();
		this.dialog.clear();
	},
	save_draft: function (issue) {
		localStorage.setItem("ESI", JSON.stringify(issue));
	},
	delete_draft: function () {
		localStorage.removeItem("ESI");
	},
	restore_draft: function () {
		if (localStorage.getItem("ESI")) {
			let draft = JSON.parse(localStorage.getItem("ESI"));

			this.dialog.set_value("subject", draft.subject);
			this.dialog.set_value("issue_type", draft.issue_type);
			this.dialog.set_value("issue_found_in", draft.issue_found_in);
			this.dialog.set_value("reply", draft.description);
		}
	}
})

// Handle Error Reports
frappe.request.report_error = function(xhr, request_opts) {
	let show_reply_composer = function() {
		let error_report_message = [
			'<h5>Please type some additional information that could help us reproduce this issue:</h5>',
			'<div style="min-height: 100px; border: 1px solid #bbb; \
				border-radius: 5px; padding: 15px; margin-bottom: 15px;"></div>',
			'<hr>',
			'<h5>App Versions</h5>',
			'<pre>' + JSON.stringify(frappe.boot.versions, null, "\t") + '</pre>',
			'<h5>Route</h5>',
			'<pre>' + frappe.get_route_str() + '</pre>',
			'<hr>',
			'<h5>Error Report</h5>',
			'<pre>' + exc + '</pre>',
			'<hr>',
			'<h5>Request Data</h5>',
			'<pre>' + JSON.stringify(request_opts, null, "\t") + '</pre>',
			'<hr>',
			'<h5>Response JSON</h5>',
			'<pre>' + JSON.stringify(data, null, '\t')+ '</pre>'
		].join("\n");

		let reply_composer = new frappe.views.ReplyComposer({
			subject: 'Error Report [' + frappe.datetime.nowdate() + ']',
			description: error_report_message,
			issue_type: "Error Report",
			doc: {},
			is_new: 1
		});
		reply_composer.dialog.$wrapper.css("z-index", cint(frappe.msg_dialog.$wrapper.css("z-index")) + 1);
	}

	let data = JSON.parse(xhr.responseText);
	let exc = null;

	if (data.exc) {
		try {
			exc = (JSON.parse(data.exc) || []).join("\n");
		} catch (e) {
			exc = data.exc;
		}
		delete data.exc;
	} else {
		exc = null;
	}

	if (exc) {
		request_opts = frappe.request.cleanup_request_opts(request_opts);

		if (!frappe.error_dialog) {
			frappe.error_dialog = new frappe.ui.Dialog({
				title: 'Server Error',
				primary_action_label: __('Report'),
				primary_action: () => {
					show_reply_composer();
					frappe.error_dialog.hide();
				}
			});
			frappe.error_dialog.wrapper.classList.add('msgprint-dialog');
		}
		let parts = strip(exc).split('\n');
		frappe.error_dialog.$body.html(parts[parts.length - 1]);
		frappe.error_dialog.show();
	}
}
