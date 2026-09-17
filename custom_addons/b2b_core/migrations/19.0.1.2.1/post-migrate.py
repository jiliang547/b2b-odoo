from odoo import SUPERUSER_ID, Command, api


def migrate(cr, version):
    """Normalize pure Marketing users without breaking combined roles."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    marketing = env.ref("b2b_core.group_b2b_marketing_media")
    b2b_product = env.ref("b2b_core.group_b2b_product_manager")
    native_product = env.ref("product.group_product_manager")
    users = env["res.users"].with_context(active_test=False).search([
        ("all_group_ids", "in", marketing.id),
        ("group_ids", "in", native_product.id),
    ])
    for user in users.filtered(lambda item: b2b_product not in item.group_ids):
        user.write({"group_ids": [Command.unlink(native_product.id)]})
