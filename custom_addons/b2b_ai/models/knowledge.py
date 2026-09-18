import base64
import hashlib

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import html2plaintext


class AISource(models.Model):
    _name = "b2b.ai.source"
    _description = "Partner Hub Authorized AI Source"
    _order = "name, id"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    website_id = fields.Many2one("website", required=True, ondelete="cascade")
    product_document_id = fields.Many2one("product.document", ondelete="cascade")
    faq_id = fields.Many2one("b2b.faq.item", string="FAQ Question", ondelete="cascade")
    published = fields.Boolean(string="Approved for Customer AI", default=False)
    native_source_id = fields.Many2one("ai.agent.source", readonly=True, copy=False, ondelete="set null")
    indexed_checksum = fields.Char(readonly=True, copy=False)
    index_state = fields.Char(compute="_compute_index_state")

    @api.constrains("product_document_id", "faq_id", "website_id")
    def _check_reference(self):
        for source in self:
            if bool(source.product_document_id) == bool(source.faq_id):
                raise ValidationError(_("Choose exactly one existing product document or FAQ."))
            if source.faq_id.website_id and source.faq_id.website_id != source.website_id:
                raise ValidationError(_("The FAQ belongs to another website."))

    def _current_checksum(self):
        self.ensure_one()
        if self.product_document_id:
            return self.product_document_id.ir_attachment_id.checksum or ""
        text = (self.faq_id.question or "") + html2plaintext(self.faq_id.answer or "")
        return hashlib.sha256(text.encode()).hexdigest()

    def _compute_index_state(self):
        for source in self:
            if not source.published:
                source.index_state = _("Not published")
            elif source.faq_id:
                source.index_state = _("Live FAQ (no indexing required)")
            elif source.indexed_checksum != source._current_checksum():
                source.index_state = _("Index required / source changed")
            else:
                source.index_state = source.native_source_id.status or _("Index required")

    def action_index(self):
        self.check_access("write")
        for source in self:
            if not source.published or not source.active:
                raise UserError(_("Approve this source for Customer AI before indexing."))
            if source.faq_id:
                continue
            if source.website_id._b2b_ai_ready() != "ready":
                raise UserError(_("Save your OpenAI key in Native AI Settings. For a copied test database, authorize AI calls in Website AI Configuration before indexing."))
            document = source.product_document_id
            original = document.ir_attachment_id
            if document.type != "binary" or original.mimetype not in ("application/pdf", "text/plain"):
                raise UserError(_("This release indexes text PDFs and plain text files only."))
            if original.file_size > 20 * 1024 * 1024 or not original.file_size:
                raise UserError(_("Choose a non-empty file up to 20 MB."))
            # Native create_from_attachments reparents files. Never pass the
            # original product attachment: retain product ACLs and ownership.
            attachment = self.env["ir.attachment"].create({
                "name": original.name, "datas": base64.b64encode(original.raw),
                "mimetype": original.mimetype, "public": False,
            })
            native = self.env["ai.agent.source"].create_from_attachments(
                attachment.ids, source.website_id.b2b_ai_agent_id.id)
            if source.native_source_id:
                source.native_source_id.is_active = False
            source.write({"native_source_id": native.id, "indexed_checksum": original.checksum})
        return True

    def _allowed_for(self, user, website):
        service = self.env["b2b.product.service"].with_user(user)
        allowed = self.browse()
        for source in self.sudo():
            if not source.active or not source.published or source.website_id != website:
                continue
            if source.product_document_id and service.document_is_allowed(
                    source.product_document_id, website=website.with_user(user)):
                allowed |= source
            elif (source.faq_id and source.faq_id.active and source.faq_id.published
                  and source.faq_id.category_id.active
                  and (not source.faq_id.website_id or source.faq_id.website_id == website)):
                allowed |= source
        return allowed


class FAQItem(models.Model):
    _inherit = "b2b.faq.item"
    # The original FAQ model has no name field. Native many2one selectors
    # otherwise show only "b2b.faq.item,ID", which operators cannot identify.
    _rec_name = "question"
