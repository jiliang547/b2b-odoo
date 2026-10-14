from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestERPSettings(TransactionCase):
    def test_unrelated_settings_save_preserves_restricted_erp_key(self):
        admin = mail_new_test_user(self.env, login="settings-without-erp-role", groups="base.group_system")
        parameters = self.env["ir.config_parameter"].sudo()
        parameters.set_param("b2b_erp.api_token", "private-test-token")
        settings = self.env["res.config.settings"].with_user(admin).create({})
        with self.assertRaises(AccessError):
            settings.read(["b2b_erp_api_token"])
        with self.assertRaises(AccessError):
            settings.write({"b2b_erp_api_token": "not-permitted"})
        settings.set_values()
        self.assertEqual(parameters.get_param("b2b_erp.api_token"), "private-test-token")

    def test_authorized_settings_admin_can_still_save_erp_key(self):
        admin = mail_new_test_user(self.env, login="settings-with-erp-role",
                                  groups="base.group_system,b2b_erp_connector.group_b2b_integration_manager")
        settings = self.env["res.config.settings"].with_user(admin).create({"b2b_erp_api_token": "authorized-test-token"})
        settings.set_values()
        self.assertEqual(self.env["ir.config_parameter"].sudo().get_param("b2b_erp.api_token"), "authorized-test-token")
