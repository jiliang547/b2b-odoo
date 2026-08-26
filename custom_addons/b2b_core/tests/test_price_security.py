from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestB2BPriceSecurity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product_manager = mail_new_test_user(
            cls.env,
            login="b2b-product-no-price",
            groups="b2b_core.group_b2b_product_manager",
        )
        cls.price_manager = mail_new_test_user(
            cls.env,
            login="b2b-price-manager",
            groups="b2b_core.group_b2b_special_price_manager",
        )
        cls.marketing = mail_new_test_user(
            cls.env,
            login="b2b-marketing-media",
            groups="b2b_core.group_b2b_marketing_media",
        )
        cls.product = cls.env["product.template"].create({"name": "Price Guard Product"})

    def test_product_manager_cannot_change_sales_price(self):
        with self.assertRaises(AccessError):
            self.product.with_user(self.product_manager).write({"list_price": 999})

    def test_product_manager_bundle_can_change_product_master_data(self):
        self.product.with_user(self.product_manager).write({"name": "Updated Product"})
        self.assertEqual(self.product.name, "Updated Product")

    def test_price_manager_can_change_sales_price(self):
        self.product.with_user(self.price_manager).write({"list_price": 123})
        self.assertEqual(self.product.list_price, 123)

    def test_price_manager_cannot_change_product_master_data(self):
        with self.assertRaises(AccessError):
            self.product.with_user(self.price_manager).write({"name": "Forbidden"})

    def test_product_manager_cannot_create_pricelist_rule(self):
        pricelist = self.env["product.pricelist"].create({"name": "Guarded Pricelist"})
        with self.assertRaises(AccessError):
            self.env["product.pricelist.item"].with_user(self.product_manager).create({
                "pricelist_id": pricelist.id,
                "compute_price": "fixed",
                "fixed_price": 1,
            })

    def test_price_manager_can_create_pricelist_rule_without_product_role(self):
        pricelist = self.env["product.pricelist"].with_user(self.price_manager).create({
            "name": "Authorized Pricelist",
        })
        item = self.env["product.pricelist.item"].with_user(self.price_manager).create({
            "pricelist_id": pricelist.id,
            "compute_price": "fixed",
            "fixed_price": 12,
        })
        self.assertTrue(item.exists())

    def test_marketing_can_manage_native_product_media(self):
        image = self.env["product.image"].with_user(self.marketing).create({
            "name": "Marketing Image",
            "product_tmpl_id": self.product.id,
        })
        image.with_user(self.marketing).write({"name": "Updated Image"})
        image.with_user(self.marketing).unlink()

    def test_marketing_can_manage_native_product_documents(self):
        document = self.env["product.document"].with_user(self.marketing).create({
            "name": "Marketing Manual.txt",
            "datas": b"VUF0IE1hbnVhbA==",
            "res_model": "product.template",
            "res_id": self.product.id,
        })
        document.with_user(self.marketing).write({"name": "Updated Manual.txt"})
        document.with_user(self.marketing).unlink()
