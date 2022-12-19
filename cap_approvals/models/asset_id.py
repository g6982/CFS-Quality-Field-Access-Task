# -*- coding: utf-8 -*-
# EOI 735 adding asset id field
from odoo import api, fields, models

class AccountAsset(models.Model):
    _inherit = 'account.asset'

    asset_id = fields.Char(string='Asset ID')

    # EOI 793 adding asset_location field
    asset_location = fields.Char(string='Asset Location')