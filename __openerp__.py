# -*- coding: utf-8 -*-
##############################################################################
#
#    Asset Management Streamline, for OpenERP
#    Copyright (C) 2013 XCG Consulting (http://odoo.consulting)
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
{
    'name': "Asset Management Streamline",
    'version': '1.7',
    'author': "XCG Consulting",
    'category': "Accounting & Finance",
    'description': """Includes several integrity fixes and optimizations over
    the standard Asset Management module.
    """,
    'website': 'http://odoo.consulting/',
    'depends': [
        'base',
        'account_streamline',
        'account_invoice_streamline',
        'analytic_structure',
        'account_asset',
        'oemetasl',
    ],
    'data': [
        'data/asset_sequence.xml',
        'security/security.xml',
        'security/ir.model.access.csv',
        'wizard/account_asset_close_view.xml',
        'wizard/account_asset_suspend_view.xml',
        'wizard/account_asset_change_values_view.xml',
        'wizard/account_asset_depreciation_wizard.xml',
        'wizard/account_asset_change_duration_view.xml',
        'views/account_asset_view.xml',
    ],
    'demo': [
        'demo/account_asset_demo.xml'
    ],
    'css': [
        'static/src/css/account_asset_streamline.css'
    ],
    'test': [],
    'installable': True,
    'active': False,
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
