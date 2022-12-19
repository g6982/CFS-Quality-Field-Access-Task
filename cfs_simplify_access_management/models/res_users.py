from odoo import fields, models, api, _
from odoo.exceptions import UserError


class res_users(models.Model):
    _inherit = 'res.users'

    def _get_user_access_management_names(self):
        """EOI730 - get access management for user

        Returns:
            access_management (list): list of names of access management

        """
        return [access_right.name for access_right in self.access_management_ids]

    def _if_access_right_exists(self, access_right, limit=1):
        """EOI730 - if the access right is attached to the user

        Args:
            access_right (string): can be substring or full string
            limit (int): access right must only appear in the list x number of times
                default: 1
        Returns:
            True - access right exists only the number of times specified by the limit
            False - otherwise
        """
        access_list = list(filter(lambda x: access_right in x, self._get_user_access_management_names()))
        if access_list and len(access_list) == limit:
            return True 
        return False
