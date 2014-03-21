# -*- coding: utf-8 -*-
##############################################################################
#
##############################################################################
{
    'name': u"Asset Streamline",
    'version': u"0.1",
    'author': u"XCG Consulting",
    'category': u"Custom Module",
    'description': u"""Includes several integrity fixes and optimizations over
    the standard module.
    """,
    'website': u"",
    'depends': [
        'base',
        'account_streamline',
        'account_asset'
    ],
    'data': [
        'wizard/account_asset_change_values_view.xml',
        'views/account_asset_view.xml',
        'wizard/account_asset_depreciation_wizard.xml',
        'wizard/account_asset_change_duration_view.xml',
    ],
    'demo': [
        'demo/account_asset_demo.xml'
    ],
    'css': [
    ],
    'test': [],
    'installable': True,
    'active': False,
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
