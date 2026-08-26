from odoo import SUPERUSER_ID, Command, api


def migrate(cr, version):
    """Normalize the role graph without changing explicit user assignments."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    operator = env.ref("b2b_core.group_b2b_operator")
    manager = env.ref("b2b_core.group_b2b_manager")
    price_manager = env.ref("b2b_core.group_b2b_special_price_manager")
    product_manager = env.ref("b2b_core.group_b2b_product_manager")
    native_contacts = env.ref("base.group_partner_manager")
    native_product = env.ref("product.group_product_manager")
    native_settings = env.ref("base.group_system")

    manager.write({
        "implied_ids": [
            Command.link(operator.id),
            Command.link(native_contacts.id),
        ],
    })
    price_manager.write({
        "implied_ids": [
            Command.link(operator.id),
            Command.link(native_contacts.id),
            Command.unlink(manager.id),
        ],
    })
    product_manager.write({
        "implied_ids": [
            Command.link(operator.id),
            Command.link(native_product.id),
        ],
    })
    native_settings.write({
        "implied_ids": [Command.unlink(price_manager.id)],
    })
