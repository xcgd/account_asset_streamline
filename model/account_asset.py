# -*- encoding: utf-8 -*-

from openerp.osv import fields, osv
import time
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from tools.translate import _
import openerp.addons.decimal_precision as dp


class account_asset_category_streamline(osv.Model):

    _name = 'account.asset.category'
    _inherit = 'account.asset.category'

    _defaults = {
        'method_period': 1,
    }


class account_asset_asset_streamline(osv.Model):

    _name = 'account.asset.asset'
    _inherit = ["account.asset.asset", "mail.thread"]

    def compute_depreciation_board(self, cr, uid, ids, context=None):
        """ Creates the projected depreciation/correction lines in the
        Depreciation Board table."""

        assets = self.browse(cr, uid, ids, context=context)
        line_osv = self.pool.get('account.asset.depreciation.line')
        period_osv = self.pool.get('account.period')
        today_str = time.strftime('%Y-%m-%d')
        line_ids = {}
        error = _(u"No period was found after the date: {0}. " \
            "You may need to create them.")

        for a in assets:

            asset_id = a.id
            depreciable_amount = a.depreciable_amount
            end = a.method_end if a.method_time == 'end' else a.method_end_fct
            vals = {
                'net_book_value': a.net_book_value,
                'depreciation_auto': a.depreciation_auto,
                'depreciation_total': a.depreciation_total,
                'theoretical_depreciation': a.theoretical_depreciation,
            }
            sequence = a.depreciation_line_sequence
            line_ids[asset_id] = []

            # Get the latest of current period or placed in service period.
            cur_id = self._get_period(cr, uid, context)
            nxt_id = period_osv.find(cr, uid, a.service_date, context)[0]
            domain = ['|', ('id', '=', cur_id), ('id', '=', nxt_id)]
            period_id = period_osv.search(cr, uid, domain, context=context)[-1]
            if period_id == a.last_depreciation_period.id:
                p = period_osv.browse(cr, uid, period_id, context=context)
                period_id = period_osv.next(cr, uid, p, 1, context)

            old_line_ids = line_osv.search(cr, uid,
                [('asset_id', '=', asset_id), ('move_id', '=', False)]
            )
            if old_line_ids:
                line_osv.unlink(cr, uid, old_line_ids, context=context)

            while vals['net_book_value'] != 0:

                period = period_osv.browse(cr, uid, period_id, context=context)
                try:
                    date_start = period.date_start
                    if period.special:
                        period_id = period_osv.find(cr, uid, date_start,
                            dict(context, account_period_prefer_normal=True)
                        )[0]
                        period = period_osv.browse(
                            cr, uid, period_id, context=context
                        )
                        if period.special:
                            raise Exception
                except:
                    raise osv.except_osv(_('Error!'), error.format(date_start))

                next_period_id = period_osv.next(cr, uid, period, 1, context)
                depr_iter = self._compute_depreciation(a, period, vals=vals)

                for depr in depr_iter:

                    sequence += 1
                    amount = depr['amount']
                    if not amount:
                        continue

                    if depr['type'] == 'correction':
                        name = _(u"Projected Correction")
                    else:
                        name = _(u"Projected Depreciation")

                    line_vals = {
                        'name': name,
                        'sequence': sequence,
                        'asset_id': asset_id,
                        'amount': amount,
                        'depreciable_amount': depreciable_amount,
                        'remaining_value': vals['net_book_value'],
                        'depreciated_value': vals['depreciation_total'],
                        'depreciation_date': today_str,
                        'depreciation_period': period_id
                    }
                    line = line_osv.create(cr, uid, line_vals, context=context)
                    line_ids[asset_id].append(line)

                if date_start > end:
                    break
                period_id = next_period_id

        return line_ids

    def _get_method_end(self, cr, uid, ids, field_name, args, context=None):
        """Compute the end date from the number of depreciations"""

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
        """Compute the number of depreciations from the end date"""

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

    def _get_book_value(self, cr, uid, ids, field_name, args, context=None):

        assets = self.browse(cr, uid, ids, context=context)
        res = {}
        for asset in assets:
            gross_value = asset.adjusted_gross_value
            salvage_value = asset.adjusted_salvage_value
            depreciations = asset.depreciation_total
            res[asset.id] = gross_value - salvage_value - depreciations

        return res

    def _get_depr_amount(self, cr, uid, ids, field_name, args, context=None):

        assets = self.browse(cr, uid, ids, context=context)
        res = {}
        for asset in assets:
            gross_value = asset.adjusted_gross_value
            salvage_value = asset.adjusted_salvage_value
            res[asset.id] = gross_value - salvage_value

        return res

    def _sum(self, fields, cr, uid, ids, field_name, args, context=None):
        """Returns the sum of two or more local fields."""

        assets = self.browse(cr, uid, ids, context=context)
        res = {}
        for asset in assets:
            add = 0
            for field in fields:
                val = getattr(asset, field)
                add += val
            res[asset.id] = add

        return res

    def _calculate_days(self, asset, period_start=None):

        method_time = asset.method_time
        srv_date = datetime.strptime(asset.service_date, "%Y-%m-%d").date()
        if period_start is None:
            period_start = srv_date

        if method_time == 'number':
            nb_months = asset.method_number
            if period_start > srv_date:
                nb_months -= period_start.month - srv_date.month
                nb_months -= (period_start.year - srv_date.year) * 12
                nb_days = min(30, srv_date.day) - min(30, period_start.day)
                nb_days += nb_months * 30
            else:
                nb_days = nb_months * 30

        else:
            end_date = datetime.strptime(asset.method_end, "%Y-%m-%d").date()
            start_date = period_start if period_start > srv_date else srv_date
            nb_months = end_date.month - start_date.month
            nb_months += (end_date.year - start_date.year) * 12
            nb_days = min(30, end_date.day) - min(30, start_date.day)
            nb_days += nb_months * 30

        return nb_days

    def _compute_depreciation(self, asset, period, vals=None):

        if vals is None:
            vals = {}

        pattern = "%Y-%m-%d"
        period_start = datetime.strptime(period.date_start, pattern).date()
        srv_start = datetime.strptime(asset.service_date, pattern).date()

        for k in ('net_book_value', 'depreciation_auto', 'depreciation_total'):
            vals.setdefault(k, getattr(asset, k))

        remaining_days = self._calculate_days(asset, period_start=period_start)

        if remaining_days <= 0:
            correction = vals['net_book_value']
            vals['depreciation_auto'] += correction
            vals['depreciation_total'] += correction
            vals['net_book_value'] = 0
            yield {'type': 'correction', 'amount': correction, 'vals': vals}
            return

        first_depreciation = (period_start.month == srv_start.month and
            period_start.year == srv_start.year)

        total_days = self._calculate_days(asset)
        elapsed_days = total_days - remaining_days
        prorata = 30

        theoretical_depreciation = vals.get(
            'theoretical_depreciation',
            asset.theoretical_depreciation
        )

        if not theoretical_depreciation:
            initial = asset.adjusted_gross_value - asset.adjusted_salvage_value
            theoretical_depreciation = initial / total_days
        expected_depreciation = theoretical_depreciation * elapsed_days
        correction = expected_depreciation - vals['depreciation_total']

        # Correction line only if there is at least one cent to correct
        if abs(correction) > 0.01:
            vals['depreciation_auto'] += correction
            vals['depreciation_total'] += correction
            vals['net_book_value'] -= correction
            yield {'type': 'correction', 'amount': correction, 'vals': vals}

        daily_depreciation = vals['net_book_value'] / remaining_days

        if remaining_days <= prorata:
            depreciation = vals['net_book_value']

        else:
            if first_depreciation:
                prorata -= min(30, srv_start.day) - min(30, period_start.day)
            depreciation = daily_depreciation * prorata

        vals['depreciation_total'] += depreciation
        vals['depreciation_auto'] += depreciation
        vals['net_book_value'] -= depreciation

        next_days = elapsed_days + min(prorata, remaining_days)
        theoretical_depreciation = vals['depreciation_total'] / next_days
        vals['theoretical_depreciation'] = theoretical_depreciation

        yield {'type': 'depreciation', 'amount': depreciation, 'vals': vals}
        return

    _gross_cols = ['purchase_value', 'additional_value']
    _salvage_cols = ['salvage_value', 'salvage_adjust']
    _depreciation_cols = [
        'depreciation_initial',
        'depreciation_auto',
        'depreciation_manual'
    ]

    _states = [
        ('draft', u"Draft"),
        ('open', u"Running"),
        ('suspended', u"Suspended"),
        ('close', u"Disposed"),
    ]

    _columns = {

        'state': fields.selection(
            _states,
            u"Status",
            required=True,
            help="When an asset is created, the status is 'Draft'.\n" \
                "If the asset is confirmed, the status goes in 'Running' and "\
                "the depreciation lines can be posted in the accounting.\n" \
                "You can manually close an asset when the depreciation is " \
                "over. If the last line of depreciation is posted, the asset "\
                "automatically goes in that status."
        ),
        'description': fields.char(
            u"Description",
            size=256
        ),
        'additional_value': fields.float(
            u"Additional Value",
            readonly=True,
            digits_compute=dp.get_precision('Account'),
        ),
        'adjusted_gross_value': fields.function(
            lambda s, *a: s._sum(s._gross_cols, *a),
            type='float',
            string=u"Adjusted Gross Value",
            readonly=True,
            digits_compute=dp.get_precision('Account'),
            store={
                'account.asset.asset': (
                    lambda self, cr, uid, ids, c={}: ids,
                    _gross_cols,
                    10
                ),
            },
        ),
        'salvage_adjust': fields.float(
            u"Salvage Value Adjustment",
            readonly=True,
            digits_compute=dp.get_precision('Account'),
        ),
        'adjusted_salvage_value': fields.function(
            lambda s, *a: s._sum(s._salvage_cols, *a),
            type='float',
            string=u"Adjusted Salvage Value",
            readonly=True,
            digits_compute=dp.get_precision('Account'),
            store={
                'account.asset.asset': (
                    lambda self, cr, uid, ids, c={}: ids,
                    _salvage_cols,
                    10
                ),
            },
        ),
        'depreciation_initial': fields.float(
            u"Initial Depreciation",
            readonly=True,
            digits_compute=dp.get_precision('Account'),
            states={
                'draft': [('readonly', False)]
            },
        ),
        # TODO Should be functional or at least readonly and edited by methods.
        'depreciation_auto': fields.float(
            u"Automatic Depreciations",
            readonly=True,
            digits_compute=dp.get_precision('Account'),
        ),
        'depreciation_manual': fields.float(
            u"Manual Depreciations",
            readonly=True,
            digits_compute=dp.get_precision('Account'),
        ),
        'depreciation_total': fields.function(
            lambda s, *a: s._sum(s._depreciation_cols, *a),
            type='float',
            string=u"Total of Depreciations",
            readonly=True,
            digits_compute=dp.get_precision('Account'),
            store={
                'account.asset.asset': (
                    lambda self, cr, uid, ids, c={}: ids,
                    _depreciation_cols,
                    10
                ),
            },
        ),
        'net_book_value': fields.function(
            _get_book_value,
            type='float',
            string=u"Net Book Value",
            readonly=True,
            digits_compute=dp.get_precision('Account'),
            store={
                'account.asset.asset': (
                    lambda self, cr, uid, ids, c={}: ids,
                    _gross_cols + _salvage_cols + _depreciation_cols,
                    20
                ),
            },
        ),
        'depreciable_amount': fields.function(
            _get_depr_amount,
            type='float',
            string=u"Depreciable amount",
            readonly=True,
            digits_compute=dp.get_precision('Account'),
        ),
        'theoretical_depreciation': fields.float(
            u"Theoretical Daily Depreciation",
        ),
        'quantity': fields.char(
            u"Quantity",
            size=64,
        ),
        'service_date': fields.date(
            u"Placed in Service Date",
            required=True,
            readonly=True,
            states={
                'draft': [('readonly', False)]
            },
        ),
        'suspension_date': fields.date(
            u"Suspension Date",
            readonly=True,
        ),
        'suspension_reason': fields.char(
            u"Suspension Reason",
            size=256,
            readonly=True,
        ),
        'disposal_date': fields.date(
            u'Disposal Date',
            readonly=True,
        ),
        'disposal_reason': fields.selection(
            [
                ('scrapped', u"Scrapped"),
                ('sold', u"Sold"),
                ('stolen', u"Stolen"),
                ('destroyed', u"Destroyed")
            ],
            u"Disposal Reason",
            size=256,
            translate=True,
            readonly=True,
        ),
        'disposal_value': fields.integer(
            u"Disposal Value",
            readonly=True,
        ),
        'last_depreciation_period': fields.many2one(
            "account.period",
            u"Last Depreciation Period",
            readonly=True,
        ),
        'depreciation_line_sequence': fields.integer(
            u"Depreciation Line Sequence",
            readonly=True,
        ),
        'method_end_fct': fields.function(
            _get_method_end,
            type='date',
            string=u"Calculated End Date",
            readonly=True,
            digits_compute=dp.get_precision('Account'),
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
            string=u"Calculated Depreciations",
            readonly=True,
            digits_compute=dp.get_precision('Account'),
            store={
                'account.asset.asset': (
                    lambda self, cr, uid, ids, c={}: ids,
                    ['service_date', 'method_end'],
                    10
                ),
            },
        ),
        'invoice_ids': fields.one2many(
            'account.asset.invoice',
            'asset_id',
            u"Invoices",
            ondelete='cascade'
        ),
        'insurance_type': fields.char(
            u"Type",
            size=64,
        ),
        'insurance_contract_number': fields.char(
            u"Contract Number",
            size=64,
        ),
        'insurance_contract_amount': fields.integer(
            u"Contract Amount",
        ),
        'insurance_company_deductible': fields.integer(
            u"Company Deductible Amount",
        ),
        'start_insurance_contract_date': fields.date(
            u"Contract Start Date",
        ),
        'end_insurance_contract_date': fields.date(
            u"Contract End Date",
        ),
        'insurance_partner_id': fields.many2one(
            'res.partner',
            u"Contact Partner",
        ),
        'a1_id': fields.many2one(
            'analytic.code',
            u"Analysis Code 1",
            domain=[
                ('nd_id.ns_id.model_name', 'in', ['account_asset_asset']),
                ('nd_id.ns_id.ordering', '=', '1'),
            ],
            track_visibility='onchange',
        ),
        'a2_id': fields.many2one(
            'analytic.code',
            u"Analysis Code 2",
            domain=[
                ('nd_id.ns_id.model_name', 'in', ['account_asset_asset']),
                ('nd_id.ns_id.ordering', '=', '2'),
            ],
            track_visibility='onchange',
        ),
        'a3_id': fields.many2one(
            'analytic.code',
            u"Analysis Code 3",
            domain=[
                ('nd_id.ns_id.model_name', 'in', ['account_asset_asset']),
                ('nd_id.ns_id.ordering', '=', '3'),
            ],
            track_visibility='onchange',
        ),
        'a4_id': fields.many2one(
            'analytic.code',
            u"Analysis Code 4",
            domain=[
                ('nd_id.ns_id.model_name', 'in', ['account_asset_asset']),
                ('nd_id.ns_id.ordering', '=', '4'),
            ],
            track_visibility='onchange',
        ),
        'a5_id': fields.many2one(
            'analytic.code',
            u"Analysis Code 5",
            domain=[
                ('nd_id.ns_id.model_name', 'in', ['account_asset_asset']),
                ('nd_id.ns_id.ordering', '=', '5'),
            ],
            track_visibility='onchange',
        ),
        't1_id': fields.many2one(
            'analytic.code',
            u"Transaction Code 1",
            domain=[
                ('nd_id.ns_id.model_name', 'in', ['account_move_line']),
                ('nd_id.ns_id.ordering', '=', '1'),
            ],
            track_visibility='onchange',
        ),
        't2_id': fields.many2one(
            'analytic.code',
            u"Transaction Code 2",
            domain=[
                ('nd_id.ns_id.model_name', 'in', ['account_move_line']),
                ('nd_id.ns_id.ordering', '=', '2'),
            ],
            track_visibility='onchange',
        ),
        't3_id': fields.many2one(
            'analytic.code',
            u"Transaction Code 3",
            domain=[
                ('nd_id.ns_id.model_name', 'in', ['account_move_line']),
                ('nd_id.ns_id.ordering', '=', '3'),
            ],
            track_visibility='onchange',
        ),
        't4_id': fields.many2one(
            'analytic.code',
            u"Transaction Code 4",
            domain=[
                ('nd_id.ns_id.model_name', 'in', ['account_move_line']),
                ('nd_id.ns_id.ordering', '=', '4'),
            ],
            track_visibility='onchange',
        ),
        't5_id': fields.many2one(
            'analytic.code',
            u"Transaction Code 5",
            domain=[
                ('nd_id.ns_id.model_name', 'in', ['account_move_line']),
                ('nd_id.ns_id.ordering', '=', '5'),
            ],
            track_visibility='onchange',
        ),
        'values_history_ids': fields.one2many(
            'account.asset.values.history',
            'asset_id',
            u"Values History",
            readonly=True
        ),
    }

    _defaults = {
        'depreciation_line_sequence': 0,
        'method_period': 1,
        'service_date': lambda *a: time.strftime('%Y-%m-%d'),
    }

    def unlink(self, cr, uid, ids, context=None):

        history_osv = self.pool.get('account.asset.history')
        for asset in self.browse(cr, uid, ids, context=context):
            domain = [('asset_id', '=', asset.id)]
            history_ids = history_osv.search(cr, uid, domain, context=context)
            history_osv.unlink(cr, uid, history_ids, context=context)
        return super(account_asset_asset_streamline, self).unlink(
            cr, uid, ids, context=context
        )

    def set_to_close(self, cr, uid, ids, context=None):
        vals = {'state': 'close', 'disposal_date': time.strftime('%Y-%m-%d')}
        return self.write(cr, uid, ids, vals, context=context)

    def suspend(self, cr, uid, ids, context=None):
        vals = {
            'state': 'suspended',
            'suspension_date': time.strftime('%Y-%m-%d')
        }
        return self.write(cr, uid, ids, vals, context=context)

    def reactivate(self, cr, uid, ids, context=None):
        vals = {'state': 'open'}
        return self.write(cr, uid, ids, vals, context=context)

    def onchange_category_id(self, cr, uid, ids, category_id, context=None):
        return {}

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

    def depreciate(self, cr, uid, ids, period_id, context=None):

        line_osv = self.pool.get('account.asset.depreciation.line')
        period_osv = self.pool.get('account.period')
        move_osv = self.pool.get('account.move')
        move_line_osv = self.pool.get('account.move.line')
        period = period_osv.browse(cr, uid, period_id, context=context)
        today = date.today()
        today_str = datetime.strftime(today, '%Y-%m-%d')

        assets = self.browse(cr, uid, ids, context=context)
        for asset in assets:

            sequence = asset.depreciation_line_sequence
            vals = {}
            depr_iter = self._compute_depreciation(asset, period, vals=vals)

            for depr in depr_iter:

                sequence += 1
                amount = depr['amount']
                if not amount:
                    continue

                if depr['type'] == 'correction':
                    type_str = _(u"Correction")
                else:
                    type_str = _(u"Depreciation")

                journal_id = asset.category_id.journal_id.id
                move_vals = {
                    'name': asset.name,
                    'date': today_str,
                    'ref': type_str,
                    'period_id': period_id,
                    'journal_id': journal_id,
                    'state': 'draft'
                }
                move_id = move_osv.create(cr, uid, move_vals, context=context)

                line_ref = u"{0} / {1}".format(asset.name, period.name)
                line_name = _(u"Mensual {type} of Asset {ref}").format(
                    type=type_str, ref=line_ref
                )
                stocks_acc = asset.category_id.account_depreciation_id
                expense_acc = asset.category_id.account_expense_depreciation_id
                (cre, deb) = [0 if i < 0 else i for i in [amount, -amount]]
                line_vals_base = {
                    'asset_id': asset.id,
                    'move_id': move_id,
                    'period_id': period_id,
                    'journal_id': journal_id,
                    'ref': line_ref,
                    'partner_id': uid,
                    'date': today_str,
                    'name': line_name,
                    'currency_id': asset.currency_id.id,
                    'a1_id': asset.t1_id.id,
                    'a2_id': asset.t2_id.id,
                    'a3_id': asset.t3_id.id,
                    'a4_id': asset.t4_id.id,
                    'a5_id': asset.t5_id.id,
                }

                for acc in (stocks_acc, expense_acc):
                    line_vals = line_vals_base.copy()
                    line_vals.update(account_id=acc.id, credit=cre, debit=deb)
                    move_line_osv.create(cr, uid, line_vals, context=context)
                    (cre, deb) = (deb, cre)
                move_osv.write(
                    cr, uid, [move_id], {'state': 'posted'}, context=context
                )

                depreciation_vals = {
                    'name': type_str,
                    'sequence': sequence,
                    'asset_id': asset.id,
                    'amount': amount,
                    'depreciable_amount': asset.depreciable_amount,
                    'remaining_value': vals['net_book_value'],
                    'depreciated_value': vals['depreciation_total'],
                    'depreciation_date': today_str,
                    'depreciation_period': period_id,
                    'move_id': move_id,
                }
                line_osv.create(cr, uid, depreciation_vals, context=context)

            vals['last_depreciation_period'] = period_id
            vals['depreciation_line_sequence'] = sequence
            self.write(cr, uid, asset.id, vals, context=context)

        self.compute_depreciation_board(cr, uid, ids, context=context)

    # TODO Implementation
    def depreciate_move(self, cr, uid, ids, depreciation_value, context=None):
        pass


