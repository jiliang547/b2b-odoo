from odoo import Command
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestB2BCustomerPricing(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env["website"].search([], limit=1)
        cls.product_a = cls.env["product.product"].create({
            "name": "Company Special Product", "list_price": 150,
        })
        cls.product_b = cls.env["product.product"].create({
            "name": "Agreement Product", "list_price": 160,
        })
        cls.product_c = cls.env["product.product"].create({
            "name": "Base Product", "list_price": 170,
        })
        currency = cls.website.company_id.currency_id
        cls.base_pricelist = cls.env["product.pricelist"].create({
            "name": "Distributor Base Test",
            "currency_id": currency.id,
            "item_ids": [Command.create({
                "compute_price": "fixed", "fixed_price": 100,
            })],
        })
        cls.lower_override = cls.env["product.pricelist"].create({
            "name": "Annual Agreement Test",
            "currency_id": currency.id,
            "item_ids": [Command.create({
                "applied_on": "1_product",
                "product_tmpl_id": cls.product_b.product_tmpl_id.id,
                "min_quantity": 20,
                "compute_price": "fixed",
                "fixed_price": 90,
            })],
        })
        cls.high_override = cls.env["product.pricelist"].create({
            "name": "Company Project Test",
            "currency_id": currency.id,
            "item_ids": [
                Command.create({
                    "applied_on": "1_product",
                    "product_tmpl_id": cls.product_a.product_tmpl_id.id,
                    "min_quantity": 50,
                    "compute_price": "fixed",
                    "fixed_price": 80,
                }),
                Command.create({
                    "compute_price": "fixed", "fixed_price": 1,
                }),
            ],
        })
        cls.customer_type = cls.env["b2b.customer.type"].create({
            "name": "Distributor Pricing Test",
        })
        cls.env["b2b.customer.type.pricelist"].create({
            "customer_type_id": cls.customer_type.id,
            "website_id": cls.website.id,
            "pricelist_id": cls.base_pricelist.id,
        })
        cls.company = cls.env["res.partner"].create({
            "name": "Customer Pricing Company",
            "is_company": True,
            "b2b_customer_type_id": cls.customer_type.id,
        })
        cls.env["b2b.partner.pricelist.override"].create([
            {
                "partner_id": cls.company.id,
                "website_id": cls.website.id,
                "pricelist_id": cls.lower_override.id,
                "priority": 20,
            },
            {
                "partner_id": cls.company.id,
                "website_id": cls.website.id,
                "pricelist_id": cls.high_override.id,
                "priority": 10,
            },
        ])
        cls.effective = cls.company._b2b_get_effective_pricelist(
            cls.website, currency
        )

    def test_customer_type_creates_one_native_effective_pricelist(self):
        self.assertTrue(self.effective)
        self.assertEqual(self.effective.b2b_effective_partner_id, self.company)
        self.assertEqual(self.effective.currency_id, self.base_pricelist.currency_id)
        self.assertEqual(self.company.property_product_pricelist, self.effective)

    def test_native_pricelist_feature_is_enabled(self):
        self.assertTrue(
            self.env["res.groups"]._is_feature_enabled(
                "product.group_product_pricelist"
            )
        )

    def test_contact_inherits_company_effective_pricing(self):
        contact = self.env["res.partner"].create({
            "name": "Customer Pricing Contact",
            "parent_id": self.company.id,
        })
        self.assertEqual(contact.property_product_pricelist, self.effective)
        self.assertEqual(
            contact._b2b_get_effective_pricelist(
                self.website, self.base_pricelist.currency_id
            ),
            self.effective,
        )

    def test_overrides_then_customer_type_base_are_resolved_in_order(self):
        self.assertEqual(self.effective._get_product_price(self.product_a, 50), 80)
        self.assertEqual(self.effective._get_product_price(self.product_b, 20), 90)
        self.assertEqual(self.effective._get_product_price(self.product_c, 1), 100)

    def test_override_global_rule_does_not_shadow_lower_layers(self):
        price, rule_id = self.effective._get_product_price_rule(self.product_b, 20)
        self.assertEqual(price, 90)
        self.assertEqual(
            self.env["product.pricelist.item"].browse(rule_id).pricelist_id,
            self.lower_override,
        )

    def test_moq_comes_from_the_same_winning_layer_as_price(self):
        service = self.env["b2b.product.service"]
        special = service.procurement_info(
            self.product_a, pricelist=self.effective, website=self.website
        )
        agreement = service.procurement_info(
            self.product_b, pricelist=self.effective, website=self.website
        )
        base = service.procurement_info(
            self.product_c, pricelist=self.effective, website=self.website
        )
        self.assertEqual(special["minimum_quantity"], 50)
        self.assertEqual(agreement["minimum_quantity"], 20)
        self.assertEqual(base["minimum_quantity"], 1)

    def test_order_line_uses_native_effective_pricelist(self):
        order = self.env["sale.order"].create({
            "partner_id": self.company.id,
            "pricelist_id": self.effective.id,
        })
        line = self.env["sale.order.line"].create({
            "order_id": order.id,
            "product_id": self.product_a.id,
            "product_uom_qty": 50,
        })
        self.assertEqual(line.price_unit, 80)
        self.assertEqual(line.pricelist_item_id.pricelist_id, self.high_override)

    def test_override_requires_matching_customer_type_base(self):
        other_currency = self.env["res.currency"].search([
            ("id", "!=", self.base_pricelist.currency_id.id),
        ], limit=1)
        if not other_currency:
            self.skipTest("A second currency is required")
        other_pricelist = self.env["product.pricelist"].create({
            "name": "Unmapped Currency Override",
            "currency_id": other_currency.id,
        })
        with self.assertRaises(ValidationError):
            self.env["b2b.partner.pricelist.override"].create({
                "partner_id": self.company.id,
                "website_id": self.website.id,
                "pricelist_id": other_pricelist.id,
            })

    def test_customer_type_cannot_leave_existing_overrides_without_base(self):
        unmapped_type = self.env["b2b.customer.type"].create({
            "name": "Unmapped Pricing Test",
        })
        with self.assertRaises(ValidationError):
            self.company.b2b_customer_type_id = unmapped_type

    def test_source_rule_change_updates_price_and_customer_revision(self):
        revision = self.company.b2b_pricing_revision
        rule = self.high_override.item_ids.filtered(
            lambda item: item.applied_on == "1_product"
        )
        rule.fixed_price = 79
        self.company.invalidate_recordset(["b2b_pricing_revision"])
        self.assertGreater(self.company.b2b_pricing_revision, revision)
        self.assertEqual(self.effective._get_product_price(self.product_a, 50), 79)

    def test_company_override_does_not_leak_to_another_company(self):
        other_company = self.env["res.partner"].create({
            "name": "Customer Pricing Isolation Company",
            "is_company": True,
            "b2b_customer_type_id": self.customer_type.id,
        })
        other_effective = other_company._b2b_get_effective_pricelist(
            self.website, self.base_pricelist.currency_id
        )

        self.assertTrue(other_effective)
        self.assertNotEqual(other_effective, self.effective)
        self.assertEqual(other_effective._get_product_price(self.product_a, 50), 100)

    def test_active_base_cannot_be_archived_or_detached_from_overrides(self):
        mapping = self.customer_type.pricelist_mapping_ids.filtered(
            lambda item: item.website_id == self.website
            and item.currency_id == self.base_pricelist.currency_id
        )
        with self.assertRaises(ValidationError):
            self.base_pricelist.write({"active": False})
        with self.assertRaises(ValidationError):
            mapping.write({"active": False})
        with self.assertRaises(ValidationError):
            mapping.unlink()

    def test_override_must_belong_to_commercial_company(self):
        contact = self.env["res.partner"].create({
            "name": "Pricing Override Contact",
            "parent_id": self.company.id,
        })
        with self.assertRaises(ValidationError):
            self.env["b2b.partner.pricelist.override"].create({
                "partner_id": contact.id,
                "website_id": self.website.id,
                "pricelist_id": self.lower_override.id,
            })


@tagged("post_install", "-at_install")
class TestB2BCustomerPricingSecurity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env["website"].search([], limit=1)
        cls.pricelist = cls.env["product.pricelist"].create({
            "name": "Pricing Security Base",
        })
        cls.customer_type = cls.env["b2b.customer.type"].create({
            "name": "Pricing Security Type",
        })
        cls.env["b2b.customer.type.pricelist"].create({
            "customer_type_id": cls.customer_type.id,
            "website_id": cls.website.id,
            "pricelist_id": cls.pricelist.id,
        })
        cls.company = cls.env["res.partner"].create({
            "name": "Pricing Security Company", "is_company": True,
        })
        cls.manager = mail_new_test_user(
            cls.env, login="customer-type-manager",
            groups="b2b_core.group_b2b_manager",
        )
        cls.price_manager = mail_new_test_user(
            cls.env, login="company-price-manager",
            groups="b2b_core.group_b2b_special_price_manager",
        )

    def test_manager_assigns_type_but_cannot_create_override(self):
        self.company.with_user(self.manager).write({
            "b2b_customer_type_id": self.customer_type.id,
        })
        with self.assertRaises(AccessError):
            self.env["b2b.partner.pricelist.override"].with_user(self.manager).create({
                "partner_id": self.company.id,
                "website_id": self.website.id,
                "pricelist_id": self.pricelist.id,
            })

    def test_price_manager_cannot_assign_customer_type(self):
        with self.assertRaises(AccessError):
            self.company.with_user(self.price_manager).write({
                "b2b_customer_type_id": self.customer_type.id,
            })
