from openerp.osv import osv, fields


class account_asset_depreciation_wizard(osv.TransientModel):
    _name = 'account.asset.depreciation.wizard'

    def _get_asset_ids(self, cr, uid, context=None):

        asset_osv = self.pool.get('account.asset.asset')
        period_id = asset_osv._get_period(cr, uid, context)
        period_osv = self.pool.get('account.period')
        period = period_osv.browse(cr, uid, period_id, context)
        period_start = period.date_start
        period_stop = period.date_stop

        domain = [
            ('state', '=', 'open'),
            ('service_date', '<=', period_stop),
            '|',
                ('last_depreciation_period', '!=', period_id),
                ('last_depreciation_period', '=', False),
            '&',
                ('net_book_value', '!=', 0),
                '|',
                    '&',
                        ('method_time', '=', 'end'),
                        ('method_end', '>=', period_start),
                    '&',
                        ('method_time', '=', 'number'),
                        ('method_end_fct', '>=', period_start),
        ]

        asset_ids = asset_osv.search(cr, uid, domain, context=context)
        return asset_ids

    _columns = {
        'asset_ids': fields.many2many(
            'account.asset.asset',
            'depreciation_wizard_asset_rel',
            'wizard_id',
            'asset_id',
            string=u"Assets",
        )
    }

    _defaults = {
        'asset_ids': _get_asset_ids
    }

    def onchange_assets(self, cr, uid, ids, context=None):

        asset_ids = self._get_asset_ids(cr, uid, context=context)
        asset_ids_domain = [('id', 'in', asset_ids)]
        domain = {'asset_ids': asset_ids_domain}
        return {'values': {}, 'domain': domain}

    def depreciate_assets(self, cr, uid, ids, context=None):

        asset_osv = self.pool.get('account.asset.asset')
        asset_read = self.read(cr, uid, ids, ['asset_ids'], context=context)
        unchecked_asset_ids = set(asset_read[0]['asset_ids'])
        valid_asset_ids = set(self._get_asset_ids(cr, uid, context))
        asset_ids = list(unchecked_asset_ids & valid_asset_ids)
        period_id = asset_osv._get_period(cr, uid, context=context)
        asset_osv.depreciate(cr, uid, asset_ids, period_id, context=context)
