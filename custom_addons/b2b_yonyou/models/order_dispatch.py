"""Small durable send ledger; no UI or public mutation API.

Independent commits are intentional: the send claim must survive rollback or
process termination after an ERP write. No business record is committed here.
There are no foreign keys to records locked by the job transaction.
"""
from odoo import fields, models


class OrderDispatch(models.Model):
    _name = 'b2b.yonyou.order.dispatch'
    _description = 'ERP Order Submission Guard'
    _log_access = False

    key = fields.Char(required=True)
    remote_id = fields.Char()
    _key_unique = models.Constraint('UNIQUE(key)', 'An ERP order may only be submitted once.')

    def _claim(self, key):
        with self.env.registry.cursor() as cr:
            cr.execute('INSERT INTO b2b_yonyou_order_dispatch (key) VALUES (%s) '
                       'ON CONFLICT (key) DO NOTHING RETURNING id', [key])
            claimed = bool(cr.fetchone())
            cr.commit()
        return claimed

    def _lookup(self, key):
        with self.env.registry.cursor() as cr:
            cr.execute('SELECT remote_id FROM b2b_yonyou_order_dispatch WHERE key=%s', [key])
            row = cr.fetchone()
        return (bool(row), row[0] if row else False)

    def _remember(self, key, remote_id):
        with self.env.registry.cursor() as cr:
            cr.execute('UPDATE b2b_yonyou_order_dispatch SET remote_id=%s WHERE key=%s',
                       [str(remote_id), key])
            cr.commit()

    def init(self):
        # Older workers may have sent these payloads without saving the result.
        # Prefer manual investigation to blindly sending an ambiguous legacy job.
        self.env.cr.execute('''
            INSERT INTO b2b_yonyou_order_dispatch (key)
            SELECT s.yonyou_key FROM b2b_integration_job j
            JOIN sale_order s ON j.reference_model='sale.order' AND j.reference_id=s.id
            WHERE j.yonyou_order AND j.yonyou_payload IS NOT NULL AND s.yonyou_key IS NOT NULL
            ON CONFLICT (key) DO NOTHING
        ''')
