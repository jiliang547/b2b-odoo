from odoo import Command
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.tests import TransactionCase


class SampleCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.partner"].create({
            "name": "Sample Customer", "is_company": True, "b2b_approved": True
        })
        cls.contact = cls.env["res.partner"].create({
            "name": "Sample Contact", "parent_id": cls.company.id, "email": "sample@example.com"
        })
        cls.portal_user = mail_new_test_user(
            cls.env, login="sample-portal", groups="base.group_portal", partner_id=cls.contact.id
        )
        cls.product = cls.env["product.product"].create({
            "name": "Sample Product",
            "sale_ok": True,
            "is_published": True,
            "b2b_visibility_mode": "approved",
        })

    def sample_values(self):
        return {
            "contact_name": "Project Engineer",
            "company_name": "Sample Customer",
            "email": "engineer@example.com",
            "phone": "+1 555 0100",
            "shipping_address": "1 Project Street",
            "reason": "Evaluation for a meeting room project",
            "line_ids": [Command.create({
                "product_id": self.product.id,
                "quantity": 1,
                "uom_id": self.product.uom_id.id,
            })],
        }
