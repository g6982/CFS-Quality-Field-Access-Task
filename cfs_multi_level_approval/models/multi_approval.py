# -*- coding: utf-8 -*-

from odoo import models
from odoo.exceptions import UserError
import logging
CFO_MIN_AMOUNT = 50000

_logger = logging.getLogger(__name__)


class cfs_multi_level_approval(models.Model):
    _inherit = "multi.approval"

    # EOI-349: Retrieves Approver IDs and Passes data into Create
    def update_approver_ids(self,res_id,multi_approval_request,service_total,model_name,analytic_account):
        """Update the approvers list based on the model
            EOI-833

        Args:
            res_id (int): id of record being referenced
            multi_approval_request (record): record of type multi.approval that is being worked on
            service_total (float): total of all serviceable items on the puchase.order or account.move record
            model_name (string): name of record model generating an approval. Expected values:
                account.move
                purchase.order

                a debug log will be generated if the model_name is not one of the above
            analytic_account (record): analytic.account record for determining budget
        """

        # Retrive Request from AM and Approver Data
        if model_name == 'account.move':
            account_move = self.env['account.move'].browse(res_id)
            approval_list,chatter_list = account_move.determine_bill_approvers(multi_approval_request,analytic_account,service_total,threshold=CFO_MIN_AMOUNT)
        # Retrive Request from PO and Approver Data
        elif model_name == 'purchase.order':
            purchase_order = self.env['purchase.order'].browse(res_id)
            approval_list,chatter_list = purchase_order.get_approver_vals(multi_approval_request,service_total)
        else:
            _logger.debug(f'model name {model_name} was not recognized for generating approvers')
            raise UserError(f'Approval not generated correctly. Please contact the administrator')
        # eoi591 show in chatter who was deleted
        for message in chatter_list:
            multi_approval_request.message_post(body=message)
        # Creates Lines under the Multi Level Approval Request
        for val in approval_list:
            self.env['multi.approval.line'].with_context({'item': 'new_bill'}).create(val)