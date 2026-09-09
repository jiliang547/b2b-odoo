from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    answers = {
        "b2b_website.faq_price_visibility": (
            "<p>Price visibility is controlled by your company approval, customer "
            "segment, and assigned company pricing. Contact sales if your approved "
            "account still does not show prices.</p>"
        ),
        "b2b_website.faq_moq": (
            "<p>MOQ is the minimum order quantity for the selected product and "
            "configuration. The quantity control follows the applicable unit and "
            "pricing rule.</p>"
        ),
        "b2b_website.faq_sample_cost": (
            "<p>Yes. After approval, the sample request becomes a quotation. Review "
            "the quoted product, tax, and delivery amounts and complete payment "
            "before fulfilment.</p>"
        ),
    }
    for xmlid, answer in answers.items():
        record = env.ref(xmlid, raise_if_not_found=False)
        if record:
            record.write({"answer": answer})
