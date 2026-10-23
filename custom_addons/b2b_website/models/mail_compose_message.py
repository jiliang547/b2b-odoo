"""Keep the business sender mailbox separate from the authenticated author."""
from odoo import models

from .customer_message_policy import CUSTOMER_MESSAGE_SOURCES


class MailComposeMessage(models.TransientModel):
    _inherit = "mail.compose.message"

    def _prepare_mail_values_static(self):
        values = super()._prepare_mail_values_static()
        subtype = self.env["mail.message.subtype"].browse(values.get("subtype_id"))
        if (self.composition_mode == "comment" and self.template_id
                and self.model in CUSTOMER_MESSAGE_SOURCES
                and self.message_type in ("comment", "auto_comment")
                and subtype and not subtype.internal and self.env.user._is_internal()):
            # Native template rendering can infer a partner author from From.
            # A legal seller's company contact has partner_share=True without
            # being another customer. Attribute outgoing business templates to
            # the internal actor; keep the template's From address untouched.
            # Source access, public recipient isolation and the native mail
            # transport are deliberately unchanged. Incoming customer mail and
            # direct message_post(author_id=...) never pass through this rule.
            values["author_id"] = self.env.user.partner_id.id
        return values
