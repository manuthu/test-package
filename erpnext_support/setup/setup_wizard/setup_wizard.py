# Copyright (c) 2019, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from __future__ import unicode_literals

import frappe
from frappe import _
from erpnext_support.api.server_utils import set_custom_field as server_fields

def get_setup_stages(args=None):
	stages = [
		{
			'status': _('Installing Support App'),
			'fail_msg': _('Failed to install Support App'),
			'tasks': [
				{
					'fn': setup_fields,
					'args': args,
					'fail_msg': _("Failed to install Support App")
				}
			]
		},
	]

	return stages

def setup_fields(args=None):
	server_fields()
