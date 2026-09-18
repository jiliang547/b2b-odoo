"""Portal address adapter for customer-company routed website orders."""

from odoo.addons.website_sale.controllers.main import WebsiteSale


class PartnerHubMultiCompanyWebsiteSale(WebsiteSale):

    def _complete_address_values(
        self, address_values, *args, order_sudo=False, **kwargs
    ):
        super()._complete_address_values(
            address_values, *args, order_sudo=order_sudo, **kwargs
        )
        if (
            order_sudo
            and order_sudo.website_id.b2b_multicompany_enabled
            and not order_sudo._is_anonymous_cart()
        ):
            # External customer addresses are shared master data. Their legal
            # seller is derived from the commercial customer's brand/explicit
            # assignment and is snapshotted on the order, never from here.
            address_values['company_id'] = False
