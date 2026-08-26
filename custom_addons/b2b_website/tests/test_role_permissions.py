from odoo import Command
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestB2BNativeRoleBundles(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.after_sales = mail_new_test_user(
            cls.env,
            login="b2b-role-after-sales",
            groups="b2b_core.group_b2b_after_sales",
        )
        cls.pmc = mail_new_test_user(
            cls.env,
            login="b2b-role-pmc",
            groups="b2b_core.group_b2b_pmc",
        )
        cls.helpdesk_team = cls.env["helpdesk.team"].create({
            "name": "B2B Role Test Team",
            "member_ids": [Command.link(cls.after_sales.id)],
        })
        cls.warehouse = cls.env["stock.warehouse"].search([], limit=1)

    def test_after_sales_gets_helpdesk_user_without_manager_permissions(self):
        self.assertTrue(self.after_sales.has_group("b2b_core.group_b2b_operator"))
        self.assertTrue(self.after_sales.has_group("helpdesk.group_helpdesk_user"))
        self.assertFalse(self.after_sales.has_group("helpdesk.group_helpdesk_manager"))
        self.assertFalse(self.after_sales.has_group("stock.group_stock_user"))
        self.assertFalse(self.after_sales.has_group("b2b_core.group_b2b_manager"))

        ticket = self.env["helpdesk.ticket"].with_user(self.after_sales).create({
            "name": "Authorized After-sales Ticket",
            "team_id": self.helpdesk_team.id,
        })
        self.assertTrue(ticket.exists())
        with self.assertRaises(AccessError):
            self.env["stock.picking"].with_user(self.after_sales).create({
                "picking_type_id": self.warehouse.int_type_id.id,
                "location_id": self.warehouse.lot_stock_id.id,
                "location_dest_id": self.warehouse.lot_stock_id.id,
            })

    def test_pmc_gets_inventory_user_without_high_risk_manager_permissions(self):
        self.assertTrue(self.pmc.has_group("b2b_core.group_b2b_operator"))
        self.assertTrue(self.pmc.has_group("stock.group_stock_user"))
        self.assertFalse(self.pmc.has_group("stock.group_stock_manager"))
        self.assertFalse(self.pmc.has_group("helpdesk.group_helpdesk_user"))
        self.assertFalse(self.pmc.has_group("b2b_core.group_b2b_manager"))
        purchase_user = self.env.ref(
            "purchase.group_purchase_user", raise_if_not_found=False
        )
        if purchase_user:
            self.assertFalse(self.pmc.has_group("purchase.group_purchase_user"))

        picking = self.env["stock.picking"].with_user(self.pmc).create({
            "picking_type_id": self.warehouse.int_type_id.id,
            "location_id": self.warehouse.lot_stock_id.id,
            "location_dest_id": self.warehouse.lot_stock_id.id,
        })
        self.assertTrue(picking.exists())
        with self.assertRaises(AccessError):
            self.env["helpdesk.ticket"].with_user(self.pmc).create({
                "name": "Forbidden PMC Ticket",
                "team_id": self.helpdesk_team.id,
            })
