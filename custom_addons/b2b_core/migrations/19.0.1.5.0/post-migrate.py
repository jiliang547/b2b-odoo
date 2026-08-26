def migrate(cr, version):
    """Keep Partner Hub policy only on each commercial entity."""
    cr.execute("""
        DELETE FROM b2b_segment_partner_rel relation
        USING res_partner partner
        WHERE relation.partner_id = partner.id
          AND partner.commercial_partner_id != partner.id
    """)
    cr.execute("""
        UPDATE res_partner
           SET b2b_approved = FALSE,
               b2b_approval_date = NULL,
               b2b_approved_by_id = NULL,
               b2b_erp_customer_id = NULL
         WHERE commercial_partner_id != id
           AND (
                b2b_approved
                OR b2b_approval_date IS NOT NULL
                OR b2b_approved_by_id IS NOT NULL
                OR b2b_erp_customer_id IS NOT NULL
           )
    """)
