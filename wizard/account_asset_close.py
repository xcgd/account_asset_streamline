# -*- encoding: utf-8 -*-

import time
from openerp.osv import fields, osv
import openerp.addons.decimal_precision as dp


class asset_close(osv.TransientModel):
    """Prompt the user to select a reason for the closure of an asset."""

    _name = 'asset.close'
    _description = 'Close Asset'

    _columns = {
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
        'currency_id': fields.many2one(
            'res.currency',
            'Currency',
            readonly=True,
        ),
    }

    def modify(self, cr, uid, ids, context=None):
        """Close the asset."""

        if not context:
            context = {}

        asset_obj = self.pool.get('account.asset.asset')
        asset_id = context.get('active_id', False)
        data = self.browse(cr, uid, ids[0], context=context)

        asset_val = {
            'state': 'close',
            'disposal_date': time.strftime('%Y-%m-%d'),
            'disposal_reason': data.disposal_reason,
        }
        if asset_val['disposal_reason'] != 'sold':
            asset_val['disposal_value'] = 0
        else:
            asset_val['disposal_value'] = data.disposal_value

        asset_obj.write(cr, uid, [asset_id], asset_val, context=context)

        return {'type': 'ir.actions.act_window_close'}

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
