"""Keep customer links and tracking metadata while removing a reserved-name clash."""
import json
import re


def migrate(cr, version):
    cr.execute("""SELECT column_name FROM information_schema.columns
        WHERE table_name='b2b_registration_application'
        AND column_name IN ('company_id', 'resolved_partner_id')""")
    columns = {row[0] for row in cr.fetchall()}
    if 'company_id' not in columns:
        return
    if 'resolved_partner_id' in columns:
        raise RuntimeError('Both registration customer columns exist; review migration before continuing.')
    cr.execute('ALTER TABLE b2b_registration_application RENAME COLUMN company_id TO resolved_partner_id')
    cr.execute("""UPDATE ir_model_fields SET name='resolved_partner_id'
        WHERE model='b2b.registration.application' AND name='company_id'""")
    cr.execute("""UPDATE ir_model_data SET name='field_b2b_registration_application__resolved_partner_id'
        WHERE module='b2b_website' AND name='field_b2b_registration_application__company_id'
        AND model='ir.model.fields'""")
    # Also preserve saved/customized registration views. Word boundaries leave
    # website_id.company_id and unrelated prefixed fields untouched below.
    cr.execute("SELECT id, arch_db FROM ir_ui_view WHERE model='b2b.registration.application'")
    for view_id, arch in cr.fetchall():
        updated = {lang: re.sub(r'(?<![\w.])company_id\b', 'resolved_partner_id', text)
                   for lang, text in arch.items()}
        if updated != arch:
            cr.execute('UPDATE ir_ui_view SET arch_db=%s::jsonb WHERE id=%s', (json.dumps(updated), view_id))
