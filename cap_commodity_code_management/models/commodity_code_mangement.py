from odoo import fields, models, api, _
from odoo.exceptions import UserError, ValidationError

class CommodityCodeManagement(models.Model):
   _inherit = ['mail.thread','mail.activity.mixin'] 

   _name = 'commodity.code.management' 

   name = fields.Char('Name', compute='_compute_commodity_code', readonly=True, tracking=True, store=True)

   description = fields.Text(string='Description', tracking=True)

   notes = fields.Text(string='Notes', tracking=True)

   buyer = fields.Many2one('res.users','Buyer', tracking=True)

   write_date = fields.Datetime(string='Last Updated on')

   user_id = fields.Many2one(
      'res.users', string='Last Updated by', index=True, tracking=True,
       default=lambda self: self.env.user, check_company=True
       )

   commodity_parent = fields.Many2one('commodity.code.segment', 'Commodity Parent', tracking=True, required=True)

   commodity_sub = fields.Many2one('commodity.code.segment', 'Commodity Sub', tracking=True, required=True)

   commodity_low = fields.Many2one('commodity.code.segment', 'Commodity Low', tracking=True, required=True)
   
   @api.depends('commodity_parent', 'commodity_sub', 'commodity_low')
   def _compute_commodity_code(self):
      # record = env['commodity.code.management'].search([])
      # raise UserError(record)
  
      for rec in self:
         if rec.commodity_sub.name == '#' and rec.commodity_low.name !='#' and rec.commodity_low.name != False:
            raise UserError('Cannot have parent and low without sub')
         elif rec.commodity_parent and rec.commodity_sub and rec.commodity_low:  
            rec.name = f'{str(rec.commodity_parent.name)}{str(rec.commodity_sub.name)}{str(rec.commodity_low.name)}'
         elif self.commodity_parent and self.commodity_sub:
            rec.name = f'{str(rec.commodity_parent.name)}{str(rec.commodity_sub.name)}'
         elif self.commodity_parent:
            rec.name = f'{str(rec.commodity_parent.name)}'
         else:
            rec.name = ' '


   _sql_constraints = [
        ('code__uniq', 'unique (commodity_parent, commodity_sub, commodity_low)', 'The commodity code must be unique')
    ]
