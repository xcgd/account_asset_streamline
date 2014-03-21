# -*- encoding: utf-8 -*-

import time
from openerp.osv import fields, osv


class asset_modify_values(osv.TransientModel):

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
        'adjustment_amount': fields.float('Adjustment'),
        'note': fields.text('Notes'),
    }

    def modify(self, cr, uid, ids, context=None):

        if not context:
            context = {}
        asset_val = {}

        asset_obj = self.pool.get('account.asset.asset')
        asset_id = context.get('active_id', False)
        asset = asset_obj.browse(cr, uid, asset_id, context=context)
        data = self.browse(cr, uid, ids[0], context=context)

        adjusted_value = data.adjusted_value
        try:
            old_value = getattr(asset, adjusted_value)
            new_value = old_value + data.adjustment_amount
            asset_val[adjusted_value] = new_value
        except NameError:
            pass

        asset_obj.write(cr, uid, [asset_id], asset_val, context=context)
        return {'type': 'ir.actions.act_window_close'}

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
