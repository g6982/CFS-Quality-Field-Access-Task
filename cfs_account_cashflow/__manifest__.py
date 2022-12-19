# -*- coding: utf-8 -*-
{
    'name': "CFS: Cash Flow Report Changes",

    'summary': """
        Short (1 phrase/line) summary of the module's purpose, used as
        subtitle on modules listing or apps.openerp.com""",

    'description': """
        Task ID: 2501764
        1. Split the Entries made on the Stock Input Account by the Product Categories on the Cash Flow Report
        2. Do not show any entries made by the Stock Output Account on the Cash Flow Report
        3. Journal Entries that impact the Stock Output Account and Expense Account from an Invoice should not show up on the Cash Flow Report
    """,

    'author': "Odoo Inc.",
    'website': "http://www.odoo.com",
    'category': 'Accounting/Accounting',
    'license': 'OEEL-1',
    'version': '0.1',
    'depends': ['cfs_autoexec','account_reports', 'account_accountant'],
    'data': [
    ],
}
