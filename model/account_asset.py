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

    # TODO This method needs to be overloaded with a new behavior.
    def compute_depreciation_board(self, cr, uid, ids, context=None):
        depreciation_lin_obj = self.pool.get('account.asset.depreciation.line')
        currency_obj = self.pool.get('res.currency')
        for asset in self.browse(cr, uid, ids, context=context):
            if asset.value_residual == 0.0:
                continue
            posted_depreciation_line_ids = depreciation_lin_obj.search(cr, uid, [('asset_id', '=', asset.id), ('move_check', '=', True)],order='depreciation_date desc')
            old_depreciation_line_ids = depreciation_lin_obj.search(cr, uid, [('asset_id', '=', asset.id), ('move_id', '=', False)])
            if old_depreciation_line_ids:
                depreciation_lin_obj.unlink(cr, uid, old_depreciation_line_ids, context=context)

            amount_to_depr = residual_amount = asset.value_residual
            if asset.prorata:
                depreciation_date = datetime.strptime(self._get_last_depreciation_date(cr, uid, [asset.id], context)[asset.id], '%Y-%m-%d')
            else:
                # depreciation_date = 1st January of purchase year
                purchase_date = datetime.strptime(asset.purchase_date, '%Y-%m-%d')
                #if we already have some previous validated entries, starting date isn't 1st January but last entry + method period
                if (len(posted_depreciation_line_ids)>0):
                    last_depreciation_date = datetime.strptime(depreciation_lin_obj.browse(cr,uid,posted_depreciation_line_ids[0],context=context).depreciation_date, '%Y-%m-%d')
                    depreciation_date = (last_depreciation_date+relativedelta(months=+asset.method_period))
                else:
                    depreciation_date = datetime(purchase_date.year, 1, 1)
            day = depreciation_date.day
            month = depreciation_date.month
            year = depreciation_date.year
            total_days = (year % 4) and 365 or 366

            undone_dotation_number = self._compute_board_undone_dotation_nb(cr, uid, asset, depreciation_date, total_days, context=context)
            for x in range(len(posted_depreciation_line_ids), undone_dotation_number):
                i = x + 1
                amount = self._compute_board_amount(cr, uid, asset, i, residual_amount, amount_to_depr, undone_dotation_number, posted_depreciation_line_ids, total_days, depreciation_date, context=context)
                company_currency = asset.company_id.currency_id.id
                current_currency = asset.currency_id.id
                # compute amount into company currency
                amount = currency_obj.compute(cr, uid, current_currency, company_currency, amount, context=context)
                residual_amount -= amount
                vals = {
                     'amount': amount,
                     'asset_id': asset.id,
                     'sequence': i,
                     'name': str(asset.id) +'/' + str(i),
                     'remaining_value': residual_amount,
                     'depreciated_value': (asset.purchase_value - asset.salvage_value) - (residual_amount + amount),
                     'depreciation_date': depreciation_date.strftime('%Y-%m-%d'),
                }
                depreciation_lin_obj.create(cr, uid, vals, context=context)
                # Considering Depr. Period as months
                depreciation_date = (datetime(year, month, day) + relativedelta(months=+asset.method_period))
                day = depreciation_date.day
                month = depreciation_date.month
                year = depreciation_date.year
        return True

    def _get_method_end(self, cr, uid, ids, field_name, args, context=None):

        assets = self.browse(cr, uid, ids, context)
        res = {}
        for asset in assets:
            if asset.method_time == 'end':
                res[asset.id] = asset.method_end
                continue
            date = datetime.strptime(asset.service_date, "%Y-%m-%d").date()
            method_number = asset.method_number
            month_dec = relativedelta(months=method_number)
            day_dec = relativedelta(days=1)
            res[asset.id] = (date + month_dec) - day_dec
        return res

    def _get_method_number(self, cr, uid, ids, field_name, args, context=None):

        assets = self.browse(cr, uid, ids, context=context)
        res = {}
        for asset in assets:
            if asset.method_time == 'number':
                res[asset.id] = asset.method_number
                continue
            srv_date = datetime.strptime(asset.service_date, "%Y-%m-%d").date()
            end_date = datetime.strptime(asset.method_end, "%Y-%m-%d").date()
            nb_periods = 1
            nb_periods += end_date.month - srv_date.month
            nb_periods += (end_date.year - srv_date.year) * 12
            res[asset.id] = nb_periods
        return res

    def _calculate_daily_deprecation(self, cr, uid, ids, context=None):

        asset = self.browse(cr, uid, ids, context=context)
        value_residual = asset.value_residual
        method_time = asset.method_time

        if method_time == 'number':
            method_number = asset.method_number
            monthly_deprecation = value_residual / method_number
            daily_deprecation = monthly_deprecation / 30

        else:
            srv_date = datetime.strptime(asset.service_date, "%Y-%m-%d").date()
            end_date = datetime.strptime(asset.method_end, "%Y-%m-%d").date()
            nb_months = end_date.month - srv_date.month
            nb_months += (end_date.year - srv_date.year) * 12
            nb_days = end_date.month - srv_date.month
            nb_days += nb_months * 30
            print nb_days
            daily_deprecation = value_residual / nb_days

        return daily_deprecation

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
                    ['service_date', 'method_number'],
                    10
                ),
            },
        ),
        'method_number_fct': fields.function(
            _get_method_number,
            type='integer',
            string=u'Calculated deprecations',
            readonly=True,
            store={
                'account.asset.asset': (
                    lambda self, cr, uid, ids, c={}: ids,
                    ['service_date', 'method_end'],
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
        'a1_id': fields.many2one(
            'analytic.code',
            "Analysis Code 1",
            domain=[
                ('nd_id.ns_id.model_name', 'in', ['account_asset_asset']),
                ('nd_id.ns_id.ordering', '=', '1'),
            ],
            track_visibility='onchange',
        ),
        'a2_id': fields.many2one(
            'analytic.code',
            "Analysis Code 2",
            domain=[
                ('nd_id.ns_id.model_name', 'in', ['account_asset_asset']),
                ('nd_id.ns_id.ordering', '=', '2'),
            ],
            track_visibility='onchange',
        ),
        'a3_id': fields.many2one(
            'analytic.code',
            "Analysis Code 3",
            domain=[
                ('nd_id.ns_id.model_name', 'in', ['account_asset_asset']),
                ('nd_id.ns_id.ordering', '=', '3'),
            ],
            track_visibility='onchange',
        ),
        'a4_id': fields.many2one(
            'analytic.code',
            "Analysis Code 4",
            domain=[
                ('nd_id.ns_id.model_name', 'in', ['account_asset_asset']),
                ('nd_id.ns_id.ordering', '=', '4'),
            ],
            track_visibility='onchange',
        ),
        'a5_id': fields.many2one(
            'analytic.code',
            "Analysis Code 5",
            domain=[
                ('nd_id.ns_id.model_name', 'in', ['account_asset_asset']),
                ('nd_id.ns_id.ordering', '=', '5'),
            ],
            track_visibility='onchange',
        ),
        't1_id': fields.many2one(
            'analytic.code',
            "Transaction Code 1",
            domain=[
                ('nd_id.ns_id.model_name', 'in', ['account_move_line']),
                ('nd_id.ns_id.ordering', '=', '1'),
            ],
            track_visibility='onchange',
        ),
        't2_id': fields.many2one(
            'analytic.code',
            "Transaction Code 2",
            domain=[
                ('nd_id.ns_id.model_name', 'in', ['account_move_line']),
                ('nd_id.ns_id.ordering', '=', '2'),
            ],
            track_visibility='onchange',
        ),
        't3_id': fields.many2one(
            'analytic.code',
            "Transaction Code 3",
            domain=[
                ('nd_id.ns_id.model_name', 'in', ['account_move_line']),
                ('nd_id.ns_id.ordering', '=', '3'),
            ],
            track_visibility='onchange',
        ),
        't4_id': fields.many2one(
            'analytic.code',
            "Transaction Code 4",
            domain=[
                ('nd_id.ns_id.model_name', 'in', ['account_move_line']),
                ('nd_id.ns_id.ordering', '=', '4'),
            ],
            track_visibility='onchange',
        ),
        't5_id': fields.many2one(
            'analytic.code',
            "Transaction Code 5",
            domain=[
                ('nd_id.ns_id.model_name', 'in', ['account_move_line']),
                ('nd_id.ns_id.ordering', '=', '5'),
            ],
            track_visibility='onchange',
        ),
    }

    _defaults = {
        'method_period': 1,
        'service_date': lambda *a: time.strftime('%Y-%m-%d')
    }

    def fields_get(
        self, cr, uid, allfields=None, context=None, write_access=True
    ):
        """Override this function to rename analytic fields."""

        res = super(account_asset_asset_streamline, self).fields_get(
            cr, uid, allfields=allfields, context=context,
            write_access=write_access
        )

        analytic_osv = self.pool.get('analytic.structure')
        res = analytic_osv.analytic_fields_get(
            cr, uid, 'account_asset_asset', res, context=context
        )
        res = analytic_osv.analytic_fields_get(
            cr, uid, 'account_move_line', res, prefix='t', context=context
        )

        return res

    def fields_view_get(
        self, cr, uid, view_id=None, view_type='form', context=None,
        toolbar=False, submenu=False
    ):

        res = super(account_asset_asset_streamline, self).fields_view_get(
            cr, uid, view_id=view_id, view_type=view_type, context=context,
            toolbar=toolbar, submenu=submenu
        )

        analytic_osv = self.pool.get('analytic.structure')
        res = analytic_osv.analytic_fields_view_get(
            cr, uid, 'account_asset_asset', res, context=context
        )
        res = analytic_osv.analytic_fields_view_get(
            cr, uid, 'account_move_line', res, prefix='t', context=context
        )

        return res

    def depreciate(self, cr, uid, ids, context=None):

        period_id = self._get_period(cr, uid, context=context)
        period_osv = self.pool.get('account.period')
        period = period_osv.browse(cr, uid, period_id, context=context)
        pattern = "%Y-%m-%d"
        period_start = datetime.strptime(period.date_start, pattern).date()
        period_stop = datetime.strptime(period.date_stop, pattern).date()

        assets = self.browse(cr, uid, ids, context=context)
        for asset in assets:

            srv_date = datetime.strptime(asset.service_date, pattern).date()
            daily_deprecation = self._calculate_daily_deprecation(
                cr, uid, asset.id, context=context
            )
            if asset.method_time == 'end':
                end_field = asset.method_end
            else:
                end_field = asset.method_end_fct
            end_date = datetime.strptime(end_field, pattern).date()

            if(end_date <= period_stop):
                depreciation_value = asset.value_residual
            elif (srv_date >= period_start):
                diff_days = srv_date.day - period_start.day
                depreciation_value = daily_deprecation * (30 - diff_days)
            else:
                depreciation_value = daily_deprecation * 30

            self.depreciate_move(cr, uid, ids, depreciation_value,
                context=context
            )

        vals = {'last_depreciation_date': time.strftime('%Y-%m-%d')}
        self.write(cr, uid, ids, vals, context=context)

    # TODO Implementation
    def depreciate_move(self, cr, uid, ids, depreciation_value, context=None):
        pass


# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
