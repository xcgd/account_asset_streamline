# -*- encoding: utf-8 -*-

import time
from openerp.osv import fields, osv


class account_asset_category_streamline(osv.Model):

    _name = 'account.asset.category'
    _inherit = 'account.asset.category'

    _defaults = {
        'method_period': 1,
    }

account_asset_category_streamline()


class account_asset_asset_streamline(osv.Model):

    _name = 'account.asset.asset'
    _inherit = 'account.asset.asset'

    _columns = {

        'quantity': fields.char(
            'Quantity',
            size=64,
        ),
        'service_date': fields.date(
            'Placed in Service date',
            required=True,
            readonly=True,
            states={
                'draft': [('readonly', False)]
            },
        ),
        'insurance_type': fields.char(
            'Type',
            size=64,
        ),
        'insurance_contract_number': fields.char(
            'Contract number',
            size=64,
        ),
        'insurance_contract_amount': fields.integer(
            'Contract amount',
        ),
        'insurance_company_deductible': fields.integer(
            'Company deductible amount',
        ),
        'start_insurance_contract_date': fields.date(
            'Contract start date',
        ),
        'end_insurance_contract_date': fields.date(
            'Contract end date',
        ),
        'insurance_partner_id': fields.many2one(
            'res.partner',
            'Contact partner',
        ),
        'disposal_date': fields.date(
            'Asset disposal date',
        ),
        'sales_value': fields.integer(
            'Sales value',
        ),
    }

    _defaults = {
        'method_period': 1,
        'service_date': lambda *a: time.strftime('%Y-%m-%d')
    }

account_asset_asset_streamline()

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
