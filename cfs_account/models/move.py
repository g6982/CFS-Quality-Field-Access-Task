from odoo import fields, models, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class AccountMove(models.Model):
    _inherit = "account.move"

    # EOI-522: Register Payment button appear
    hide_register_payment_button = fields.Boolean(string='Hide Button',compute="_compute_hide_register_payment_button")

    def _check_analytic_account_create(self, vals=None):
        """EOI524 throw an error if more than one analytic account is used
        create a list of accounts and throw an error if there is more than one analytic
        this is different for create because there is a different structure to the data passed
        """
        invoice_line_ids = vals.get("invoice_line_ids")
        analytic_account_id = None
        errors = ""
        values = {}
        if invoice_line_ids:
            for line in invoice_line_ids:
                # find the dictionary containing the values
                for val in line:
                    if type(val) is dict:
                        values = val
                line_analytic_account_id = values.get("analytic_account_id")
                line_analytic_account = self.env["account.analytic.account"].browse(line_analytic_account_id)
                if line_analytic_account:
                    line_analytic_account_name = line_analytic_account.name
                else:
                    line_analytic_account_name = "Unknown Analytic Account"
                # if there is no analytic account yet, we'll set the current line as the analytic account to use
                if not analytic_account_id:
                    analytic_account_id = line_analytic_account_id
                    analytic_account_name = line_analytic_account_name
                    continue
                # if the analytic account doesn't equal the analytic_account_id for the line
                if analytic_account_id != line_analytic_account_id:
                    errors += f'{values.get("name", "Unknown Product")} uses {line_analytic_account_name} instead of {analytic_account_name}.  Please ensure that all lines use the same analytic account.\n'
            # If there are errors, display them to the user
            if errors:
                raise UserError(errors)
        return vals

    def _check_analytic_account_write(self, vals=None):
        """EOI524 throw an error if more than one analytic account is used
        create a list of accounts and throw an error if there is more than one analytic
        this is different for write because there is a different structure to the data passed
        """
        analytic_account_id = None
        errors = ""
        for rec in self:
            for analytic_line in rec.invoice_line_ids:
                if 'analytic_account_id' in analytic_line:
                    line_analytic = analytic_line.analytic_account_id
                    analytic_line_id = line_analytic.id
                    analytic_line_name = line_analytic.name
                if not analytic_account_id:
                    analytic_account_id = analytic_line_id
                    analytic_account_name = analytic_line_name
                    continue
                # EOI-556: Removed if statements to prevent raise user error
                # if the analytic account doesn't equal the analytic_account_id for the line
                # if analytic_account_id != analytic_line_id:
                #     errors += f'{analytic_line.product_id.name} uses {analytic_line_name} instead of {analytic_account_name}. Please ensure that all lines use the same analytic account.\n'
            # If there are errors, display them to the user
            # if errors:
            #     raise UserError(errors)
        return vals

    @api.model
    def create(self, vals):
        """EOI524  Check line items for dif analytic account
        """
        vals = self._check_analytic_account_create(vals=vals)
        result = super().create(vals)
        return result

    def write(self, vals):
        """EOI524  Check line items for dif analytic account
        """

        res = super().write(vals)
        vals = self._check_analytic_account_write(vals=vals)
        return res

    @api.depends('state')
    def _compute_hide_register_payment_button(self):
        """EOI522 - compute when the register payment button should be shown
        """
        for rec in self:
            # assume it shows
            val = False
            # If the bill is not posted, btn should never show
            if rec.state != 'posted':
                val = True 
            # if the bill is in payment or paid, it should not show
            elif rec.payment_state in ('in_payment','paid'):
                val = True
            # EOI-508: Adding domain to the Register Payment button
            elif rec.require_approval == True:
                val = True
            # If the bill is not approved, btn should never show
            elif rec.is_approved == False:
                val = True 
            # If the bill is of move type entry, btn should never show 
            elif rec.move_type == "entry":
                val = True 
            # If the bill passes all scenerios, then it will show
            rec.hide_register_payment_button = val


    # EOI-392: Add default Journal on Register Payment wizard
    def action_register_payment(self):
        res = super(AccountMove, self).action_register_payment()
        # EOI-508: Prevent any singleton error 'for rec in self'
        
        default_journal = self.env["account.journal"].search([("payment_default", "=", True)])
        if default_journal:
            res["context"]["default_journal_id"] = default_journal.id
        # EOI-491: Added check to make sure all bill's should be paid field are 'True'
        # EOI-508: List view functionality, needs to check record for all passing criteria
        # ma_req = rec.multi_approval_ids.filtered(lambda request: request.state == 'Approved')

        # EOI-707: Uncommented until 3-way/2-way match is 100% operational
        # should_not_pay = self.filtered(lambda bill: bill.release_to_pay_manual != 'yes' )
        # if should_not_pay:
        #     raise UserError("Cannot register payment. Need to verify 2-way and/or 3-way match.")
        return res

    def determine_bill_approvers(self, multi_approval_request,analytic_account,service_total,threshold=50000):
        """Determine approvers that should appear on account.move record
            EOI-833

        Args:
            multi_approval_request (record): record of type multi.approval that is being worked on
            analytic_account (record): analytic.account record for determining budget
            service_total (float): total of all serviceable items on the puchase.order or account.move record
            threshold (int): Threshold amount where the second level is requested
                default: 50000

        Returns: Tuple of 
            (
                approval_list - list of dictionaries for insert into multi.approval.line records attached to multi.approval record 
                    {
                        'user_ids': ids for approvers at level,
                        'name': name of multi.approval template to be user,
                        'min_approval' (int): number of required approvers to approve at level,
                        'level' (int): level to be used for multi.approval.line record,
                        'sequence' (int): sequence for line to appear if at same level,
                        'require_opt' (String): TODO seems to always be Optional,
                        'user_id' (int): id of user to approve TODO not sure if needed,
                        'approval_id' (int): id of multi.approval object,
                        'status' (string): status of the created line determining the activities of the assigned approver(s)
                            new
                            pending
                            approved
                            refused
                            cancel
                    },
                chatter_list - list of string chatter messages to attach to the record
            ) 
        """
        approval_list = []
        chatter_list = []
        approver_level = 10
        linked_purchase_order = self.linked_purchase_id
        if linked_purchase_order:
            # get requester from po
            # raise user error if not found
            approver = linked_purchase_order.requester_id
            if not approver:
                _logger.debug(f'No requester was found for {linked_purchase_order}')
                raise UserError(f'The requester of the linked purchase order was not found. Please contact the administrator')
            chatter_list.append(f'A linked purchase order was found so {approver.name} was requested for level {approver_level}')
        else:
            # if no linked purchase order, use the budget owner
            # raise user error if no budget owner
            approver = analytic_account.user_id
            if not approver:
                _logger.debug(f'The budget owner was not received for {analytic_account}')
                raise UserError(f'This budget does not have a budget owner. Please check the responsible ID of the analytic account.')
            chatter_list.append(f'No linked purchase order was found so {approver.name} was requested for level {approver_level}')
        approver_id = approver.id
        approval_list.append({
            'user_ids': [(4, approver_id, 0)],
            'name': 'BudgetOwnername',
            'everyone_approves': True,
            'min_approval': 1,
            'level': approver_level,
            'sequence':10,
            'require_opt': 'Optional',
            'user_id': approver_id,
            'approval_id': multi_approval_request.id,
            'status': 'new'
        })
        # If the total cost of the serviceable items is greater than the CFO threshold then also add the CFO as another level
        if service_total > threshold:
            # Determine cfo only needed if the service total is over the threshold
            cfo = self.env["ir.config_parameter"].sudo().get_param("cap_settings.cfs_cfo")
            try:
                cfo = int(cfo)
            except:
                raise UserError(f'Unable to convert cfs_cfo {cfo} to integer. Please check the value of CFO under Budget User Parameter in settings.')
            # Add CFO
            approval_list.append({
                'user_ids': [(4, cfo, 0)],
                'name': 'CFOname',
                'everyone_approves': True,
                'min_approval': 1,
                'level': 20,
                'sequence':20,
                'require_opt': 'Optional',
                'user_id': cfo,
                'approval_id': multi_approval_request.id,
                'status': 'new'
            })
        return approval_list, chatter_list

