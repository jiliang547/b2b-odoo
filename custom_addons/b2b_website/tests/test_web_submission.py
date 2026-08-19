from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestWebSubmissionIdempotency(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env["website"].search([], limit=1)
        cls.Submission = cls.env["b2b.web.submission"].sudo()

    def test_same_token_returns_completed_submission(self):
        token = self.Submission.new_token()
        submission, is_new = self.Submission.claim(
            token, "service_request", self.env.user, self.website
        )
        self.assertTrue(is_new)
        submission.complete("/service-center?submitted=1")

        duplicate, duplicate_is_new = self.Submission.claim(
            token, "service_request", self.env.user, self.website
        )
        self.assertFalse(duplicate_is_new)
        self.assertEqual(duplicate, submission)
        self.assertEqual(duplicate.response_url, "/service-center?submitted=1")

    def test_token_cannot_be_reused_for_another_operation(self):
        token = self.Submission.new_token()
        self.Submission.claim(token, "contact_request", self.env.user, self.website)
        with self.assertRaises(ValidationError):
            self.Submission.claim(token, "sample_request", self.env.user, self.website)

    def test_invalid_token_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.Submission.claim(
                "not-a-token", "service_request", self.env.user, self.website
            )
