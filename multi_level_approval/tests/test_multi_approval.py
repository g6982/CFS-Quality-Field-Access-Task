from .common import ExportsCommon,setAssertionFunction

class TestMultiApprovalLine(ExportsCommon):
    def test_multi_approval_get_approval_type(self):
        """
        EOI695 - Test that we receive the proper exceptions
        """
        setAssertionFunction("test_multi_approval_get_approval_type")
        try:
            # the following approval should be a purchase
            approval_type = self.env['multi.approval'].browse(14058)._get_approval_type()
            self.assertEquals(approval_type, "purchase")
        except Exception as err:
            self.assertionErrors.append(err)
