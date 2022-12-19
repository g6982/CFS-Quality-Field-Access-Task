
from .common import AccountCommon,setAssertionFunction

class TestAccountMove(AccountCommon):
    def test_determine_bill_approvers(self):
        """
        Given datetime can properly be converted
        """
        setAssertionFunction("test_determine_bill_approvers")
        multi_approval_request = self.env['multi.approval'].browse(16014)
        analytic_account = self.env['account.analytic.account'].browse(1571)
        try:
            approval_list,chatter_list = self.env['account.move'].determine_bill_approvers(
                multi_approval_request = multi_approval_request, 
                analytic_account = analytic_account,
                service_total = 30000,
                threshold = 50000
            )
            for key,val in approval_list.items():
                print(f'key: {key} - val: {val}')
            self.assertEqual(approval_list)
        except Exception as err:
            self.assertionErrors.append(err)