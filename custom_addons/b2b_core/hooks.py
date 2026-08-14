def uninstall_hook(env):
    """Restore the native Website Sale rule modified by this module."""
    rule = env.ref("website_sale.product_template_public", raise_if_not_found=False)
    if rule:
        rule.domain_force = "[('website_published', '=', True), ('sale_ok', '=', True)]"
