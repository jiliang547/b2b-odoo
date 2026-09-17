from odoo import Command
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestB2BPartnerSecurity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.segment = cls.env["b2b.customer.segment"].create({
            "name": "Partner Security Segment",
        })
        cls.partner = cls.env["res.partner"].create({
            "name": "Partner Security Company",
            "is_company": True,
        })
        cls.contact = cls.env["res.partner"].create({
            "name": "Partner Security Contact",
            "parent_id": cls.partner.id,
        })
        cls.pricelist = cls.env["product.pricelist"].create({
            "name": "Partner Security Pricelist",
        })
        cls.internal = mail_new_test_user(
            cls.env,
            login="b2b-security-internal",
            groups="base.group_user",
        )
        cls.operator_editor = mail_new_test_user(
            cls.env,
            login="b2b-security-operator-editor",
            groups="b2b_core.group_b2b_operator,base.group_partner_manager",
        )
        cls.manager = mail_new_test_user(
            cls.env,
            login="b2b-security-manager",
            groups="b2b_core.group_b2b_manager",
        )
        cls.price_manager = mail_new_test_user(
            cls.env,
            login="b2b-security-price-manager",
            groups="b2b_core.group_b2b_special_price_manager",
        )
        cls.product_manager = mail_new_test_user(
            cls.env,
            login="b2b-security-product-manager",
            groups="b2b_core.group_b2b_product_manager",
        )
        cls.marketing = mail_new_test_user(
            cls.env,
            login="b2b-security-marketing",
            groups="b2b_core.group_b2b_marketing_media",
        )
        cls.sales_manager = mail_new_test_user(
            cls.env,
            login="b2b-security-sales-manager",
            groups="sales_team.group_sale_manager",
        )
        cls.settings_admin = mail_new_test_user(
            cls.env,
            login="b2b-security-settings-admin",
            groups="base.group_system",
        )

    def test_internal_user_does_not_receive_b2b_role(self):
        self.assertFalse(self.internal.has_group("b2b_core.group_b2b_operator"))
        self.assertFalse(self.internal.has_group("b2b_core.group_b2b_manager"))

    def test_job_roles_bundle_only_their_stable_native_permissions(self):
        self.assertTrue(self.manager.has_group("b2b_core.group_b2b_operator"))
        self.assertTrue(self.manager.has_group("base.group_partner_manager"))

        self.assertTrue(self.price_manager.has_group("b2b_core.group_b2b_operator"))
        self.assertTrue(self.price_manager.has_group("base.group_partner_manager"))
        self.assertFalse(self.price_manager.has_group("b2b_core.group_b2b_manager"))

        self.assertTrue(self.product_manager.has_group("product.group_product_manager"))
        self.assertFalse(self.product_manager.has_group("b2b_core.group_b2b_manager"))
        self.assertFalse(
            self.product_manager.has_group("b2b_core.group_b2b_special_price_manager")
        )

        self.assertTrue(self.marketing.has_group("b2b_core.group_b2b_operator"))
        self.assertFalse(self.marketing.has_group("product.group_product_manager"))
        self.assertFalse(self.marketing.has_group("b2b_core.group_b2b_manager"))
        self.assertFalse(
            self.marketing.has_group("b2b_core.group_b2b_special_price_manager")
        )

    def test_native_administrators_do_not_receive_customer_approval(self):
        self.assertTrue(
            self.sales_manager.has_group("b2b_core.group_b2b_special_price_manager")
        )
        self.assertFalse(self.sales_manager.has_group("b2b_core.group_b2b_manager"))
        self.assertFalse(
            self.settings_admin.has_group("b2b_core.group_b2b_special_price_manager")
        )
        self.assertFalse(self.settings_admin.has_group("b2b_core.group_b2b_manager"))

    def test_operator_cannot_approve_or_write_sensitive_customer_fields(self):
        partner = self.partner.with_user(self.operator_editor)
        with self.assertRaises(AccessError):
            partner.action_b2b_approve()
        with self.assertRaises(AccessError):
            partner.write({"b2b_approved": True})
        with self.assertRaises(AccessError):
            partner.with_context(_b2b_approval_write_token=True).write({
                "b2b_approved": True,
            })
        with self.assertRaises(AccessError):
            partner.write({"b2b_segment_ids": [Command.link(self.segment.id)]})
        with self.assertRaises(AccessError):
            partner.write({"property_product_pricelist": self.pricelist.id})

    def test_manager_can_approve_segment_assign_and_revoke(self):
        partner = self.partner.with_user(self.manager)
        partner.write({
            "b2b_segment_ids": [Command.link(self.segment.id)],
            "property_product_pricelist": self.pricelist.id,
        })
        partner.action_b2b_approve()
        self.assertTrue(self.partner.b2b_approved)
        self.assertEqual(self.partner.b2b_approved_by_id, self.manager)
        self.assertTrue(self.partner.b2b_approval_date)
        self.assertIn(self.segment, self.partner.b2b_segment_ids)
        self.assertEqual(self.partner.property_product_pricelist, self.pricelist)

        partner.action_b2b_revoke()
        self.assertFalse(self.partner.b2b_approved)
        self.assertFalse(self.partner.b2b_approved_by_id)
        self.assertFalse(self.partner.b2b_approval_date)

    def test_price_manager_can_assign_pricelist_but_not_approve_or_segment(self):
        partner = self.partner.with_user(self.price_manager)
        partner.write({"property_product_pricelist": self.pricelist.id})
        self.assertEqual(self.partner.property_product_pricelist, self.pricelist)
        with self.assertRaises(AccessError):
            partner.action_b2b_approve()
        with self.assertRaises(AccessError):
            partner.write({"b2b_segment_ids": [Command.link(self.segment.id)]})

    def test_company_policy_is_effective_but_not_duplicated_on_contact(self):
        partner = self.partner.with_user(self.manager)
        partner.write({"b2b_segment_ids": [Command.link(self.segment.id)]})
        self.contact.invalidate_recordset()
        self.assertFalse(self.contact.b2b_segment_ids)
        self.assertEqual(self.contact.b2b_effective_segment_ids, self.segment)

        self.contact.with_user(self.manager).action_b2b_approve()
        self.assertTrue(self.partner.b2b_approved)
        self.assertFalse(self.contact.b2b_approved)
        self.assertTrue(self.contact.b2b_effective_approved)

    def test_manager_cannot_write_company_policy_on_child_contact(self):
        contact = self.contact.with_user(self.manager)
        with self.assertRaises(AccessError):
            contact.write({"b2b_segment_ids": [Command.link(self.segment.id)]})
        with self.assertRaises(AccessError):
            contact.write({"b2b_erp_customer_id": "CHILD-ERP"})

    def test_linking_standalone_contact_clears_dormant_policy(self):
        standalone = self.env["res.partner"].with_user(self.manager).create({
            "name": "Standalone Partner",
            "b2b_segment_ids": [Command.link(self.segment.id)],
            "b2b_erp_customer_id": "STANDALONE-ERP",
        })
        standalone.with_user(self.manager).action_b2b_approve()
        standalone.with_user(self.manager).write({"parent_id": self.partner.id})
        self.assertFalse(standalone.b2b_approved)
        self.assertFalse(standalone.b2b_segment_ids)
        self.assertFalse(standalone.b2b_erp_customer_id)
        self.assertEqual(standalone.commercial_partner_id, self.partner)
