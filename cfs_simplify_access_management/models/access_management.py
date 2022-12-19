# -*- coding: utf-8 -*-
from odoo import fields, models, api, _
from odoo.exceptions import UserError

class AccessManagement(models.Model):
    _inherit = 'access.management'

    #EOI 806
    is_ap_or_tameka = fields.Boolean(string='AP/Tameka')

    # EOI-689: Create a field identifies which access group are buyers
    check_buyer = fields.Boolean(string="Check Buyer", help="Enabling this will consider all users in this studio role as Buyers", default=False)

    # ERPQ4-316: Create a field that identifies whicha access groups are allowed access to Quality Clauses Field
    # check_quality = feilds.Boolean(string="Check Quality", help="Enabling this will grant all users in this studio role access to quality specific fields", default=False)
    cap_check_quality = fields.Boolean(string='Check Quality Access', 
                                        help="Enabling this will grant all users in this studio role access to quality specific fields", 
                                        default=False)

