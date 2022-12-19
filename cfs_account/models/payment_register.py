from odoo import models, api, _
import logging 
_logger = logging.getLogger(__name__)


class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"
    # EOI 753 update that the currency matches once you click register payment
    @api.depends('journal_id')
    def _compute_currency_id(self):
        for wizard in self:
            currency_ids = wizard.line_ids.mapped('currency_id')
            currency_id = False
            if currency_ids:
                currency_id = currency_ids[0]
            wizard.currency_id = currency_id or wizard.journal_id.currency_id or wizard.source_currency_id or wizard.company_id.currency_id

    def _get_invoice_contacts(self, record):
        # EOI-388: Add remittance emails
        partner = record.partner_id
        # If the partner is already an invoice/billing contact, can return
        if partner.type == "invoice":
            return [partner]
        try:
            invoice_contacts = [contact for contact in partner.child_ids if contact.type == "invoice"]
        except Exception as ex:
            _logger.info(f'Unable to get child ids of the contact to create a payment. The partner {partner} will be used. Error: {str(ex)}')
            return [partner]
        # If there are no contacts:
        if not invoice_contacts:
            return [partner]
        # Take the first invoice contact that we find
        return invoice_contacts


    def _create_payments(self):
        # EOI-388: Add remittance emails
        res = super()._create_payments()
        for rec in res:
            if (
                rec.partner_type == "supplier"
                and rec.partner_id
                and rec.state == "posted"
            ):
                recipients = self._get_invoice_contacts(record=rec)
                if recipients:
                    template = self.env.ref(
                        "cfs_account.mail_template_data_payment_receipt_enhance"
                    )
                    print
                    template.send_mail(
                        rec.id,
                        force_send=True,
                        email_values={"recipient_ids": [(4, recipient.id) for recipient in recipients]},
                    )
        return res