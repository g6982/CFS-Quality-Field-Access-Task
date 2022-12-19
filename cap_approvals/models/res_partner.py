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

from datetime import datetime
from odoo import models, fields, api
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # EOI-806 Set company_type default based on the user who is logged in
    def default_get(self, default_fields):
        values = super().default_get(default_fields)
        # raise UserError(str(self) + '\n' + str(default_fields) + '\n' + str(values))
        ap_tam = self.env['access.management'].search([('is_ap_or_tameka', '=', True)]).user_ids
        if self.env.user in ap_tam:
            values['company_type'] = 'person'
        else:
            values['company_type'] = 'company'

        return values

    # EOI-434: Removing Tax IDs from Vendor names in partner_id dropdown menu
    def _get_name(self):
        """ Utility method to allow name_get to be overrided without re-browse the partner """
        partner = self
        name = partner.name or ''

        if partner.company_name or partner.parent_id:
            if not name and partner.type in ['invoice', 'delivery', 'other']:
                name = dict(self.fields_get(['type'])['type']['selection'])[partner.type]
            if not partner.is_company:
                name = self._get_contact_name(partner, name)
        if self._context.get('show_address_only'):
            name = partner._display_address(without_company=True)
        if self._context.get('show_address'):
            name = name + "\n" + partner._display_address(without_company=True)
        name = name.replace('\n\n', '\n')
        name = name.replace('\n\n', '\n')
        if self._context.get('partner_show_db_id'):
            name = "%s (%s)" % (name, partner.id)
        if self._context.get('address_inline'):
            splitted_names = name.split("\n")
            name = ", ".join([n for n in splitted_names if n.strip()])
        if self._context.get('show_email') and partner.email:
            name = "%s <%s>" % (name, partner.email)
        if self._context.get('html_format'):
            name = name.replace('\n', '<br/>')
        if self._context.get('show_vat') and partner.vat:
            # name = "%s ‒ %s" % (name, partner.vat)
            ######
            name = partner.name 
            ######
        return name

    @api.model
    def create(self, vals):
        raise UserError(str(self) + '\n' + str(vals))
        # res = super(ResPartner, self).create(vals)
        ap_tameka = self.env['access.management'].search([('is_ap_or_tameka', '=', True)]).user_ids
        # raise UserError(str(ap_tameka))

        if self.env.user in ap_tameka:
            self.company_type = 'person'
            vals['company_type'] = 'person'
        else:
            vals['company_type'] = 'company'
        return super(ResPartner, self).create(vals)


class ResPartnerBank(models.Model):
    _inherit = 'res.partner.bank'

    type = fields.Selection([
        ('bank', 'Normal'),
        ('iban', 'IBAN')
    ],'Type')
    account_type = fields.Selection([
        ('c', 'Checking'),
        ('s', 'Savings')
    ],'Account Type')
    swift = fields.Char('SWIFT')
    b_name = fields.Char('Bank Name')
