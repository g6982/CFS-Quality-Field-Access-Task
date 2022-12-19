# -*- coding: utf-8 -*-
######################################################################################
#
#    Captivea LLC
#
#    This program is under the terms of the Odoo Proprietary License v1.0 (OPL-1)
#    It is forbidden to publish, distribute, sublicense, or sell copies of the Software
#    or modified copies of the Software.
#
#    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
#    IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
#    DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
#    ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#    DEALINGS IN THE SOFTWARE.
#
########################################################################################

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

import datetime
import logging
_logger = logging.getLogger(__name__)

class AccountMove(models.Model):
    _inherit = 'account.move'

    #EOI-804: Cleaned data for reflecting correct Account Type on Bill
    acc_type = fields.Selection(string="Account Type", related="partner_bank_id.type")
    should_be_paid = fields.Selection([
        ('yes', 'Yes'),
        ('no', 'No'),
        ('exception', 'Exception'),
    ])
    level_one_approval = fields.Boolean('First Approval')
    # EOI-349: Added compute field to update is_approved
    is_approved = fields.Boolean('Approved', compute="_compute_is_approved", default=False)
    # EOI-349: Computes product type
    # EOI-508: Replaced check_product_type logic for require_approval and it's compute function
    check_product_type = fields.Selection([
        ('service','Service'),
        ('empty','Empty'),
        ('receivable','Receivable')])
    # EOI-502: Use field as domain to see if there is an active approval
    approval_in_progress = fields.Boolean(string="Approval In Process", compute='_compute_approval_in_progress')

    # EOI-480: Gives total for services
    service_total = fields.Monetary(string='Services Total')
    on_hold = fields.Boolean('On Hold')
    bank_info_check = fields.Boolean('Bank Check', compute='_compute_bank_info_check')
    terms_due_date = fields.Date('Discounted Due Date', compute='_compute_terms_due_date')
    terms_amount = fields.Monetary('Discounted Amount', compute='_compute_terms_amount')
    # EOI-520: Removed the readonly field so users have a chance to prepare Bills before products are received
    linked_purchase_id = fields.Many2one('purchase.order', 'Linked Purchase Order')
    multi_approval_ids = fields.Many2many('multi.approval', string='Approvals', compute='_compute_multi_approval_ids')
    multi_approval_id_count = fields.Integer(string='Count Approvals', compute='_compute_multi_approval_id_count')

    # EOI-444 - Warn Vendor Bills w/ 0$
    warning_displayed = fields.Boolean('Warning Displayed')

    # EOI-508: Required Approval under special circumstances, replacement for check_product_type
    require_approval = fields.Boolean('Approval Required', compute='_compute_require_approval', default=False)

    #add required multi.approval fields that would be created by third party module
    x_has_request_approval = fields.Boolean('x_has_request_approval', copy=False)
    x_need_approval = fields.Boolean('x_need_approval', compute='_compute_x_need_approval')
    x_review_result = fields.Char('x_review_result', copy=False)
    
    # EOI 498 - Add linked to refund
    # Intentionally adding this field. There is functionality tied to the linked_purchase_id that does not make sense to decouple for this ticket.
    linked_purchase_refund_id = fields.Many2one('purchase.order', 'Linked Purchase Order')

    # EOI 738, Making the check for Bill Duplication stricter. No longer includes invoice date
    # Override base odoo function here.
    @api.constrains('ref', 'move_type', 'partner_id', 'journal_id', 'state')
    def _check_duplicate_supplier_reference(self):
        moves = self.filtered(lambda move: move.state == 'posted' and move.is_purchase_document() and move.ref)
        if not moves:
            return

        self.env["account.move"].flush([
            "ref", "move_type", "journal_id",
            "company_id", "partner_id", "commercial_partner_id",
        ])
        self.env["account.journal"].flush(["company_id"])
        self.env["res.partner"].flush(["commercial_partner_id"])

        # /!\ Computed stored fields are not yet inside the database.
        #AND (move.invoice_date is NULL OR move2.invoice_date = move.invoice_date)
        self._cr.execute('''
            SELECT move2.id
            FROM account_move move
            JOIN account_journal journal ON journal.id = move.journal_id
            JOIN res_partner partner ON partner.id = move.partner_id
            INNER JOIN account_move move2 ON
                move2.ref = move.ref
                AND move2.company_id = journal.company_id
                AND move2.commercial_partner_id = partner.commercial_partner_id
                AND move2.move_type = move.move_type
                AND move2.id != move.id
            WHERE move.id IN %s
        ''', [tuple(moves.ids)])
        duplicated_moves = self.browse([r[0] for r in self._cr.fetchall()])
        if duplicated_moves:
            raise ValidationError(_('Duplicated vendor reference detected. You probably encoded twice the same vendor bill/credit note:\n%s') % "\n".join(
                duplicated_moves.mapped(lambda m: "%(partner)s - %(ref)s" % {
                    'ref': m.ref,
                    'partner': m.partner_id.display_name,
                })
            ))

    @api.depends('multi_approval_ids')
    def _compute_approval_in_progress(self):
        for rec in self:
            one_in_progress = rec.multi_approval_ids.filtered(lambda ma_id: ma_id.state == 'Draft' or ma_id.state == 'Submitted')
            if one_in_progress:
                rec.approval_in_progress = True
            else:
                rec.approval_in_progress = False
    
    # EOI-508: Revised 3-way Service logic and 2-way logic, replaced _compute_check_product_type function
    # EOI-814: Change all cases of 'Exception' to 'No'. Improved/optimized logic
    # NOTE: This will NOT run on the list view, must include logic for Special Scenario in _compute_is_approved
    @api.depends('release_to_pay_manual','is_approved')
    def _compute_require_approval(self):
        for rec in self:

            # Find PO related to current Bill
            # todo logic for related po field always empty
            related_po = self.env['purchase.order'].search([('invoice_ids','in',rec.ids)])

            active_approval = rec.multi_approval_ids.filtered(lambda ma: ma.state == 'Draft' or ma.state == 'Submitted')

            # Check if product lines has a service
            # EOI-520: Specified to exclude Freight/Shipping
            line_has_service = rec.invoice_line_ids.filtered(lambda line: line.product_id.detailed_type == 'service' and line.product_id.categ_id.name != 'Freight / Shipping')

            # EOI-520: Check if quantity is 0 (Approved)
            line_has_service_zero_qty = rec.invoice_line_ids.filtered(lambda line: line.quantity == 0 and line.product_id.detailed_type == 'service' and line.product_id.categ_id.name != 'Freight / Shipping')

            # EOI-562: Check if line is Freight/Shipping
            line_has_freight = rec.invoice_line_ids.filtered(lambda line:line.product_id.categ_id.name == 'Freight / Shipping')
            
            # Products on Bill Lines
            prod_on_lines = rec.invoice_line_ids.product_id.filtered(lambda line:line.detailed_type in ['consu','product'])
            # Checks Products on Receipt if the id is on the Bill Lines and if the Receipt has been Validated
            receipts = related_po.picking_ids.filtered(lambda receipt:receipt.move_ids_without_package.filtered(lambda r_line:r_line.product_id.id in prod_on_lines.ids and r_line.quantity_done != 0) and receipt.state == 'done') 

            # EOI-520: Show Register Payment button if service was already approved (qty = 0) and was 3-way matched
            # Special scenario that happens when Service is approved and paid before receiving Consum/Storab products on the same PO
            # if line_has_service_zero_qty and related_po and rec.release_to_pay_manual != 'no':
            if line_has_service_zero_qty and related_po:
                # EOI 814
                if receipts and prod_on_lines:
                    rec.require_approval = False
                    rec.is_approved = True
                    rec.release_to_pay_manual = 'yes'
                    rec.force_release_to_pay = True
                else:
                    rec.require_approval = False
                    rec.is_approved = True
                    rec.release_to_pay_manual = 'no'
                    rec.force_release_to_pay = True
    
            # Creating Bill from Vendor Bills List View
            elif not related_po and line_has_service and rec.is_approved == True:
                rec.require_approval = False # Show Register Payment, Hide Request Approval
                rec.release_to_pay_manual = 'yes'
                rec.force_release_to_pay = True

            elif not related_po and line_has_service and rec.is_approved == False:
                rec.require_approval = True 
                rec.release_to_pay_manual = 'no'
                rec.force_release_to_pay = True

            elif not related_po and not line_has_service and rec.is_approved == False: #and not active_approval:
                rec.require_approval = False
                rec.release_to_pay_manual = 'no'
                rec.force_release_to_pay = True

            # Creating Bill from Purchase Order (Only for Services)

            # EOI-615: Services, will always require Request Approval
            # EOI-622: Added Manual Check for receipt validation for product on bill lines
            elif related_po and line_has_service: 
                # Products on Bill Lines
                prod_on_lines = rec.invoice_line_ids.product_id.filtered(lambda line:line.detailed_type in ['consu','product'])
                # Checks Products on Receipt if the id is on the Bill Lines and if the Receipt has been Validated
                receipts = related_po.picking_ids.filtered(lambda receipt:receipt.move_ids_without_package.filtered(lambda r_line:r_line.product_id.id in prod_on_lines.ids and r_line.quantity_done != 0) and receipt.state == 'done') 
                if line_has_freight and receipts and rec.is_approved == True:
                    rec.release_to_pay_manual = 'yes'
                    rec.force_release_to_pay = True
                    rec.require_approval = False

                elif rec.is_approved == True and receipts and not line_has_freight:
                    rec.force_release_to_pay = False 
                    rec.require_approval = False

                    # EOI 814 added elif for case XIII
                elif rec.is_approved == True and not prod_on_lines and not receipts and not line_has_freight:
                    rec.release_to_pay_manual = 'yes'
                    rec.force_release_to_pay = True
                    rec.require_approval = False

                elif rec.is_approved == True and not receipts and not line_has_freight:
                    rec.release_to_pay_manual = 'no'
                    rec.force_release_to_pay = True
                    rec.require_approval = False

                elif rec.is_approved == False and active_approval: 
                    rec.release_to_pay_manual = 'no'
                    rec.force_release_to_pay = True
                    rec.require_approval = True 

                elif rec.is_approved == True and not active_approval:
                    rec.require_approval = False

                    # EOI-815: Catches the scenario where Bill has PO w/ Service, but Service is NOT on PO Lines
                    if not prod_on_lines and not line_has_service_zero_qty:
                        rec.release_to_pay_manual = 'yes'
                        rec.force_release_to_pay = True
                        rec.require_approval = False

                else:
                    rec.require_approval = True 
                    rec.release_to_pay_manual = 'no'
                    rec.force_release_to_pay = True 

            elif related_po and line_has_service and rec.is_approved == False and not line_has_service_zero_qty and not line_has_freight:
                rec.require_approval = True # Hide Register Payment, Show Request Approval
                rec.release_to_pay_manual = 'no'
                rec.force_release_to_pay = True

            # EOI-508: Any 3-way match item is exempt from the approval process
            elif related_po and not line_has_service: 
                # EOI-622: Preventing Freight from affecting 3-way match

                # Products on Bill Lines
                prod_on_lines = rec.invoice_line_ids.product_id.filtered(lambda line:line.detailed_type in ['consu','product'])
                # Checks Products on Receipt if the id is on the Bill Lines and if the Receipt has been Validated
                receipts = related_po.picking_ids.filtered(lambda receipt:receipt.move_ids_without_package.filtered(lambda r_line:r_line.product_id.id in prod_on_lines.ids and r_line.quantity_done != 0) and receipt.state == 'done') 
                
                if line_has_freight and receipts:
                    rec.is_approved = True
                    rec.require_approval = False
                    rec.release_to_pay_manual = 'yes'
                    rec.force_release_to_pay = True

                elif not line_has_freight and receipts:
                    rec.require_approval = False
                    rec.is_approved = True
                    rec.release_to_pay_manual = 'yes'
                    rec.force_release_to_pay = True

                else:
                    rec.require_approval = False
                    rec.is_approved = True
                    rec.release_to_pay_manual = 'no'
                    rec.force_release_to_pay = True

            # EOI-562: Added check for line_has_freight to not affect the expected outcome aka release_to_pay_manual == 'yes'
            elif related_po and rec.is_approved == False and not line_has_service and not active_approval:
                # EOI-622: Preventing Freight from affecting 3-way match
                if line_has_freight and rec.state == 'posted':
                    rec.is_approved = True
                    rec.require_approval = False
                    rec.release_to_pay_manual = 'yes'
                    rec.force_release_to_pay = True
                else:
                    rec.is_approved = True
                    rec.require_approval = False

            else:

                # Match if received qty and bill qty matches to make it payable
                pay_flag = 'no'
                for line in rec.invoice_line_ids:
                    if line.purchase_line_id and line.quantity > 0 and line.purchase_line_id.qty_received == line.quantity:
                        pay_flag = 'yes'
                # eoi614 - test that the line type is right for the should be paid
                line_type = rec.invoice_line_ids.filtered(lambda line: line.product_id.detailed_type in ('consu', 'product'))
                if line_type and rec.linked_purchase_id:  
                    rec.require_approval = False
                    rec.is_approved = True
                    rec.force_release_to_pay = True
                    rec.release_to_pay_manual = pay_flag
                else:              
                    rec.require_approval = False
                    rec.is_approved = True
                    rec.force_release_to_pay = False

            # EOI 814, To be paid field needs to say 'no' in the draft state. 
            if rec.state == 'draft':
                rec.release_to_pay_manual = 'no'
                    
    # EOI-508: Removal of the _compute_check_product_type function, logic replaced by _compute_require_approval

    # EOI-349: Checks if corresponding multi_level_approval is 'Approved'
    # EOI-508: Revised function to be more focused and to encompass a the 3way match special scenario
    # NOTES: Runs on all account.move list view, runs when Register Payment button is hit, and obv. runs on the form views
    @api.depends('multi_approval_ids')
    def _compute_is_approved(self):
        for rec in self:
            # Find PO related to current Bill
            related_po = rec.env['purchase.order'].search([('invoice_ids','in',rec.ids)])
            
            # Check if product lines has a service
            # EOI-520: Specified to exclude Freight/Shipping
            line_has_service = rec.invoice_line_ids.filtered(lambda line: line.product_id.detailed_type == 'service' and line.product_id.categ_id.name != 'Freight / Shipping')
            
            # Check for 'Approved' multi approval requests associated with the Bill
            #EOI 729: Vender Credit shouldn't require approval. 
            if rec.move_type == 'in_invoice':
                ma_req = rec.multi_approval_ids.filtered(lambda request: request.state == 'Approved')

                if ma_req:
                    rec.is_approved = True

            # # EOI-508: Include SPECIAL SCENARIO
            # elif related_po and not line_has_service and rec.release_to_pay_manual == 'yes':
            #     rec.is_approved = True
                else:
                    rec.is_approved = False
            else:
                rec.is_approved = True

    # EOI-349: Recreating the Request Approval Button for Account Move
    def action_request(self):
        budget = self.invoice_line_ids.analytic_account_id
        # EOI-596: Raise warning if Analytic Account missing user or budget lines
        if not budget.user_id:
            raise UserError(f'Analytic Account: {budget.complete_name} has no responsible user. Please have one entered in on the analytic accounts page of the accounting app.')
        if not budget.crossovered_budget_line:
            raise UserError(f'Analytic Account: {budget.complete_name} has no Budget Items. Please have one entered in on the analytic accounts page of the accounting app.')

        ma_request = self.env['multi.approval']
        ra_request = self.env['request.approval']

        # EOI-480: Override amount_total if there is a service in the invoice lines
        # EOI-520: Specified to exclude Freight/Shipping
        line_has_service = self.invoice_line_ids.filtered(lambda line: line.product_id.detailed_type == 'service' and line.product_id.categ_id.name != 'Freight / Shipping')
        if line_has_service:
            self.service_total = 0
            for line in line_has_service:
                # EOI742 quantity is factored into the services total 
                # EOI859 - tax is included in price_total
                self.service_total += line.price_total

        model_name = 'account.move'
        vendor = self.partner_id.name
        res_id = self.id
        types = self.env['multi.approval.type']._get_types(model_name)
        approval_type = self.env['multi.approval.type'].filter_type(
                    types, model_name, res_id)

        record = self.env[model_name].browse(res_id)
        record_name = record.display_name or _('this object')
        title = _('Request approval for {}').format(record_name)
        record_url = ra_request._get_obj_url(record)
        if approval_type.request_tmpl:
            descr = _(approval_type.request_tmpl).format(
                record_url=record_url,
                record_name=record_name,
                record=record
            )
        else:
            descr = ''
        # Multi Level Approval Request Data
        # EOI-520: Added 'amount' into the vals dict
        vals = {
            'name': title,
            'type_id': approval_type.id,
            'description': descr,
            'reference':self.name,
            'deadline': self.invoice_date,
        # EOI-713: Added currency indicator before amount
            'currency_id': self.currency_id.id,
            'state':'Draft',
            'amount': self.service_total,
            'origin_ref': '{model},{res_id}'.format(
                model=model_name,
                res_id=res_id)
        }
        req = ma_request.create(vals)
        # Gather and write all approvers onto Multi Level Approval Request Lines
        
        ma_request.update_approver_ids(res_id,req,self.service_total,model_name,budget)
        return {
            
            'name': _('My Requests'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'multi.approval',
            'view_id': self.env.ref('multi_level_approval.multi_approval_view_form_inherit').id,
            'res_id': req.id,
        }

    @api.onchange('ref')
    def _onchange_ref(self):
        self.payment_reference = self.ref
    
    @api.onchange('purchase_vendor_bill_id', 'purchase_id')
    def _onchange_purchase_auto_complete(self):
        ''' Load from either an old purchase order, either an old vendor bill.
        When setting a 'purchase.bill.union' in 'purchase_vendor_bill_id':
        * If it's a vendor bill, 'invoice_vendor_bill_id' is set and the loading is done by '_onchange_invoice_vendor_bill'.
        * If it's a purchase order, 'purchase_id' is set and this method will load lines.
        /!\ All this not-stored fields must be empty at the end of this function.
        '''
        if self.purchase_vendor_bill_id.vendor_bill_id:
            self.invoice_vendor_bill_id = self.purchase_vendor_bill_id.vendor_bill_id
            self._onchange_invoice_vendor_bill()
        elif self.purchase_vendor_bill_id.purchase_order_id:
            self.purchase_id = self.purchase_vendor_bill_id.purchase_order_id
        self.purchase_vendor_bill_id = False

        if not self.purchase_id:
            return

        # Copy data from PO
        invoice_vals = self.purchase_id.with_company(
            self.purchase_id.company_id)._prepare_invoice()
        invoice_vals['currency_id'] = self.line_ids and self.currency_id or invoice_vals.get(
            'currency_id')
        del invoice_vals['ref']
        self.update(invoice_vals)

        # Copy purchase lines.
        po_lines = self.purchase_id.order_line - \
            self.line_ids.mapped('purchase_line_id')
        new_lines = self.env['account.move.line']
        sequence = max(self.line_ids.mapped('sequence')) + \
            1 if self.line_ids else 10
        for line in po_lines.filtered(lambda l: not l.display_type):
            line_vals = line._prepare_account_move_line(self)
            line_vals.update({'sequence': sequence})
            ############ Modification to base code
            line_vals.update({'account_id': line.override_account_id})
            ############
            new_line = new_lines.new(line_vals)
            sequence += 1
            # new_line.account_id = new_line._get_computed_account()
            new_line._onchange_price_subtotal()
            new_lines += new_line
        new_lines._onchange_mark_recompute_taxes()

        # Compute invoice_origin.
        origins = set(self.line_ids.mapped('purchase_line_id.order_id.name'))
        self.invoice_origin = ','.join(list(origins))
        #################### Modification to base code
        if self.linked_purchase_id or len(self.invoice_line_ids.filtered('purchase_order_id')) > 1:
            #self.linked_purchase_id = False
            existing_po_ids = []
            for li in self.invoice_line_ids.filtered('purchase_order_id'):
                if li.purchase_order_id and li.purchase_order_id.id in existing_po_ids:
                    continue
                else:
                    existing_po_ids.append(li.purchase_order_id.id)
            if len(existing_po_ids) > 1:
                self.linked_purchase_id = False
            else:
                if existing_po_ids:
                    po_id = self.env['purchase.order'].browse(existing_po_ids)
                    self.linked_purchase_id = po_id
        else:
            self.linked_purchase_id = self.invoice_line_ids.mapped('purchase_order_id')
        ####################

        # Compute ref.
        refs = self._get_invoice_reference()
        self.ref = ', '.join(refs)

        # Compute payment_reference.
        if len(refs) == 1:
            self.payment_reference = refs[0]

        self.purchase_id = False
        self._onchange_currency()

    #Copied from third party module
    def _compute_x_need_approval(self):
        for rec in self:
            rec['x_need_approval'] = rec.env['multi.approval.type'].compute_need_approval(rec)

    #EOI 350
    def _compute_bank_info_check(self):
        for record in self:
            record.bank_info_check = False
            if record.partner_bank_id:
                if record.partner_bank_id.acc_number:
                    record.bank_info_check = True
    #EOI 350
    def _compute_terms_due_date(self):
        for record in self:
            if record.invoice_payment_term_id.id == 9:
                if (record.invoice_payment_term_id.line_ids[0].value == 'percent'):
                    record['terms_due_date'] = record.date + \
                        datetime.timedelta(
                            days=record.invoice_payment_term_id.line_ids[0].days)
            else:
                record['terms_due_date'] = False
    
    #EOI 350
    def _compute_terms_amount(self):
        for record in self:
            if record.invoice_payment_term_id.id == 9:
                record['terms_amount'] = record.amount_total
                if (record.invoice_payment_term_id.line_ids[0].value == 'percent'):
                    record['terms_amount'] = record['terms_amount'] * \
                        (record.invoice_payment_term_id.line_ids[0].value_amount * .01)
            else:
                record['terms_amount'] = 0

    #EOI 350
    @api.depends('name')
    def _compute_multi_approval_ids(self):
        for record in self:
            origin_ref = '{model},{res_id}'.format(model='account.move', res_id=record.id)
            record.multi_approval_ids = self.env['multi.approval'].search([('origin_ref', '=', origin_ref)])
    
    #EOI 350
    @api.depends('multi_approval_ids')
    def _compute_multi_approval_id_count(self):
        for record in self:
            record.multi_approval_id_count = len(record.multi_approval_ids)

    #EOI 350
    def action_view_approvals(self):
        return {
            'name': 'Approvals',
            'view_mode': 'tree,form',
            'res_model': 'multi.approval',
            'type': 'ir.actions.act_window',
            'target' : 'current',
            'domain': [('id', 'in', self.multi_approval_ids.mapped('id'))],
        }

    # EOI-444:Raise warning when confirming a vendor bill with amount = $0
    def action_post(self):
        if self.move_type == 'in_invoice' and sum(self.invoice_line_ids.mapped('price_subtotal')) == 0 and not self.warning_displayed:
            self.write({'warning_displayed': True})
            self.env.cr.commit()
            raise UserError(str('Warning: You are confirming a Vendor Bill with a $0 amount'))

        # EOI-839 Refund name sequence switch from "BILL/" to "CR/". Removed wrong logic of EOI-785
        if self.journal_id.refund_sequence and self.move_type == 'in_refund':
                # Call for next sequence computation
                self._set_next_sequence()
                textsplit = self.name.split('/', 1)
                self.name = 'CR/'
                self.name += textsplit[1]

        super(AccountMove, self).action_post()

    def write(self, vals):
        """EOI502 - If price has changed from editing set all active approvals to draft
        """
        for invoice_line in vals.get("invoice_line_ids", []):
            if len(invoice_line) >= 2:
                if invoice_line[2] and invoice_line[2].get("amount_currency"):
                    for approval in self.multi_approval_ids:
                        for approval_line in approval.line_ids:
                            if approval_line.status in ("pending", "new", "approved"):
                                approval.state = 'Draft'
                                approval_line.status = "new"
                                approval_line.user_approval_ids.unlink()
                                approval_line.action_timestamp = False
        return super(AccountMove, self).write(vals)

    def button_cancel(self):
        """EOI502 - If canceled cancel all active approvals
        """
        for approval in self.multi_approval_ids:
            for approval_line in approval.line_ids:
                if approval_line.status in ("pending", "new", "approved"):
                    approval_line.status = 'cancel'
                    approval.state = 'Cancel'

        return super(AccountMove, self).button_cancel()

    def close_posted_approvals(self):
        """EOI502 - Cancel all approvals for bills that are already posted
        """
        bills = self.env['account.move'].search([("approval_ids", "=", True),("state", "=", "posted")])
        for bill in bills:
            for approval in bill.multi_approval_ids:
                for approval_line in approval.line_ids:
                    if approval_line.status in  ("new", "pending"):
                        approval_line.status = 'cancel'
                        approval.state = 'Cancel'

    def button_set_checked(self):
        for move in self:
            move.to_check = False


    # EOI-736: Copied button_draft and button_cancel to swap a piece of code (more below)
    def button_draft(self):
        AccountMoveLine = self.env['account.move.line']
        excluded_move_ids = []

        if self._context.get('suspense_moves_mode'):
            excluded_move_ids = AccountMoveLine.search(AccountMoveLine._get_suspense_moves_domain() + [('move_id', 'in', self.ids)]).mapped('move_id').ids

        for move in self:
            if move in move.line_ids.mapped('full_reconcile_id.exchange_move_id'):
                raise UserError(_('You cannot reset to draft an exchange difference journal entry.'))
            if move.tax_cash_basis_rec_id or move.tax_cash_basis_origin_move_id:
                # If the reconciliation was undone, move.tax_cash_basis_rec_id will be empty;
                # but we still don't want to allow setting the caba entry to draft
                # (it'll have been reversed automatically, so no manual intervention is required),
                # so we also check tax_cash_basis_origin_move_id, which stays unchanged
                # (we need both, as tax_cash_basis_origin_move_id did not exist in older versions).
                raise UserError(_('You cannot reset to draft a tax cash basis journal entry.'))
            if move.restrict_mode_hash_table and move.state == 'posted' and move.id not in excluded_move_ids:
                raise UserError(_('You cannot modify a posted entry of this journal because it is in strict mode.'))
            # We remove all the analytics entries for this journal
            move.mapped('line_ids.analytic_line_ids').unlink()

        # EOI-736: Commented out this line and added it to button_cancel below
        # self.mapped('line_ids').remove_move_reconcile()
        self.write({'state': 'draft', 'is_move_sent': False})

    def button_cancel(self):
        self.write({'auto_post': False, 'state': 'cancel'})
        # EOI-736: Made Bills unlink and unpaid for payments only when cancelled
        for move in self:
            self.mapped('line_ids').remove_move_reconcile()
