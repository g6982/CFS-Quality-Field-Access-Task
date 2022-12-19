from odoo import models, fields, api
from odoo.exceptions import UserError
import logging
_logger = logging.getLogger(__name__)

#EOI 226/227 - Add fields analytics accounts and update read_groups
class CrossoveredBudgetLines(models.Model):
    _inherit = 'crossovered.budget.lines'

    draft_burden = fields.Monetary(string='Draft Burden', group_operator='sum',
                                help="Amount that is spent on a draft purchase order")
    approved_burden = fields.Monetary(string='Approved Burden', group_operator='sum',
                                   help="Amount that is spent on an approved purchase order")
    released_burden = fields.Monetary(string='Released Burden', group_operator='sum',
                                   help="Amount that is spent on a released purchase order")
    closed_burden = fields.Monetary(string='Closed Burden', group_operator='sum',
                                 help="Amount that is spent on a closed purchase order")
    total_burden = fields.Monetary(string='Total Burden', group_operator='sum',
                                help="The total amount that is spent on all stages of a purchase order")
    abs_practical_amount = fields.Monetary(string='ABS Practical Amount', 
                                           help="Amount really earned/spent.")
    abs_theoritical_amount = fields.Monetary(string='ABS Theoretical Amount', 
                                             help="Amount you are supposed to have earned/spent at this date.")
    abs_planned_amount = fields.Monetary(string='ABS Planned Amount', group_operator='sum',
                                         help="Amount you plan to earn/spend. Record a positive amount if it is a revenue and a negative amount if it is a cost.")
    user_id = fields.Many2one('res.users', string="Owner")

    # EOI 716 Analytic Account Chatter
########### Using Write for chatter trace
    def write(self, vals):
        # _logger.info(f'\n\n\n\n{self}\n{vals}\n{test}\n\n\n\n')
        parent=self.analytic_account_id.id
        analyticaccount = self.env['account.analytic.account'].search([('id', '=', parent)])

        trackingmsg = ''

        if vals.get('crossovered_budget_id'):
            test = self.env['crossovered.budget'].browse(vals.get('crossovered_budget_id')).name
            trackingmsg += f'Old name : {self.name} --> {str(test)} <br/>'
        
        if vals.get('date_from'):
            datefrom = dateto = str(vals.get('date_from'))
            trackingmsg += f'Date From : {self.date_from} --> {datefrom} <br/>'

        if vals.get('date_to'):
            dateto = str(vals.get('date_to'))
            trackingmsg += f'Date To: {self.date_to} --> {dateto} <br/>'

        if vals.get('planned_amount'):
            plannedamt = str(vals.get('planned_amount'))
            trackingmsg += f'Old Planned Amount : ${self.planned_amount} --> ${plannedamt} <br/>'
        analyticaccount.message_post(body=trackingmsg.rstrip('<br/>'))
        return super().write(vals)

    # EOI 716 Analytic Account Chatter. This create is only used to log if there is a new line created
    @api.model
    def create(self, vals):
        res = super().create(vals)
        # _logger.info(f'\n\n\n\n{self}\n{vals}\n\n\n\n')

        if vals.get('analytic_account_id'):
            self.env['account.analytic.account'].browse(vals.get('analytic_account_id')).message_post(body='New Budget Line Created')

        return res
      
    @api.onchange('planned_amount')
    def onchange_base_amts(self):
        self.abs_planned_amount = abs(self.planned_amount)   
      
    @api.model
    def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        ###################################
        budgets = self.env['crossovered.budget.lines'].search([])
        for budget in budgets:
            if abs(budget.abs_practical_amount) != abs(budget.practical_amount):
                budget.abs_practical_amount = abs(budget.practical_amount)
            if abs(budget.abs_theoritical_amount) != abs(budget.theoritical_amount):
                budget.abs_theoritical_amount = abs(budget.theoritical_amount)
            budget.total_burden = budget.draft_burden + budget.approved_burden + budget.released_burden + budget.closed_burden + budget.abs_practical_amount
            
        fields_list = {'practical_amount', 'theoritical_amount', 'percentage', 'bs_theoritical_amount', 'abs_practical_amount'}
        ###################################
        
        def truncate_aggr(field):
            field_no_aggr = field.split(':', 1)[0]
            if field_no_aggr in fields_list:
                return field_no_aggr
            return field
        fields = {truncate_aggr(field) for field in fields}

        result = super(CrossoveredBudgetLines, self).read_group(
            domain, list(fields - fields_list), groupby, offset=offset,
            limit=limit, orderby=orderby, lazy=lazy)

        if fields & fields_list:
            for group_line in result:
                ###################################
                if 'abs_practical_amount' in fields:
                    group_line['abs_practical_amount'] = 0
                if 'abs_theoritical_amount' in fields:
                    group_line['abs_theoritical_amount'] = 0
                ###################################
                if 'practical_amount' in fields:
                    group_line['practical_amount'] = 0
                if 'theoritical_amount' in fields:
                    group_line['theoritical_amount'] = 0
                if 'percentage' in fields:
                    group_line['percentage'] = 0
                    group_line['practical_amount'] = 0
                    group_line['theoritical_amount'] = 0

                domain = group_line.get('__domain') or domain
                all_budget_lines_that_compose_group = self.search(domain)

                for budget_line_of_group in all_budget_lines_that_compose_group:
                    ###################################
                    if 'abs_practical_amount' in fields:
                        group_line['abs_practical_amount'] += budget_line_of_group.abs_practical_amount
                    
                    if 'abs_theoritical_amount' in fields:
                        group_line['abs_theoritical_amount'] += budget_line_of_group.abs_theoritical_amount
                    ###################################
                    if 'practical_amount' in fields or 'percentage' in fields:
                        group_line['practical_amount'] += budget_line_of_group.practical_amount

                    if 'theoritical_amount' in fields or 'percentage' in fields:
                        group_line['theoritical_amount'] += budget_line_of_group.theoritical_amount

                    if 'percentage' in fields:
                        if group_line['theoritical_amount']:
                            group_line['percentage'] = float(
                                (group_line['practical_amount'] or 0.0) / group_line['theoritical_amount'])
        return result