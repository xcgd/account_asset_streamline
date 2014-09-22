# -*- encoding: utf-8 -*-

from openerp.osv import fields, osv
import time
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from openerp.tools.translate import _
import calendar
import openerp.addons.decimal_precision as dp
import psycopg2
from openerp.addons.analytic_structure.MetaAnalytic import MetaAnalytic

class period_error(osv.except_osv):
    """
    This error message is displayed during the projection of an asset's
    depreciation, when it failed to get the next period.
    Takes a date from the previous period as an argument.
    """

    MSG_PATTERN = _(
        u"No period was found after the month: {month}/{year}. "
        u"You may need to create the missing periods."
    )

    def __init__(self, period_date):
        year, month, day = period_date.split('-')
        msg = self.MSG_PATTERN.format(year=year, month=month, day=day)
        super(period_error, self).__init__(_(u"Error!"), msg)


class account_asset_category_streamline(osv.Model):
    """Extends account.asset.category, from the core module account_asset."""

    _name = 'account.asset.category'
    _inherit = 'account.asset.category'

    def _check_journal_account_company(self, cr, uid, ids, context=False):
        categories = self.browse(cr, uid, ids, context=context)
        for category in categories:
            company_id = category.company_id
            for field in self._journal_account_fields:
                if getattr(category, field).company_id != company_id:
                    return False
        return True

    _journal_account_fields = (
        'journal_id',
        'account_asset_id',
        'account_depreciation_id',
        'account_expense_depreciation_id',
        'disposal_journal_id',
        'account_disposal_id'
    )

    _columns = {
        'disposal_journal_id': fields.many2one(
            'account.journal',
            'Disposal Journal',
            required=True
        ),
        'account_disposal_id': fields.many2one(
            'account.account',
            'Asset Disposal Account',
            required=True
        ),
    }

    _defaults = {
        'method_period': 1,
    }

    _constraints = [
        (
            _check_journal_account_company,
            u"Accounts and journals must belong to the same company as the " \
                "category.",
            _journal_account_fields + ('company_id',)
        ),
    ]

    def onchange_company_id(self, cr, uid, ids, context=None):
        value = {field: None for field in self._journal_account_fields}
        return {'value': value}


