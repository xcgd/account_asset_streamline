# -*- encoding: utf-8 -*-

from openerp.osv import fields, osv
import time
from datetime import datetime, date
from dateutil.relativedelta import relativedelta


class account_asset_category_streamline(osv.Model):

    _name = 'account.asset.category'
    _inherit = 'account.asset.category'

    _defaults = {
        'method_period': 1,
    }


class account_asset_asset_streamline(osv.Model):

    _name = 'account.asset.asset'
    _inherit = 'account.asset.asset'

    def _get_method_end(self, cr, uid, ids, field_name, args, context=None):

        assets = self.browse(cr, uid, ids, context)
        res = {}
        for asset in assets:
            date = datetime.strptime(asset.service_date, "%Y-%m-%d").date()
            prorata = asset.prorata
            method_number = asset.method_number
            if(prorata):
                month_dec = relativedelta(months=method_number)
            else:
                month_dec = relativedelta(months=(method_number - 1))
            res[asset.id] = date + month_dec
        return res

    _columns = {

        'quantity': fields.char(
            u'Quantity',
            size=64,
        ),
        'service_date': fields.date(
            u'Placed in Service date',
            required=True,
            readonly=True,
            states={
                'draft': [('readonly', False)]
            },
        ),
        'method_end_fct': fields.function(
            _get_method_end,
            type='date',
            string=u'Calculated end date',
            readonly=True,
            store={
                'account.asset.asset': (
                    lambda self, cr, uid, ids, c={}: ids,
                    ['service_date', 'method_number', 'prorata'],
                    10
                ),
            },
        ),
        'insurance_type': fields.char(
            u'Type',
            size=64,
        ),
        'insurance_contract_number': fields.char(
            u'Contract number',
            size=64,
        ),
        'insurance_contract_amount': fields.integer(
            u'Contract amount',
        ),
        'insurance_company_deductible': fields.integer(
            u'Company deductible amount',
        ),
        'start_insurance_contract_date': fields.date(
            u'Contract start date',
        ),
        'end_insurance_contract_date': fields.date(
            u'Contract end date',
        ),
        'insurance_partner_id': fields.many2one(
            'res.partner',
            u'Contact partner',
        ),
        'disposal_date': fields.date(
            u'Asset disposal date',
        ),
        'sales_value': fields.integer(
            u'Sales value',
        ),
        'last_depreciation_date': fields.date(
            u'Last depreciation date'
        ),
    }

    _defaults = {
        'method_period': 1,
        'service_date': lambda *a: time.strftime('%Y-%m-%d')
    }

    def deprecate(self, cr, uid, ids, context=None):

        vals = {'last_depreciation_date': time.strftime('%Y-%m-%d')}
        self.write(cr, uid, ids, vals, context=context)

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
