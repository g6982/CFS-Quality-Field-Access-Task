from odoo import fields, models, api
from odoo.exceptions import UserError

class ProductQualityCode(models.Model):
    _name = "product.quality.code"
    _description = "Quality Codes"

    name = fields.Char(string="Name", required=True)
  
    # ERPQ4-37: Override Create to prevent non-numerical quality clauses
    @api.model
    def create(self, vals):
        is_num = vals['name']
        names = []

        # If not numerical, this will throw a traceback, but instead we will throw a UserError
        try:
            check_num = int(is_num)
        except:
            raise UserError('Quality clauses can only be numerical')

        for qual_code in self.env['product.quality.code'].search([]):
            names.append(qual_code.name)

        # Checks if is a duplicate
        if str(check_num) in names:
            raise UserError('This quality clause already exists')

        return super(ProductQualityCode, self).create(vals)

    # ERPQ4-37: Override Write to prevent non-numerical quality clauses
    def write(self, vals):
        is_num = vals['name']
        names = []

        # If not numerical, this will throw a traceback, but instead we will throw a UserError
        try:
            check_num = int(is_num)
        except:
            raise UserError('Quality clauses can only be numerical')

        for qual_code in self.env['product.quality.code'].search([]):
            names.append(qual_code.name)

        # Checks if is a duplicate
        if str(check_num) in names:
            raise UserError('This quality clause already exists')

        return super(ProductQualityCode,self).write(vals)