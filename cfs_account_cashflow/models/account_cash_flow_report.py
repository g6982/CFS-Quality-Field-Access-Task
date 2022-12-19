# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)
# EOI 655 allow clickable links on cashflow statement 

class AccountCashFlowReport(models.AbstractModel):
    _inherit = 'account.cash.flow.report'
    
    @api.model
    def _get_reconciled_move_report_lines(self, options, currency_table_query, payment_move_ids, payment_account_ids):
        ''' Retrieve all moves being not a liquidity move to be shown in the cash flow statement.
        Each amount must be valued at the percentage of what is actually paid.
        E.g. An invoice of 1000 being paid at 50% must be valued at 500.

        :param options:                 The report options.
        :param currency_table_query:    The floating query to handle a multi-company/multi-currency environment.
        :param payment_move_ids:        A tuple containing all account.move's ids being the liquidity moves.
        :param payment_account_ids:     A tuple containing all account.account's ids being used in a liquidity journal.
        :return:                        A list of tuple (account_id, account_code, account_name, account_internal_type, amount).
        '''
        reconciled_account_ids = set()
        reconciled_percentage_per_move = {}
        if not payment_move_ids:
            print("Checkpoint 1")
            return reconciled_percentage_per_move

        # ==== Compute reconciled amount per (move_id, account_id) ====

        query = '''
            SELECT
                debit_line.move_id,
                debit_line.account_id,
                SUM(partial.amount)
            FROM account_move_line credit_line
            LEFT JOIN account_partial_reconcile partial ON partial.credit_move_id = credit_line.id
            INNER JOIN account_move_line debit_line ON debit_line.id = partial.debit_move_id
            WHERE credit_line.move_id IN %s
            AND credit_line.account_id NOT IN %s
            AND credit_line.credit > 0.0
            AND debit_line.move_id NOT IN %s
            AND partial.max_date BETWEEN %s AND %s
            GROUP BY debit_line.move_id, debit_line.account_id
            
            UNION ALL
            
            SELECT
                credit_line.move_id,
                credit_line.account_id,
                -SUM(partial.amount)
            FROM account_move_line debit_line
            LEFT JOIN account_partial_reconcile partial ON partial.debit_move_id = debit_line.id
            INNER JOIN account_move_line credit_line ON credit_line.id = partial.credit_move_id
            WHERE debit_line.move_id IN %s
            AND debit_line.account_id NOT IN %s
            AND debit_line.debit > 0.0
            AND credit_line.move_id NOT IN %s
            AND partial.max_date BETWEEN %s AND %s
            GROUP BY credit_line.move_id, credit_line.account_id
        '''
        self._cr.execute(query, [
            payment_move_ids, payment_account_ids, payment_move_ids, options['date']['date_from'], options['date']['date_to'],
            payment_move_ids, payment_account_ids, payment_move_ids, options['date']['date_from'], options['date']['date_to'],
        ])
        for move_id, account_id, reconciled_amount in self._cr.fetchall():
            reconciled_percentage_per_move.setdefault(move_id, {})
            reconciled_percentage_per_move[move_id].setdefault(account_id, [0.0, 0.0])
            reconciled_percentage_per_move[move_id][account_id][0] += reconciled_amount
            reconciled_account_ids.add(account_id)

        if not reconciled_percentage_per_move:
            print("Checkpoint 2")
            return []

        # ==== Compute the balance per (move_id, account_id) ====

        query = '''
            SELECT
                line.move_id,
                line.account_id,
                SUM(line.balance)
            FROM account_move_line line
            JOIN ''' + currency_table_query + ''' ON currency_table.company_id = line.company_id
            WHERE line.move_id IN %s AND line.account_id IN %s
            GROUP BY line.move_id, line.account_id
        '''
        self._cr.execute(query, [tuple(reconciled_percentage_per_move.keys()), tuple(reconciled_account_ids)])
        for move_id, account_id, balance in self._cr.fetchall():
            if account_id in reconciled_percentage_per_move[move_id]:
                reconciled_percentage_per_move[move_id][account_id][1] += balance

        # ==== Fetch lines of reconciled moves ====

        reconciled_amount_per_account = {}
        reconciled_amount_per_category = {}

        query = '''
            SELECT
                line.move_id,
                line.account_id,
                account.code,
                COALESCE(NULLIF(ir_translation.value, ''), account.name) account_name,
                account.internal_type,
                SUM(ROUND(line.balance * currency_table.rate, currency_table.precision))
            FROM account_move_line line
            LEFT JOIN ''' + currency_table_query + ''' ON currency_table.company_id = line.company_id
            JOIN account_account account ON account.id = line.account_id
            LEFT JOIN ir_translation ON ir_translation.name = 'account.account,name' AND ir_translation.res_id = account.id AND ir_translation.type = 'model' AND ir_translation.lang = %s
            WHERE line.move_id IN %s
            GROUP BY line.move_id, line.account_id, account.code, account_name, account.internal_type
        '''
        self._cr.execute(query, [self.env.user.lang, tuple(reconciled_percentage_per_move.keys())])
        
        for move_id, account_id, account_code, account_name, account_internal_type, balance in self._cr.fetchall():
            # Compute the total reconciled for the whole move.
            total_reconciled_amount = 0.0
            total_amount = 0.0
            for reconciled_amount, amount in reconciled_percentage_per_move[move_id].values():
                total_reconciled_amount += reconciled_amount
                total_amount += amount
                

            # Compute matched percentage for each account.
            if total_amount and account_id not in reconciled_percentage_per_move[move_id]:
                # Lines being on reconciled moves but not reconciled with any liquidity move must be valued at the
                # percentage of what is actually paid.
                reconciled_percentage = total_reconciled_amount / total_amount
                balance *= reconciled_percentage
            elif not total_amount and account_id in reconciled_percentage_per_move[move_id]:
                # The total amount to reconcile is 0. In that case, only add entries being on these accounts. Otherwise,
                # this special case will lead to an unexplained difference equivalent to the reconciled amount on this
                # account.
                # E.g:
                #
                # Liquidity move:
                # Account         | Debit     | Credit
                # --------------------------------------
                # Bank            |           | 100
                # Receivable      | 100       |
                #
                # Reconciled move:                          <- reconciled_amount=100, total_amount=0.0
                # Account         | Debit     | Credit
                # --------------------------------------
                # Receivable      |           | 200
                # Receivable      | 200       |             <- Only the reconciled part of this entry must be added.
                balance = -reconciled_percentage_per_move[move_id][account_id][0]
            else:
                # Others lines are not considered.
                continue

            mv = self.env['account.move'].browse([move_id])
            print("\n")
            print(mv)
            print("\n")
            if mv.move_type == 'in_invoice':
                _logger.info("Bill")
                for line in mv.invoice_line_ids:
                    if line.product_id.categ_id.property_valuation == 'real_time':
                        reconciled_amount_per_category.setdefault(line.product_id.categ_id.id, [account_id, line.product_id.categ_id.id, line.product_id.categ_id.name, account_internal_type, 0.0])
                        reconciled_amount_per_category[line.product_id.categ_id.id][4] += line.price_unit
                    else:
                        if account_id not in reconciled_amount_per_account:
                            reconciled_amount_per_account.setdefault(account_id, [account_id, account_code, account_name, account_internal_type, 0.0])
                            reconciled_amount_per_account[account_id][4] += balance
                        reconciled_amount_per_account[account_id][4] -= line.price_unit
            elif mv.move_type == 'out_invoice':
                for line in mv.invoice_line_ids:
                    if line.product_id.categ_id.property_valuation != 'real_time' or (line.product_id.categ_id.property_account_expense_categ_id.id != account_id and line.product_id.categ_id.property_stock_account_output_categ_id.id != account_id):
                        if account_id not in reconciled_amount_per_account:
                            reconciled_amount_per_account.setdefault(account_id, [account_id, account_code, account_name, account_internal_type, 0.0])
                            reconciled_amount_per_account[account_id][4] += balance
                        reconciled_amount_per_account[account_id][4] -= line.price_unit
            else:
                reconciled_amount_per_account.setdefault(account_id, [account_id, account_code, account_name, account_internal_type, 0.0])
                reconciled_amount_per_account[account_id][4] += balance
        
        return {'account': list(reconciled_amount_per_account.values()), 'category': list(reconciled_amount_per_category.values()), 'money': 'Hello'}
    
    @api.model
    def _get_lines(self, options, line_id=None):

        def _insert_at_index(index, account_id, account_code, account_name, amount, product_categ_id=False, product_categ_name=False):
            ''' Insert the amount in the right section depending the line's index and the account_id. '''
            # Helper used to add some values to the report line having the index passed as parameter
            # (see _get_lines_to_compute).
            line = lines_to_compute[index]
            
            if self.env.company.currency_id.is_zero(amount):
                return

            line.setdefault('unfolded_lines', {})
            if product_categ_id:
                line['unfolded_lines'].setdefault(product_categ_id, {
                    'id': product_categ_id,
                    'name': '%s' % (product_categ_name),
                    'level': line['level'] + 1,
                    'parent_id': line['id'],
                    'columns': [{'name': 0.0, 'class': 'number'}],
                    'caret_options': 'product.category',
                })
                line['columns'][0]['name'] += amount
                line['unfolded_lines'][product_categ_id]['columns'][0]['name'] += amount
            else:
                line['unfolded_lines'].setdefault(account_id, {
                    'id': account_id,
                    'name': '%s %s' % (account_code, account_name),
                    'level': line['level'] + 1,
                    'parent_id': line['id'],
                    'columns': [{'name': 0.0, 'class': 'number'}],
                    'caret_options': 'account.account',
                })
                line['columns'][0]['name'] += amount
                line['unfolded_lines'][account_id]['columns'][0]['name'] += amount

        def _dispatch_result(account_id, account_code, account_name, account_internal_type, amount, product_categ_id=False, product_categ_name=False):
            ''' Dispatch the newly fetched line inside the right section. '''
            if account_internal_type == 'receivable':
                # 'Advance Payments received from customers'                (index=3)
                _insert_at_index(3, account_id, account_code, account_name, -amount)
            elif account_internal_type == 'payable':
                # 'Advance Payments made to suppliers'                      (index=5)
                _insert_at_index(5, account_id, account_code, account_name, -amount, product_categ_id, product_categ_name)
            elif amount < 0:
                if tag_operating_id in tags_per_account.get(account_id, []):
                    # 'Cash received from operating activities'             (index=4)
                    _insert_at_index(4, account_id, account_code, account_name, -amount)
                elif tag_investing_id in tags_per_account.get(account_id, []):
                    # 'Cash in for investing activities'                    (index=8)
                    _insert_at_index(8, account_id, account_code, account_name, -amount)
                elif tag_financing_id in tags_per_account.get(account_id, []):
                    # 'Cash in for financing activities'                    (index=11)
                    _insert_at_index(11, account_id, account_code, account_name, -amount)
                else:
                    # 'Cash in for unclassified activities'                 (index=14)
                    _insert_at_index(14, account_id, account_code, account_name, -amount)
            elif amount > 0:
                if tag_operating_id in tags_per_account.get(account_id, []):
                    # 'Cash paid for operating activities'                  (index=6)
                    _insert_at_index(6, account_id, account_code, account_name, -amount, product_categ_id, product_categ_name)
                elif tag_investing_id in tags_per_account.get(account_id, []):
                    # 'Cash out for investing activities'                   (index=9)
                    _insert_at_index(9, account_id, account_code, account_name, -amount, product_categ_id, product_categ_name)
                elif tag_financing_id in tags_per_account.get(account_id, []):
                    # 'Cash out for financing activities'                   (index=12)
                    _insert_at_index(12, account_id, account_code, account_name, -amount, product_categ_id, product_categ_name)
                else:
                    # 'Cash out for unclassified activities'                (index=15)
                    _insert_at_index(15, account_id, account_code, account_name, -amount, product_categ_id, product_categ_name)

        self.flush()
        
        unfold_all = self._context.get('print_mode') or options.get('unfold_all')
        currency_table_query = self.env['res.currency']._get_query_currency_table(options)
        lines_to_compute = self._get_lines_to_compute(options)

        tag_operating_id = self.env.ref('account.account_tag_operating').id
        tag_investing_id = self.env.ref('account.account_tag_investing').id
        tag_financing_id = self.env.ref('account.account_tag_financing').id
        tag_ids = (tag_operating_id, tag_investing_id, tag_financing_id)
        tags_per_account = self._get_tags_per_account(options, tag_ids)

        payment_move_ids, payment_account_ids = self._get_liquidity_move_ids(options)

        # Compute 'Cash and cash equivalents, beginning of period'      (index=0)
        beginning_period_options = self._get_options_beginning_period(options)
        for account_id, account_code, account_name, balance in self._compute_liquidity_balance(beginning_period_options, currency_table_query, payment_account_ids):
            _insert_at_index(0, account_id, account_code, account_name, balance)
            _insert_at_index(16, account_id, account_code, account_name, balance)

        # Compute 'Cash and cash equivalents, closing balance'          (index=16)
        for account_id, account_code, account_name, balance in self._compute_liquidity_balance(options, currency_table_query, payment_account_ids):
            _insert_at_index(16, account_id, account_code, account_name, balance)

        # ==== Process liquidity moves ====
        res = self._get_liquidity_move_report_lines(options, currency_table_query, payment_move_ids, payment_account_ids)
        for account_id, account_code, account_name, account_internal_type, amount  in res:
            _dispatch_result(account_id, account_code, account_name, account_internal_type, amount)

        # ==== Process reconciled moves ====
        res = self._get_reconciled_move_report_lines(options, currency_table_query, payment_move_ids, payment_account_ids)
        print("\n")
        print(res)
        print("\n")
        if 'account' in res:
            for account_id, account_code, account_name, account_internal_type, balance in res['account']:
                _dispatch_result(account_id, account_code, account_name, account_internal_type, balance)
        if 'category' in res:
            for account_id, product_categ_id, product_categ_name, account_internal_type, balance in res['category']:
                _dispatch_result(account_id, False, False, account_internal_type, balance, product_categ_id, product_categ_name)

        # 'Cash flows from operating activities'                            (index=2)
        lines_to_compute[2]['columns'][0]['name'] = \
            lines_to_compute[3]['columns'][0]['name'] + \
            lines_to_compute[4]['columns'][0]['name'] + \
            lines_to_compute[5]['columns'][0]['name'] + \
            lines_to_compute[6]['columns'][0]['name']
        # 'Cash flows from investing & extraordinary activities'            (index=7)
        lines_to_compute[7]['columns'][0]['name'] = \
            lines_to_compute[8]['columns'][0]['name'] + \
            lines_to_compute[9]['columns'][0]['name']
        # 'Cash flows from financing activities'                            (index=10)
        lines_to_compute[10]['columns'][0]['name'] = \
            lines_to_compute[11]['columns'][0]['name'] + \
            lines_to_compute[12]['columns'][0]['name']
        # 'Cash flows from unclassified activities'                         (index=13)
        lines_to_compute[13]['columns'][0]['name'] = \
            lines_to_compute[14]['columns'][0]['name'] + \
            lines_to_compute[15]['columns'][0]['name']
        # 'Net increase in cash and cash equivalents'                       (index=1)
        lines_to_compute[1]['columns'][0]['name'] = \
            lines_to_compute[2]['columns'][0]['name'] + \
            lines_to_compute[7]['columns'][0]['name'] + \
            lines_to_compute[10]['columns'][0]['name'] + \
            lines_to_compute[13]['columns'][0]['name']

        # ==== Compute the unexplained difference ====

        closing_ending_gap = lines_to_compute[16]['columns'][0]['name'] - lines_to_compute[0]['columns'][0]['name']
        computed_gap = sum(lines_to_compute[index]['columns'][0]['name'] for index in [2, 7, 10, 13])
        delta = closing_ending_gap - computed_gap
        if not self.env.company.currency_id.is_zero(delta):
            lines_to_compute.insert(16, {
                'id': 'cash_flow_line_unexplained_difference',
                'name': _('Unexplained Difference'),
                'level': 0,
                'columns': [{'name': delta, 'class': 'number'}],
            })

        # ==== Build final lines ====

        lines = []
        for line in lines_to_compute:
            unfolded_lines = line.pop('unfolded_lines', {})
            sub_lines = [unfolded_lines[k] for k in sorted(unfolded_lines)]

            line['unfoldable'] = len(sub_lines) > 0
            line['unfolded'] = line['unfoldable'] and (unfold_all or line['id'] in options['unfolded_lines'])

            # Header line.
            line['columns'][0]['name'] = self.format_value(line['columns'][0]['name'])
            lines.append(line)

            # Sub lines.
            for sub_line in sub_lines:
                sub_line['columns'][0]['name'] = self.format_value(sub_line['columns'][0]['name'])
                sub_line['style'] = '' if line['unfolded'] else 'display: none;'
                lines.append(sub_line)

            # Total line.
            if line['unfoldable']:
                lines.append({
                    'id': '%s_total' % line['id'],
                    'name': _('Total') + ' ' + line['name'],
                    'level': line['level'] + 1,
                    'parent_id': line['id'],
                    'columns': line['columns'],
                    'class': 'o_account_reports_domain_total',
                    'style': '' if line['unfolded'] else 'display: none;',
                })
        return lines