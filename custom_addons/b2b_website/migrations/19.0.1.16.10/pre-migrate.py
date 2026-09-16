def migrate(cr, version):
    # These owned child views used the production indicator removed by this
    # release. Suspend them until their new XML definitions load, so upgrading
    # the parent does not validate obsolete XPath expressions midway through.
    cr.execute("""
        UPDATE ir_ui_view SET active = FALSE
        WHERE id IN (
            SELECT res_id FROM ir_model_data
            WHERE model = 'ir.ui.view' AND
                ((module = 'b2b_website' AND name = 'collection_summary_status')
                 OR (module = 'b2b_multicompany' AND name = 'external_collection_notice'))
        )
    """)
