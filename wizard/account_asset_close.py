# -*- encoding: utf-8 -*-

from openerp.osv import fields, osv
import time
from openerp.tools.translate import _
import openerp.addons.decimal_precision as dp


class asset_close(osv.TransientModel):
    """Prompt the user to select a reason for the closure of an asset."""

    _name = 'asset.close'
    _description = 'Close Asset'

    def _get_default_period(self, cr, uid, context=None):
        """Return the current period as default value for the period field."""
        asset_osv = self.pool.get('account.asset.asset')
        period_osv = self.pool.get('account.period')
        period_id = asset_osv._get_period(cr, uid, context=context)
        period = period_osv.browse(cr, uid, period_id, context=context)
        if period.state == 'done':
            return False
        else:
            return period_id

    _columns = {
        'asset_id': fields.many2one(
            'account.asset.asset',
            'Asset',
            required=True,
            readonly=True,
        ),
        'currency_id': fields.many2one(
            'res.currency',
            'Currency',
            readonly=True,
        ),
        'disposal_reason': fields.selection(
            [
                ('scrapped', u"Scrapped"),
                ('sold', u"Sold"),
                ('stolen', u"Stolen"),
                ('destroyed', u"Destroyed")
            ],
            u'Disposal Reason',
            size=256,
            translate=True,
            required=True,
        ),
        'disposal_value': fields.integer(
            u'Disposal Value',
            required=True,
            digits_compute=dp.get_precision('Account'),
        ),
        'action_date': fields.date(
            'Disposal Date',
            required=True,
        ),
        'period_id': fields.many2one(
            'account.period',
            'Disposal Period',
            required=True,
        ),
    }

    _defaults = {
        'action_date': lambda *a: time.strftime('%Y-%m-%d'),
    }

    def modify(self, cr, uid, ids, context=None):
        """Close the asset."""

        asset_osv = self.pool.get('account.asset.asset')
        data = self.browse(cr, uid, ids[0], context=context)

        asset_osv.dispose(
            cr, uid, [data.asset_id.id], data.action_date, data.period_id.id,
            data.disposal_reason, data.disposal_value, context=context
        )

        return {'type': 'ir.actions.act_window_close'}

    def onchange_date(
        self, cr, uid, id_, action_date, period_id, asset_id, context=None
    ):

        asset_osv = self.pool.get('account.asset.asset')
        period_osv = self.pool.get('account.period')
        value = {}
        warning = None

        asset = asset_osv.browse(cr, uid, asset_id, context=context)
        if action_date < asset.service_date:
            action_date = value['action_date'] = asset.service_date
            warning = {
                'title': _(u"Error!"),
                'message': _(u"Cannot dispose before the put-in-service date.")
            }

        period_domain = [
            ('state', '!=', 'done'),
            ('special', '!=', True),
            ('date_stop', '>=', action_date)
        ]
        period_ids = period_osv.search(cr, uid, period_domain, context=context)
        if period_ids:
            if period_id not in period_ids:
                value['period_id'] = period_ids[0]
        else:
            value['period_id'] = None

        return {
            'domain': {'period_id': period_domain},
            'value': value,
            'warning': warning,
        }

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
