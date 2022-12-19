# -*- coding: utf-8 -*-
from odoo import models, fields, api
from random import randint
from odoo.exceptions import UserError
from odoo.osv import expression

class ProductTags(models.Model):
    _name = "product.tag"
    _description = "Buyer Category"

    # Show the categories in order by the parent category first and then by the name of the category
    _order = 'parent_category_name asc, name' 

    def _get_default_color(self):
        return randint(1, 11)

    # TODO `buyer` needs a domain to show only Buyer group members. This must be updated after permissions are implemented.
    buyer_id = fields.Many2one("res.users", string="Buyer")
    active = fields.Boolean(string="Active", default=True, help="The active field allows you to hide the category without removing it.")
    color_index = fields.Integer(string="Color Index", default=_get_default_color)
    name = fields.Char(string="Category",index=True, required=True)
    parent_category = fields.Many2one('product.tag', string='Parent Category', index=True, ondelete='cascade')
    approved_vendors = fields.Many2many("res.partner", string="Approved Vendors")
    default_purchase_account = fields.Many2one("account.account", string="Default Purchase Account")
    # EOI-782 order records in alphabetic way by parent_category
    parent_category_name = fields.Char(string='Parent Category Name', default='',compute='_get_parent_name',store=True)

    @api.depends('parent_category')
    def _get_parent_name(self):
        for record in self:
            if record.parent_category:
                record.parent_category_name = record.parent_category.name 


    
    def name_get(self):
        if self._context.get('partner_category_display') == 'short':
            return super(ProductTags, self).name_get()
        res = []
        for category in self:
            names = []
            current = category
            while current:
                names.append(current.name)
                current = current.parent_category
            # EOI-782: add the names for parent categories in the display name 
            res.append((category.id, ' / '.join(names[::-1])))
        return res
    

    # EOI-692: make searchable by parent name too
    @api.model
    def _name_search(self, name, args=None, operator='ilike', limit=100, name_get_uid=None):
        args = args or []
        domain = []
        if name:
            domain = ['|', ('name', operator, name),('parent_category.name',operator,name)]
        return self._search(expression.AND([domain, args]), limit=limit, access_rights_uid=name_get_uid)

