# -*- coding: utf-8 -*-
from odoo import http
import json

class CfsAuthSaml(http.Controller):

    @http.route('/auth_saml/bulk_create', methods=['POST'], auth='api_key', csrf=False)
    def api_bulk_create(self, **kw):
        """EOI551 Bulk Create saml entry for all user with a cfs.energy accout

        Returns:
            200 - list of dict
                [
                    {
                        "user_id": user_id,
                        "user_login": user_login,
                        "saml_entry": saml_entry.id
                    }
                ]
            400 - not authenticated
        """
        users = http.request.env['res.users'].search([('login', 'like', '@cfs.energy')])
        if not users:
            return http.Response(f'You may not be authenticated', status=400)
        results = []
        for user in users:
            # todo sudo shouldn't be needed to access res.users.saml
            # find if the user has a saml entry
            saml_entry = http.request.env['res.users.saml'].sudo().search([('user_id', '=', user.id)], limit=1)
            # if the user has a saml entry, skip
            if saml_entry:
                continue
            # create the saml entry if it does not exist
            saml_entry = http.request.env['res.users.saml'].sudo().create({
                'user_id': user.id,
                'saml_provider_id': 1,
                'saml_uid': user.login
            })
            results.append({
                "user_id": user.id,
                "user_login": user.login,
                "saml_entry": saml_entry.id
            })
        return http.Response(json.dumps(results), status=200)

    @http.route('/auth_saml/create', methods=['POST'], auth='api_key', csrf=False)
    def api_create_saml_by_uid(self, **kw):
        """EOI551 Create SAML entry for user if they don't already have one

        form-data:
            user_id (int) - id of the user to add saml auth for

        return
            200 - if user does not have saml entry
            400 - if user already has saml entry
                if user_id not parsable int
                if no user exists for that id
        """
        try:
            user_id = int(kw.get('user_id'))
        except ValueError as verr:
            return http.Response(f'user_id must be a parsable int.', status=400)
        if not user_id:
            return http.Response("user_id is needed as form data", status=400)
        # When using browse, it seems to try to get a record so we cannot use truthy falsy
        user = http.request.env['res.users'].search([('id', '=', user_id)])
        if not user:
            return http.Response(f"User with id {user_id} cannot be found or you are not authenticated.", status=400)
        # find saml entry with user id and create if does not exist
        saml_entry = http.request.env['res.users.saml'].sudo().search([('user_id', '=', user.id)], limit=1)
        if not saml_entry:
            saml_entry = http.request.env['res.users.saml'].sudo().create({
                'user_id': user_id,
                'saml_provider_id': 1,
                'saml_uid': user.login
            })
            return http.Response(json.dumps({'saml_id': saml_entry.id}), status=200)
        return http.Response(f"User {user.login} already has SAML auth", status=400)
