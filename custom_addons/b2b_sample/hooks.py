def post_init_hook(env):
    for sample in env["b2b.sample.request"].sudo().search([]):
        if sample.contact_id and sample.contact_id not in sample.message_partner_ids:
            sample.message_subscribe(partner_ids=sample.contact_id.ids)
