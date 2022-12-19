from odoo import models, fields, api
from odoo.exceptions import UserError
from odoo.osv import expression

class AccountMove(models.Model):
    _inherit = 'account.analytic.account'

    user_id = fields.Many2one('res.users','Responsible') 
    show_in_budget_tab = fields.Boolean('Show in Budget Tab')

    # EOI 786 Improve search functionality for Analytic Accounts, search by parent or reference code
    @api.model
    def _name_search(self, name='', args=None, operator='ilike', limit=100):
        """EOI583 - Analytic account should also be searchable by parent

        Args:
            name (str, optional): _description_. Defaults to ''.
            args (_type_, optional): _description_. Defaults to None.
            operator (str, optional): _description_. Defaults to 'ilike'.
            limit (int, optional): _description_. Defaults to 100.
        """
        args = [('complete_name', operator, name)] + args
        additionalargs = [('code', operator, name)]

        return super()._search(expression.OR([args, additionalargs]), offset=0, limit=None, order=None, count=False, access_rights_uid=None)