class account_asset_values_history(osv.Model):
    _name = 'account.asset.values.history'
    _description = 'Asset Values history'
    _columns = {
        'name': fields.char(u"Reason", size=64, select=1),
        'user_id': fields.many2one('res.users', u"User", required=True),
        'date': fields.date(u"Date", required=True),
        'asset_id': fields.many2one(
            'account.asset.asset',
            u"Asset",
            required=True,
            ondelete='cascade'
        ),
        'adjusted_value': fields.selection(
            [
                ('additional_value', u"Gross Value Adjustment"),
                ('salvage_adjust', u"Salvage Value Adjustment"),
                ('depreciation_manual', u"Manual Depreciation"),
            ],
            u"Adjusted Value",
        ),
        'new_value': fields.float(
            u"New amount",
        ),
        'note': fields.text(u"Note"),
    }
    _order = 'date desc'
    _defaults = {
        'date': lambda *args: time.strftime('%Y-%m-%d'),
        'user_id': lambda self, cr, uid, ctx: uid
    }


class account_asset_depreciation_line(osv.Model):
    _name = 'account.asset.depreciation.line'
    _inherit = 'account.asset.depreciation.line'
    _columns = {
        'depreciation_period': fields.many2one(
            "account.period",
            u'Depreciation Period',
            readonly=True,
        ),
        'depreciable_amount': fields.float(
            string=u"Depreciable amount",
            digits_compute=dp.get_precision('Account'),
        ),
        'currency_id': fields.related(
            'asset_id',
            'currency_id',
            type='many2one',
            string='Currency'
        ),
    }
    _order = "sequence"


class account_asset_invoice(osv.Model):

    _name = 'account.asset.invoice'
    _description = "Invoice"

    _columns = {
        'date': fields.date(
            u"Date",
            required=True,
        ),
        'ref': fields.char(
            u"Reference",
            size=256,
            required=True,
        ),
        'amount': fields.float(
            u"Amount",
            digits_compute=dp.get_precision('Account'),
            required=True,
        ),
        'comment': fields.text(
            u"Comment",
        ),
        'partner_id': fields.many2one(
            'res.partner',
            u"Contact Partner",
        ),
        'currency_id': fields.many2one(
            'res.currency',
            u"Currency",
            required=True,
        ),
        'asset_id': fields.many2one(
            'account.asset.asset',
            u"Asset",
            readonly=True,
        )
    }

    _defaults = {
        'date': lambda *a: time.strftime('%Y-%m-%d'),
    }

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