class account_asset_asset_streamline(osv.Model):
    """Extends account.asset.asset, from the core module account_asset."""

    __metaclass__ = MetaAnalytic
    _name = 'account.asset.asset'
    _inherit = ["account.asset.asset", "mail.thread"]

    def _get_sequence(self, cr, uid, context=None):
        sequence_osv = self.pool.get('ir.sequence')
        return sequence_osv.get(cr, uid, 'asset', context=context)

    def _get_method_end(self, cr, uid, ids, field_name, args, context=None):
        """Compute the end date from the number of depreciations."""

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
        """Compute the number of depreciations from the end date."""

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
        """Compute the net book value from the (adjusted) gross value, the
        (adjusted) salvage value, and the total of all depreciations."""

        assets = self.browse(cr, uid, ids, context=context)
        res = {}
        for asset in assets:
            gross_value = asset.adjusted_gross_value
            depreciations = asset.depreciation_total
            res[asset.id] = gross_value - depreciations

        return res

    def _get_depr_amount(self, cr, uid, ids, field_name, args, context=None):
        """Get the amount to depreciate from the gross and salvage values."""

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

    def _check_category_company(self, cr, uid, ids, context=False):
        assets = self.browse(cr, uid, ids, context=context)
        for asset in assets:
            if asset.category_id.company_id != asset.company_id:
                return False
        return True

    def _nb_days_in_interval(self, start_date, end_date):
        """Return number of days in a time interval for accounting purposes."""

        nb_days = min(30, end_date.day) - min(30, start_date.day) + 1
        nb_months = end_date.month - start_date.month
        nb_months += (end_date.year - start_date.year) * 12
        nb_days += nb_months * 30
        # If the end is last day of February, count it as a 30-day month.
        days_end = calendar.monthrange(end_date.year, end_date.month)[1]
        if(end_date.day == days_end and days_end < 30):
            nb_days += 30 - days_end
        return nb_days

    def _calculate_days(self, asset, start=None):
        """If a starting date is specified as a date object, return the number
        of days between that date and the end date of the depreciation.
        Otherwise, return the total duration of the depreciation instead."""

        # Parse the asset's put-into-service date into a date object.
        srv_date = datetime.strptime(asset.service_date, "%Y-%m-%d").date()
        # Use it as our starting date if said value was not given as argument.
        if start is None:
            start = srv_date

        # If the end is defined by a number of depreciations, use this number.
        method_time = asset.method_time
        if method_time == 'number':
            nb_months = asset.method_number
            # If the depreciation has already begun at the given date...
            if start > srv_date:
                # ...we need to take the elapsed months and days into account.
                nb_months -= start.month - srv_date.month
                nb_months -= (start.year - srv_date.year) * 12
                nb_days = min(30, srv_date.day) - min(30, start.day)
                nb_days += nb_months * 30
            else:
                # We can get the number of days directly from the depreciations
                nb_days = nb_months * 30

        # If it is determined by an end date, either given as an argument or
        # defined in the asset, take the difference between the end date and
        # the latest of either the given date or the service date.
        else:
            end_date = datetime.strptime(asset.method_end, "%Y-%m-%d").date()
            start_date = max(start, srv_date)
            nb_days = self._nb_days_in_interval(start_date, end_date)

        return nb_days

    def _generate_depreciations(self, asset, period, vals=None, end_date=None):
        """Yield up to two dictionaries that contain the key/value pairs:
        * type: the type of depreciation to apply (depreciation or correction).
        * amount: the amount of the depreciation.
        * vals: the new values of the asset's fields after depreciation. Values
          for those same fields can also be given through the vals parameter.

        Fields that can be passed/returned inside the vals dictionary:
        net_book_value, depreciation_(auto|total), theoretical_depreciation.
        """

        if vals is None:
            vals = {}

        salvage_value = asset.adjusted_salvage_value
        period_start = datetime.strptime(period.date_start, "%Y-%m-%d").date()
        period_stop = datetime.strptime(period.date_stop, "%Y-%m-%d").date()
        srv_start = datetime.strptime(asset.service_date, "%Y-%m-%d").date()
        # If the asset isn't in service, no depreciation should be generated.
        if period_stop < srv_start:
            return

        # If a value isn't defined in vals, get its value from the data model.
        for k in ('net_book_value', 'depreciation_auto', 'depreciation_total'):
            vals.setdefault(k, getattr(asset, k))

        remaining_days = self._calculate_days(asset, start=period_start)

        # If the depreciation is supposed to be over but the NBV isn't equal to
        # the salvage value. we just have to rectify it with a correction line.
        if remaining_days <= 0 and vals['net_book_value'] != salvage_value:
            correction = vals['net_book_value'] - salvage_value
            vals['depreciation_auto'] += correction
            vals['depreciation_total'] += correction
            vals['net_book_value'] = salvage_value
            yield {'type': 'correction', 'amount': correction, 'vals': vals}
            return

        total_days = self._calculate_days(asset)
        elapsed_days = total_days - remaining_days

        stop_after_correction = False
        theoretical_depreciation = vals.get(
            'theoretical_depreciation',
            asset.theoretical_depreciation
        )
        # Initialize the daily rate if we are computing our first depreciation.
        # NB: Always done once, but not necessarily on the expected 1st period.
        if not theoretical_depreciation:
            theoretical_depreciation = asset.depreciable_amount / total_days
        # With end_date: if it is before or during the last depreciated period,
        # revert the depreciations for the days in the period after end_date.
        elif end_date is not None:
            last_period = asset.last_depreciation_period.date_stop
            if end_date.strftime('%Y-%m-%d') <= last_period:
                start = max(srv_start, period_start)
                elapsed_days += self._nb_days_in_interval(start, end_date)
                stop_after_correction = True

        expected_depreciation = theoretical_depreciation * elapsed_days
        correction = expected_depreciation - vals['depreciation_total']
        # Correction line only if there is at least one cent to correct.
        if abs(correction) >= 0.01:
            vals['depreciation_auto'] += correction
            vals['depreciation_total'] += correction
            vals['net_book_value'] -= correction
            yield {'type': 'correction', 'amount': correction, 'vals': vals}
            if stop_after_correction:
                return

        date_stop = period_stop if end_date is None else end_date
        # Number of days in the period.
        if period_start > srv_start:
            depr_days = self._nb_days_in_interval(period_start, date_stop)
        else:
            # First depreciation period, only take the days the service date.
            # NB: Periods, including the first period, can always be missed.
            depr_days = self._nb_days_in_interval(srv_start, date_stop)

        to_be_depreciated = vals['net_book_value'] - salvage_value
        # Calculate the depreciation amount and update the asset's values.
        daily_depreciation = to_be_depreciated / remaining_days
        if remaining_days > depr_days:
            depreciation = daily_depreciation * depr_days
        else:  # Last depreciation period, nullify NBV to end the depreciation.
            depreciation = to_be_depreciated
        vals['depreciation_total'] += depreciation
        vals['depreciation_auto'] += depreciation
        vals['net_book_value'] -= depreciation

        # Recalculate the theoretical daily rate for the next depreciation.
        # This is needed because the gross/salvage value and/or the end date
        # may have changed since the previous depreciation.
        next_days = elapsed_days + min(depr_days, remaining_days)
        theoretical_depreciation = vals['depreciation_total'] / next_days
        vals['theoretical_depreciation'] = theoretical_depreciation

        yield {'type': 'depreciation', 'amount': depreciation, 'vals': vals}
        return

    def _create_move_lines(
        self, cr, uid, asset, period, journal, cr_account, deb_account, amount,
        mv_ref='', mv_name='', ml_ref='', ml_name='', date_='', context=None
    ):
        """Create two balanced move lines of a given amount for an asset,
        grouped in an entry, with the analytic fields filled appropriately.
        Return the ID of the move entry."""

        move_osv = self.pool.get('account.move')
        move_line_osv = self.pool.get('account.move.line')
        analytic_osv = self.pool.get('analytic.structure')

        move_ref = _(u"Asset Operation") if not mv_ref else mv_ref
        move_line_ref = _(u"Asset Operation Line") if not ml_ref else ml_ref
        move_line_name = _(u"Asset Operation Line") if not ml_name else ml_name
        date_ = time.strftime('%Y-%m-%d') if not date_ else date_

        # Create the move entry.
        move_vals = {
            'date': date_,
            'ref': move_ref,
            'period_id': period.id,
            'journal_id': journal,
        }
        move = move_osv.create(cr, uid, move_vals, context=context)

        # Prepare the values shared between the move lines.
        line_base_vals = {
            'asset_id': asset.id,
            'move_id': move,
            'period_id': period.id,
            'journal_id': journal,
            'ref': move_line_ref,
            'date': date_,
            'name': move_line_name,
            'currency_id': asset.currency_id.id,
        }
        # Prepare the analytic field values.
        analytic_fields = analytic_osv.get_dimensions_names(
            cr, uid, 'account_move_line', context=context
        )
        for field_order in analytic_fields:
            line_field = "a{0}_id".format(field_order)
            asset_field = "t{0}_id".format(field_order)
            line_base_vals[line_field] = getattr(asset, asset_field).id

        # Convert amount to credit and debit, one positive, the other 0
        (credit, debit) = [0 if i < 0 else i for i in [amount, -amount]]
        # If the total gross value is positive, add a credit line to
        # the first account and a debit line to the second account.
        # If it is negative, do the opposite.
        for account in (cr_account, deb_account):
            vals = line_base_vals.copy()
            vals.update(account_id=account.id, credit=credit, debit=debit)
            move_line_osv.create(cr, uid, vals, context=context)
            # Swap the credit and debit values for the second line.
            (credit, debit) = (debit, credit)

        return move

    # Lists of fields used by functional fields (sum function and store value)
    _gross_cols = [
        'purchase_value',
        'additional_value',
        'gross_disposal'
    ]
    _salvage_cols = [
        'salvage_value',
        'salvage_adjust'
    ]
    _depreciation_cols = [
        'depreciation_initial',
        'depreciation_auto',
        'depreciation_manual',
        'depreciation_disposal',
    ]
    # Lists of values for selection fields
    _states = [
        ('draft', u"Draft"),
        ('open', u"Running"),
        ('suspended', u"Suspended"),
        ('close', u"Disposed"),
    ]
    _methods = [
        ('linear', 'Linear'),
    ]
    _time_methods = [
        ('number', 'Number of Depreciations'),
        ('end', 'Ending Date'),
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
        'category_id': fields.many2one(
            'account.asset.category',
            'Asset Category',
            required=True,
            change_default=True,
            readonly=True,
            track_visibility='onchange',
            states={
                'draft': [('readonly', False)],
            },
        ),
        'method': fields.selection(
            _methods,
            'Computation Method',
            required=True,
            readonly=True,
            track_visibility='onchange',
            states={
                'draft': [('readonly', False)],
            },
            help="Choose the method to use to compute the amount of" \
                "depreciation lines.\n" \
                "  * Linear: Calculated on basis of: Gross Value / Number" \
                "of Depreciations\n",
        ),
        'method_time': fields.selection(
            _time_methods,
            'Time Method',
            required=True,
            readonly=True,
            track_visibility='onchange',
            states={
                'draft': [('readonly', False)],
            },
            help="Choose the method to use to compute the dates and number" \
                "of depreciation lines.\n"\
                "  * Number of Depreciations: Fix the number of depreciation" \
                "lines and the time between 2 depreciations.\n" \
                "  * Ending Date: Choose the time between 2 depreciations" \
                "and the date the depreciations won't go beyond."
        ),
        'method_number': fields.integer(
            'Number of Depreciations',
            readonly=True,
            track_visibility='onchange',
            states={
                'draft': [('readonly', False)],
            },
            help="The number of depreciations needed to depreciate your asset"
        ),
        'method_end': fields.date(
            'Ending Date',
            readonly=True,
            track_visibility='onchange',
            states={
                'draft': [('readonly', False)],
            }
        ),
        'description': fields.char(
            u"Description",
            size=256,
            track_visibility='onchange',
        ),
        'additional_value': fields.float(
            u"Additional Value",
            readonly=True,
            digits_compute=dp.get_precision('Account'),
            track_visibility='onchange',
        ),
        'gross_disposal': fields.float(
            u"Disposed Asset",
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
            track_visibility='onchange',
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
        'depreciation_auto': fields.float(
            u"Automatic Depreciations",
            readonly=True,
            digits_compute=dp.get_precision('Account'),
        ),
        'depreciation_manual': fields.float(
            u"Manual Depreciations",
            readonly=True,
            digits_compute=dp.get_precision('Account'),
            track_visibility='onchange',
        ),
        'depreciation_disposal': fields.float(
            u"Disposed Asset",
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
                    _gross_cols + _depreciation_cols,
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
        'confirmation_date': fields.date(
            u"Confirmation Date",
            readonly=True,
            track_visibility='onchange',
        ),
        'suspension_date': fields.date(
            u"Suspension Date",
            readonly=True,
            track_visibility='onchange',
        ),
        'suspension_reason': fields.char(
            u"Suspension Reason",
            size=256,
            readonly=True,
            track_visibility='onchange',
        ),
        'reactivation_date': fields.date(
            u"Reactivation Date",
            readonly=True,
            track_visibility='onchange',
        ),
        'disposal_date': fields.date(
            u'Disposal Date',
            readonly=True,
            track_visibility='onchange',
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
        'disposal_period': fields.many2one(
            "account.period",
            u"Disposal Period",
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
            ondelete='cascade',
            track_visibility='onchange',
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
        'values_history_ids': fields.one2many(
            'account.asset.values.history',
            'asset_id',
            u"Values History",
            readonly=True
        ),
    }

    _analytic = {
        'a': 'account_asset_asset',
        't': 'account_move_line',
    }

    _defaults = {
        'name': _get_sequence,
        'depreciation_line_sequence': 0,
        'gross_disposal': 0.0,
        'depreciation_disposal': 0.0,
        'method_period': 1,
        'service_date': lambda *a: time.strftime('%Y-%m-%d'),
    }

    _constraints = [
        (
            _check_category_company,
            u"Asset must belong to the same company as its category.",
            ('category_id', 'company_id')
        ),
    ]

    _sql_constraints = [
        (
            'check_purchase_value',
            'CHECK(purchase_value > 0)',
            _(u"The purchase value must be greater than 0."),
        ),
        (
            'check_min_session_count',
            'CHECK(method_time != \'number\' or method_number > 0)',
            _(u"The number of depreciations must be greater than 0."),
        ),
        (
            'check_end_date',
            'CHECK(method_time != \'end\' or method_end >= service_date)',
            _(u"The depreciation end date cannot be before the service date."),
        ),
        (
            'check_service_date',
            'CHECK(service_date >= purchase_date)',
            _(u"The put-into-service date cannot be before the purchase date.")
        ),
        (
            'check_name',
            'UNIQUE(name)',
            _(u"The asset's name must be unique.")
        ),
    ]

    def unlink(self, cr, uid, ids, context=None):
        """Also delete the history rows manually."""

        history_osv = self.pool.get('account.asset.history')
        for asset in self.browse(cr, uid, ids, context=context):
            domain = [('asset_id', '=', asset.id)]
            history_ids = history_osv.search(cr, uid, domain, context=context)
            history_osv.unlink(cr, uid, history_ids, context=context)
        return super(account_asset_asset_streamline, self).unlink(
            cr, uid, ids, context=context
        )

    def reactivate(self, cr, uid, ids, context=None):
        """Change state from Suspended to Open."""
        vals = {
            'state': 'open',
            'suspension_reason': None,
            'reactivation_date': time.strftime('%Y-%m-%d'),
        }
        assets = self.browse(cr, uid, ids, context=context)
        for asset in assets:
            if asset.state == 'suspended':
                self.write(cr, uid, asset.id, vals.copy(), context=context)
            else:
                raise osv.except_osv(_(u"Error!"), _(u"Must be suspended."))
        self.compute_depreciation_board(cr, uid, ids, context=context)

    def validate(self, cr, uid, ids, context=None):
        """Set state to open. Override the method defined in the parent."""
        vals = {
            'state': 'open',
            'confirmation_date': time.strftime('%Y-%m-%d'),
        }
        assets = self.browse(cr, uid, ids, context=context)
        for asset in assets:
            if asset.state == 'draft':
                self.write(cr, uid, asset.id, vals.copy(), context=context)
            else:
                raise osv.except_osv(_(u"Error!"), _(u"Must be a draft."))
        self.compute_depreciation_board(cr, uid, ids, context=context)

    def onchange_category_id(self, cr, uid, ids, category_id, context=None):
        """Unused. Override the method defined in the parent class."""
        return {}

    def compute_depreciation_board(self, cr, uid, ids, context=None):
        """ Create the projected depreciation/correction lines in the
        Depreciation Board table.
        Return a dictionary mapping each asset's ID to its projected lines'."""

        if context == None:
            context = {}

        assets = self.browse(cr, uid, ids, context=context)
        line_osv = self.pool.get('account.asset.depreciation.line')
        period_osv = self.pool.get('account.period')
        today_str = time.strftime('%Y-%m-%d')
        find_context = dict(context, account_period_prefer_normal=True)

        line_ids = {}  # Return value, as described in the doc string.

        # Iterate for every asset.
        for asset in assets:

            asset_id = asset.id
            salvage = asset.adjusted_salvage_value
            company_id = asset.company_id
            find_context['company_id'] = company_id.id
            line_ids[asset_id] = []
            sequence = asset.depreciation_line_sequence
            if asset.method_time == 'end':
                end = asset.method_end
            else:
                end = asset.method_end_fct

            # Delete the old projection lines for the current asset.
            # Keep the actual (move_id=true) and missed (amount=0) lines.
            old_domain = [
                ('asset_id', '=', asset_id),
                ('move_id', '=', False),
                ('amount', '!=', 0),
            ]
            old_ids = line_osv.search(cr, uid, old_domain, context=context)
            if old_ids:
                line_osv.unlink(cr, uid, old_ids, context=context)

            # If the asset is closed, skip it after deleting the lines.
            if asset.state == 'close':
                continue

            # This dictionary's role is to keep the asset's projected field
            # values throughout the simulation. Its values are updated after
            # each iteration of the _generate_depreciations generator.
            vals = {
                'net_book_value': asset.net_book_value,
                'depreciation_auto': asset.depreciation_auto,
                'depreciation_total': asset.depreciation_total,
                'theoretical_depreciation': asset.theoretical_depreciation,
            }

            # If the asset has never been depreciated, start with the put-into-
            # service period. Otherwise, use the earliest non-depreciated one.
            last_period = asset.last_depreciation_period
            if not last_period:
                previous_date = asset.service_date
                service_ids = period_osv.find(
                    cr, uid, previous_date, context=find_context
                )
                if service_ids:
                    period_id = service_ids[0]
                else:
                    raise period_error(asset.service_date)
            else:
                previous_date = last_period.date_start
                period_id = period_osv.next(cr, uid, last_period, 1, context)

            try:  # Browse the starting period and test its existence.
                period = period_osv.browse(cr, uid, period_id, context=context)
                period_start = period.date_start
            except (psycopg2.ProgrammingError, IndexError):
                raise period_error(previous_date)

            # For the current asset, loop on periods until NBV = salvage value
            # AND the current period starts after the depreciation's end date.
            while period_start <= end or vals['net_book_value'] != salvage:

                # If the period returned is special or from another company,
                # try to get an appropriate period with the same start date.
                try:
                    if period.special or period.company_id != company_id:
                        period_id = period_osv.find(cr, uid, period.date_start,
                            context=find_context
                        )[0]
                        period = period_osv.browse(
                            cr, uid, period_id, context=context
                        )
                        if period.special or period.company_id != company_id:
                            raise period_error(period_start)
                except (psycopg2.ProgrammingError, IndexError):
                    raise period_error(period_start)

                # Generate up to two lines for each period: depreciation and/or
                # correction. Create each of those lines in the database.
                depr_iter = self._generate_depreciations(asset, period, vals)
                for depreciation in depr_iter:

                    sequence += 1
                    amount = depreciation['amount']
                    if not amount:
                        continue

                    if depreciation['type'] == 'correction':
                        name = _(u"Projected Correction")
                    else:
                        name = _(u"Projected Depreciation")

                    # Create the projected depreciation line.
                    line_vals = {
                        'name': name,
                        'sequence': sequence,
                        'asset_id': asset_id,
                        'amount': amount,
                        'depreciable_amount': asset.depreciable_amount,
                        'remaining_value': vals['net_book_value'],
                        'depreciated_value': vals['depreciation_total'],
                        'depreciation_date': today_str,
                        'depreciation_period': period_id
                    }
                    line = line_osv.create(cr, uid, line_vals, context=context)
                    line_ids[asset_id].append(line)

                # Get the next period.
                period_id = period_osv.next(cr, uid, period, 1, context)
                period = period_osv.browse(cr, uid, period_id, context=context)

                try:  # Finally, update the period for the next iteration.
                    period_start = period.date_start
                except (psycopg2.ProgrammingError):
                    raise period_error(period_start)

        return line_ids

    def depreciate(self, cr, uid, ids, period_id, disposal=None, context=None):
        """Perform the depreciation of assets."""

        line_osv = self.pool.get('account.asset.depreciation.line')
        period_osv = self.pool.get('account.period')
        today = date.today()
        today_str = datetime.strftime(today, '%Y-%m-%d')

        period = period_osv.browse(cr, uid, period_id, context=context)
        if disposal is None:
            comp_period = period
            end_date = None
        else:
            # If depreciating for a disposal, use the period which corresponds
            # to the disposal DATE for the calculations, even if it is closed.
            domain = [
                ('special', '!=', True),
                ('date_start', '<=', disposal),
                ('date_stop', '>=', disposal),
            ]
            search_ids = period_osv.search(cr, uid, domain, context=context)
            comp_period = period_osv.browse(
                cr, uid, search_ids[0], context=context
            )
            end_date = datetime.strptime(disposal, "%Y-%m-%d").date()

        # Iterate for every asset.
        assets = self.browse(cr, uid, ids, context=context)
        for asset in assets:

            # Error if asset and period are from different companies.
            if asset.company_id != period.company_id:
                template = _(u"Cannot depreciate asset {asset} on {period}. " \
                    u"This period is from a different company.")
                raise osv.except_osv(
                    _(u"Error!"),
                    template.format(asset=asset.name, period=period.name)
                )

            # If the depreciation has not begun, skip the asset.
            if period.date_stop < asset.service_date:
                continue

            sequence = asset.depreciation_line_sequence
            vals = {}

            if asset.last_depreciation_period:
                last_period_end = asset.last_depreciation_period.date_stop
            else:
                split_service_date = asset.service_date.split('-')
                year, month = [int(x) for x in split_service_date[0:2]]
                last_period_end = date(year, month, 1) - relativedelta(days=1)

            # Before the actual depreciation, we must create the missing lines
            miss_domain = [
                ('date_start', '>', last_period_end),
                ('date_stop', '<', period.date_start),
                ('special', '=', False),
            ]
            miss_id = period_osv.search(cr, uid, miss_domain, context=context)
            miss_periods = period_osv.browse(cr, uid, miss_id, context=context)
            for miss_period in miss_periods:
                sequence += 1
                missed_period_vals = {
                    'name': _(u"Missed Depreciation"),
                    'sequence': sequence,
                    'asset_id': asset.id,
                    'amount': 0,
                    'depreciable_amount': asset.depreciable_amount,
                    'remaining_value': asset.net_book_value,
                    'depreciated_value': asset.depreciation_total,
                    'depreciation_date': today_str,
                    'depreciation_period': miss_period.id,
                }
                line_osv.create(cr, uid, missed_period_vals, context=context)

            # Generate up to two lines: depreciation and/or correction.
            depr_iter = self._generate_depreciations(
                asset, comp_period, vals=vals, end_date=end_date
            )
            for depreciation in depr_iter:

                sequence += 1
                amount = depreciation.get('amount', False)
                if not amount:
                    continue

                if depreciation['type'] == 'correction':
                    type_str = _(u"Correction")
                else:
                    type_str = _(u"Depreciation")

                if disposal is None:
                    mv_ref = type_str
                    ml_ref = u"{0} / {1}".format(asset.name, period.name)
                else:
                    mv_ref = _(u"Disposal {type}").format(type=type_str)
                    ml_ref = u"{0}".format(asset.name)

                mv_name = asset.name
                ml_name_pattern = _(u"{type} of Asset {ref}")
                ml_name = ml_name_pattern.format(type=mv_ref, ref=ml_ref)
                journal = asset.category_id.journal_id.id
                stocks_acc = asset.category_id.account_depreciation_id
                expense_acc = asset.category_id.account_expense_depreciation_id

                move_id = self._create_move_lines(
                    cr, uid, asset, period, journal, stocks_acc, expense_acc,
                    amount, mv_ref=mv_ref, mv_name=mv_name, ml_ref=ml_ref,
                    ml_name=ml_name, date_=today_str, context=context
                )

                # Create the depreciation line.
                depreciation_vals = {
                    'name': mv_ref,
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

            # Update the asset's values after the depreciation.
            vals['last_depreciation_period'] = period_id
            vals['depreciation_line_sequence'] = sequence
            self.write(cr, uid, asset.id, vals, context=context)

        # Refresh the projected depreciations board.
        if not disposal:
            self.compute_depreciation_board(cr, uid, ids, context=context)

    def dispose(
        self, cr, uid, ids, action_date, period_id, reason, value, context=None
    ):
        """Perform the disposal of assets"""

        period_osv = self.pool.get('account.period')
        period = period_osv.browse(cr, uid, period_id, context=context)
        today_str = datetime.strftime(date.today(), '%Y-%m-%d')

        # Depreciate the assets for the period
        self.depreciate(
            cr, uid, ids, period_id, disposal=action_date, context=context
        )

        # Iterate for every asset.
        assets = self.browse(cr, uid, ids, context=context)
        for asset in assets:

            gross_ref = _(u"Gross Value Disposal")
            depr_ref = _(u"Depreciation Value Disposal")
            mv_name = asset.name
            ml_ref = u"{0} / {1}".format(asset.name, period.name)
            ml_name = _(u"Disposal of Asset {ref}").format(ref=ml_ref)
            journal = asset.category_id.disposal_journal_id.id
            asset_acc = asset.category_id.account_asset_id
            disposal_acc = asset.category_id.account_disposal_id
            stocks_acc = asset.category_id.account_depreciation_id
            gross_amount = asset.adjusted_gross_value
            depr_amount = - asset.depreciation_total

            self._create_move_lines(
                cr, uid, asset, period, journal, asset_acc, disposal_acc,
                gross_amount, mv_ref=gross_ref, mv_name=mv_name, ml_ref=ml_ref,
                ml_name=ml_name, date_=today_str, context=context
            )
            self._create_move_lines(
                cr, uid, asset, period, journal, stocks_acc, disposal_acc,
                depr_amount, mv_ref=depr_ref, mv_name=mv_name, ml_ref=ml_ref,
                ml_name=ml_name, date_=today_str, context=context
            )

            # Update the asset's values for the disposal.
            asset_vals = {
                'state': 'close',
                'disposal_date': action_date,
                'disposal_reason': reason,
                'disposal_value': value if reason == 'sold' else 0,
                'disposal_period': period_id,
                'gross_disposal': - gross_amount,
                'depreciation_disposal': depr_amount,
            }
            self.write(cr, uid, [asset.id], asset_vals, context=context)

        # Delete the projected depreciation board.
        self.compute_depreciation_board(cr, uid, ids, context=context)


class account_asset_values_history(osv.Model):
    """Store the history of a manual change on a value from an open asset."""

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
    """Extends account.asset.depreciation.line, from account_asset."""
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
    """Represent an invoice associated with an asset."""

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
