# -*- encoding: utf-8 -*-

from openerp.osv import fields, osv
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
        'service_date': fields.related(
            'account.asset.asset',
            'service_date',
            string='Service Date',
            type='date',
            readonly=True
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
        'disposal_period': fields.many2one(
            'account.period',
            'Disposal Period',
            required=True,
        ),
        'currency_id': fields.many2one(
            'res.currency',
            'Currency',
            readonly=True,
        ),
    }

    _defaults = {
        'disposal_period': _get_default_period,
    }

    def modify(self, cr, uid, ids, context=None):
        """Close the asset."""

        if not context:
            context = {}

        asset_obj = self.pool.get('account.asset.asset')
        asset_id = context.get('active_id', False)
        data = self.browse(cr, uid, ids[0], context=context)

        asset_obj.dispose(
            cr, uid, [asset_id], data.disposal_period.id, data.disposal_reason,
            value=data.disposal_value,
            context=context
        )

        return {'type': 'ir.actions.act_window_close'}

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
