def migrate(cr, version):
    # All pre-mode routed orders used native supply. Preserve their owner;
    # websites keep that default only if they already have routed history.
    cr.execute("""
        UPDATE sale_order so SET b2b_fulfilment_mode='odoo',
            b2b_fulfilment_factory_id=w.b2b_factory_company_id
        FROM website w WHERE so.website_id=w.id AND so.b2b_routed_company
          AND so.b2b_fulfilment_mode IS NULL
    """)
    cr.execute("""
        UPDATE website w SET b2b_fulfilment_mode='odoo'
        WHERE EXISTS (SELECT 1 FROM sale_order so WHERE so.website_id=w.id
                      AND so.b2b_fulfilment_mode='odoo')
    """)
