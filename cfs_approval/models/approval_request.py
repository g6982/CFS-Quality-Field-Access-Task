from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError

class ApprovalRequest(models.Model):

    _inherit = "approval.request"
    
    reason = fields.Text(required=True)

    # EOI-518: Fix RL/BQ menu domains
    purchase_order_count = fields.Integer(store=True)

    # EOI-689: Create Boolean to check to see if the cancel button is visible
    is_cancel_visible = fields.Boolean(string="Is Cancel Visible", compute="_compute_can_cancel")

    # EOI-689: When the logged in user is a buyer they will have access to the cancel button on a PR
    # don't need api depends because store=False
    def _compute_can_cancel(self):
        cancel_flag = True
        # cancel is only ever visible in new and approved state
        if self.request_status not in ['new', 'approved']:
            cancel_flag = False
        # cancel is only visble if the number of active attached purchase orders is zero
        if self.purchase_order_count != 0:
            cancel_flag = False
        # cancel is only visible in the approved state for buyers
        is_buyer = True if self.env.user in self.env['access.management'].search([('check_buyer','=',True)]).user_ids else False
        if not is_buyer and self.request_status == 'approved':
            cancel_flag = False
        self.is_cancel_visible = cancel_flag

    # EOI-322: Auto populate Buyer on Purchase Orders
    @api.model
    def create(self, vals):
        vals["cap_buyer_ids"] = []
        for line in vals["product_line_ids"]:
            if line[2] and line[2]["buyer_id"]:
                vals["cap_buyer_ids"].append(line[2]["buyer_id"])
            # vals["cap_buyer_ids"].append(line.buyer_id)
        vals["cap_buyer_ids"] = [(6, 0, set(vals["cap_buyer_ids"]))] 
        return super(ApprovalRequest, self).create(vals)

    # EOI-372: Warehouse onchange action events
    @api.onchange('cap_warehouse')
    def _onchange_warehouse(self):
        for rec in self:
            if rec.cap_warehouse.wh_type == 'production':
                rec.product_line_ids.write({'is_prod': True})
                # rec.product_line_ids._onchange_buyer()
            else:
                rec.product_line_ids.write({'is_prod': False})

    po_canceled = fields.Boolean(compute='_compute_po_cancelled')

    api.depends('purchase_order.state')
    def _compute_po_cancelled(self):
        """EOI377 - compute if the POs are canceled
        """
        for pr in self:
            pos = pr.product_line_ids.purchase_order_line_id.order_id
            pr.po_canceled = not pos.filtered(lambda po: po.state != 'cancel')

    def find_highest_buyer(self):
        # EOI-777: Set buyer_id on all lines to buyer with the highest price
        highest_buyer = self.product_line_ids[self.product_line_ids.mapped('cap_price').index(max(self.product_line_ids.mapped('cap_price')))].buyer_id.id

        for line in self.product_line_ids:
            line.buyer_id = highest_buyer

    # EOI-689: Prevent cancellation of PR if it's tied to a PO
    def action_cancel(self):
        res = super(ApprovalRequest, self).action_cancel()
        if self.purchase_order_count != 0:
            raise UserError("Cannot cancel a Purchase Request that has an associated Purchase Order.")
        else:
            self.request_status = 'cancel'
        return res

    # EOI-689: Added to 'Back to Draft' button functionality
    def action_draft(self):
        res = super(ApprovalRequest, self).action_draft()
        self.request_status = 'new'
        return res

    # EOI-516 PR Submit button click action
    def action_confirm(self):
        approvers = self.mapped("approver_ids").filtered(
            lambda approver: approver.status == "new"
            and approver.user_id.id == self.request_owner_id.id
        )

        # EOI-777: Finds highest buyer
        self.find_highest_buyer()

        # Commented because we do no want activity chatter on PRs
        # approvers.sudo()._create_activity()
        approvers.write({"status": "pending"})

        # if self.res_model == "purchase.order":
        #     po = self.env["purchase.order"].browse(self.res_id)
        #     po.rejected = False

        self.sudo().with_context({"submit": 1}).write({'date_confirmed': fields.Datetime.now()})

        # if self.pr:
        if self.cap_type == 'new' and not self.product_line_ids:
            raise ValidationError('Please add products/items to your Purchase Request')
        # Commenting because on V14 it use to create Account Analytic Line
        # self.product_line_ids.generate_similar_buyer()
        # self.submit_request_action()
        self.write({'request_status': 'approved'})
