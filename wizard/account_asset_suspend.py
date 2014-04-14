# -*- encoding: utf-8 -*-

import time
from openerp.osv import fields, osv


class asset_suspend(osv.TransientModel):
    """Prompt the user to select a reason for the suspension of an asset."""

    _name = 'asset.suspend'
    _description = 'Suspend Asset'

    _columns = {
        'suspension_reason': fields.char(
            u'Suspension Reason',
            size=256,
        ),
    }

    def modify(self, cr, uid, ids, context=None):
        """Suspend the asset."""

        if not context:
            context = {}

        asset_obj = self.pool.get('account.asset.asset')
        asset_id = context.get('active_id', False)
        data = self.browse(cr, uid, ids[0], context=context)

        asset_val = {
            'state': 'suspended',
            'suspension_reason': data.suspension_reason,
            'suspension_date': time.strftime('%Y-%m-%d')
        }
        asset_obj.write(cr, uid, [asset_id], asset_val, context=context)

        return {'type': 'ir.actions.act_window_close'}

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
