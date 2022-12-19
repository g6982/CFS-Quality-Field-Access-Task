from odoo import models, api, fields
from odoo.http import request
from odoo.exceptions import UserError
# EOI 700 imported request to create a URL



class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    # EOI-322: Auto populate Buyer on Purchase Orders
    cfs_buyer = fields.Many2one('res.users', string='Buyer', default=lambda self: self.env.user)

    # EOI-762: Updated PO Close Function to close PO's only when they have received all their products and or already paid/in_payment
    def _check_close(self):
        purchase_orders = self.env["purchase.order"].search(
            [('state', '=', 'purchase')]
        )


        # POs with only Consumable/Storable Products
        po_w_prod = purchase_orders.filtered(lambda po: 
            po.invoice_ids.filtered(lambda inv: inv.state in "posted" and inv.payment_state in ["in_payment","paid"])
            and
            po.picking_ids.filtered(lambda pic: pic.state in "done")
            and
            po.order_line.filtered(lambda line: 
                line. qty_received == line.qty_invoiced 
                and
                line.product_id.product_tmpl_id.detailed_type != 'service'
                )
        )

        # POs with only Services
        po_w_serv = purchase_orders.filtered(lambda po:
            po.invoice_ids.filtered(lambda inv: inv.state in "posted" and inv.payment_state in "paid")
            and
            po.order_line.filtered(lambda line: 
                line.qty_received == line.qty_invoiced
                and
                line.product_id.product_tmpl_id.detailed_type == 'service'
                )
        )

        # POs with Services/Consumable/Storable Products
        po_w_both = purchase_orders.filtered(lambda po:
            po.invoice_ids.filtered(lambda inv: inv.state in "posted" and inv.payment_state in ["in_payment","paid"])
            and
            po.picking_ids.filtered(lambda pic: pic.state in "done")
            and
            po.order_line.filtered(lambda line:
                line.qty_received == line.qty_invoiced
                and
                line.product_id.product_tmpl_id.detailed_type in ["consu","product","service"]
                )
            and
            po not in po_w_serv
            and
            po not in po_w_prod
        )

        # Consolidates all POs into one list
        ready_po = self
        ready_po += po_w_prod
        ready_po += po_w_serv
        ready_po += po_w_both

        for r_po in ready_po:
            r_po.state = "closed"

        return True
 

    # EOI-400: Fix auto-population default tax id on PO order lines 
    @api.onchange('cfs_default_product_line_tax')
    def onchange_cfs_default_product_line_tax(self):
        if self.cfs_default_product_line_tax:
            for line in self.order_line:
                line.taxes_id = self.cfs_default_product_line_tax

    # EOI-372: Warehouse onchange action events
    @api.onchange('wh_type')
    def _onchange_warehouse_type(self):
        for rec in self:
            if rec.wh_type == 'production':
                rec.order_line.write({'is_prod':True})
                rec.order_line._update_quality_code()
            else:
                rec.order_line.write({'is_prod':False})

    # EOI-384: Add PO state change notifications(emails)
    def write(self, vals):
        old_state = self.state
        res = super().write(vals)
        # EOI-700: add a clickable URL link for PO when status changed 
        model = 'purchase.order'
        vals_state = vals.get("state", False)
        base_url = f"{request.env['ir.config_parameter'].sudo().get_param('web.base.url')}/web#id={self.id}&view_type=form&model={model}"
        link_template = "<a href='%s'>%s</a>" % (base_url, self.name)
    
        if vals_state and vals_state != old_state and (self.cfs_buyer.login or self.requester_id.login):
            partner_ids = [self.cfs_buyer.partner_id.id, self.requester_id.partner_id.id]
            self.message_notify(

                subject=f"Status Updated: {self.name}",
                # EOI-700 added changed self.name to link_template
                body=f"The status of {link_template} has been updated from {dict(self._fields['state'].selection).get(old_state)} --> {dict(self._fields['state'].selection).get(vals_state)}",
                partner_ids=partner_ids,
                record_name=self.display_name,
                email_layout_xmlid="mail.mail_notification_light",
                model_description=self.env["ir.model"]._get(self._name).display_name,
            )
        return res




        