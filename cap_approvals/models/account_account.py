from odoo import models, fields, api

class AccountAccount(models.Model):
    _inherit = "account.account"

    # EOI 784 Adding purchase account field
    purchase_account = fields.Boolean(default = False, help = "When the checkbox is selected, that account is available to be selected on the GL accounts field in PRs, POs, and Bills.")
