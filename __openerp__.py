# -*- coding: utf-8 -*-
##############################################################################
#
##############################################################################
{
    'name': u"Asset Streamline",
    'version': "1.3.2",
    'author': u"XCG Consulting",
    'category': u"Custom Module",
    'description': u"""Includes several integrity fixes and optimizations over
    the standard module.
    """,
    'website': u"",
    'depends': [
        'base',
        'account_streamline',
        'analytic_structure',
        'account_asset',
        'oemetasl',
    ],
    'data': [
        'data/asset_sequence.xml',
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
