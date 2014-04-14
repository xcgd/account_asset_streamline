# -*- encoding: utf-8 -*-

import time
from openerp.osv import fields, osv
from tools.translate import _
import openerp.addons.decimal_precision as dp


class asset_modify_values(osv.TransientModel):
    """Change the gross, salvage and manual depreciation values of an asset."""

    _name = 'asset.modify.values'
    _description = 'Modify Asset Values'

    _columns = {
        'name': fields.char('Reason', size=64, required=True),
        'adjusted_value': fields.selection(
            [
                ('additional_value', u"Gross Value Adjustment"),
                ('salvage_adjust', u"Salvage Value Adjustment"),
                ('depreciation_manual', u"Manual Depreciation"),
            ],
            'Adjusted Value'
        ),
        'currency_id': fields.many2one(
            'res.currency',
            'Currency',
            readonly=True,
        ),
        'adjustment_amount': fields.float(
            'Adjustment',
            digits_compute=dp.get_precision('Account'),
        ),
        'note': fields.text('Notes'),
    }

    def modify(self, cr, uid, ids, context=None):
        """Apply the modification to the selected value."""

        if not context:
            context = {}
        asset_val = {}

        asset_obj = self.pool.get('account.asset.asset')
        history_obj = self.pool.get('account.asset.values.history')
        asset_id = context.get('active_id', False)
        asset = asset_obj.browse(cr, uid, asset_id, context=context)
        data = self.browse(cr, uid, ids[0], context=context)

        adjusted_value = data.adjusted_value
        try:
            old_value = getattr(asset, adjusted_value)
            new_value = old_value + data.adjustment_amount
            asset_val[adjusted_value] = new_value
            asset_obj.write(cr, uid, [asset_id], asset_val, context=context)
        except AttributeError:
            raise osv.except_osv(_('Error!'), _('Invalid value type.'))

        history_vals = {
            'asset_id': asset_id,
            'name': data.name,
            'adjusted_value': data.adjusted_value,
            'new_value': new_value,
            'user_id': uid,
            'date': time.strftime('%Y-%m-%d'),
            'note': data.note,
        }
        history_obj.create(cr, uid, history_vals, context=context)

        asset_obj.compute_depreciation_board(cr, uid, [asset_id], context)
        return {'type': 'ir.actions.act_window_close'}

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
