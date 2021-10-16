# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from frappe import _

def get_data():
	return [
		{
			"module_name": "ERPNext Support Issue",
			"category": "Places",
			"label": _('ERPNext Support'),
			"icon": "fa fa-ticket",
			"type": 'link',
			"link": '#list/ERPNext Support Issue/list',
			"doctype": "ERPNext Support Issue",
			"color": '#589494',
			"description": "ERPNext Support."
		},
	]