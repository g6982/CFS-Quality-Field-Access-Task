from odoo import fields, models, api, _
from odoo.exceptions import UserError

class CommoditySegment(models.Model):
   _name = 'commodity.code.segment' 
   
   name = fields.Char(string='Name', readonly=False, required=True) #False for now, might make read only later

   commodity_segment_type = fields.Selection([
   ('parent', 'Parent'),
   ('sub_low', 'Sub Low'),
   ])