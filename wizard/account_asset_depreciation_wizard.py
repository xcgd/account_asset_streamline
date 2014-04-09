from openerp.osv import osv, fields
from openerp.tools.translate import _


class account_asset_depreciation_wizard(osv.TransientModel):
    _name = 'account.asset.depreciation.wizard'

    def _get_asset_domain(self, cr, uid, period_id, context=None):

        if period_id is False:
            return [('id', 'in', [])]

        period_osv = self.pool.get('account.period')
        period = period_osv.browse(cr, uid, period_id, context)
        period_start = period.date_start
        period_stop = period.date_stop

        return [
            ('state', '=', 'open'),
            ('service_date', '<=', period_stop),
            '|',
                ('last_depreciation_period.date_stop', '<', period_start),
                ('last_depreciation_period', '=', False),
            '|',
                ('net_book_value', '!=', 0),
                '|',
                    '&',
                        ('method_time', '=', 'end'),
                        ('method_end', '>=', period_start),
                    '&',
                        ('method_time', '=', 'number'),
                        ('method_end_fct', '>=', period_start),
        ]

    def _get_default_period(self, cr, uid, context=None):
        asset_osv = self.pool.get('account.asset.asset')
        period_osv = self.pool.get('account.period')
        period_id = asset_osv._get_period(cr, uid, context=context)
        period = period_osv.browse(cr, uid, period_id, context=context)
        if period.state == 'done':
            return False
        else:
            return period_id

    _auto_values = [
        ('all', "Select all depreciable assets"),
        ('none', "Clear selection"),
    ]

    _columns = {
        'asset_ids': fields.many2many(
            'account.asset.asset',
            'depreciation_wizard_asset_rel',
            'wizard_id',
            'asset_id',
            string=u"Assets",
            required=True,
        ),
        'period_id': fields.many2one(
            'account.period',
            u"Period",
            required=True,
        ),
        'auto': fields.selection(
            _auto_values,
            u"Auto selection",
            translate=True,
        )
    }

    _defaults = {
        'period_id': _get_default_period,
        'auto': False,
    }

    def onchange_period(self, cr, uid, ids, period_id, context=None):

        domain = self._get_asset_domain(cr, uid, period_id, context=context)
        asset_osv = self.pool.get('account.asset.asset')
        asset_ids = asset_osv.search(cr, uid, domain, context=context)
        return {
            'domain': {'asset_ids': domain},
            'value': {'asset_ids': asset_ids}
        }

    def auto_select(self, cr, uid, ids, auto, period_id, context=None):

        res = {'auto': False}
        if auto == 'none':
            res['asset_ids'] = []
        elif auto == 'all':
            asset_osv = self.pool.get('account.asset.asset')
            dom = self._get_asset_domain(cr, uid, period_id, context=context)
            res['asset_ids'] = asset_osv.search(cr, uid, dom, context=context)
        return {'value': res}

    def depreciate_assets(self, cr, uid, ids, context=None):

        asset_osv = self.pool.get('account.asset.asset')
        wizards = self.browse(cr, uid, ids, context=context)

        for wizard in wizards:
            period = wizard.period_id
            if(period.state == 'done'):
                pattern = _(u"The period {0} is closed.")
                raise osv.except_osv(_(u"Error!"), pattern.format(period.name))
            unchecked_ids = [asset.id for asset in wizard.asset_ids]
            domain = self._get_asset_domain(cr, uid, period.id, context)
            domain.append(('id', 'in', unchecked_ids))
            assets = asset_osv.search(cr, uid, domain, context=context)
            asset_osv.depreciate(cr, uid, assets, period.id, context=context)
