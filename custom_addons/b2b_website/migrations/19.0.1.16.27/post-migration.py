def migrate(cr, version):
    # Existing service requests were approved against the mandatory round-trip
    # workflow. Preserve that agreement, including closed and pending cases.
    cr.execute("""
        UPDATE helpdesk_ticket SET b2b_service_route = 'roundtrip'
        WHERE b2b_request_type IS NOT NULL
    """)
    from odoo import api, SUPERUSER_ID
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid, label in [('service_processing', 'In Progress'), ('service_shipped', 'Dispatched')]:
        stage = env.ref('b2b_website.' + xmlid, raise_if_not_found=False)
        if stage:
            stage.with_context(lang='en_US').name = label
