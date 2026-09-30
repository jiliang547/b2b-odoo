import json
import logging
import hashlib

from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)


class PartnerAI(http.Controller):
    @http.route("/ai-assistant", type="http", auth="public", website=True, sitemap=False)
    def assistant(self, **kw):
        return request.redirect("/?ai=open")

    @http.route("/ai-assistant/bootstrap", type="http", auth="public", website=True, sitemap=False)
    def bootstrap(self, **kw):
        user, website = request.env.user, request.website
        audience = request.env["b2b.ai.session"]._audience(user, website)
        identity = hashlib.sha256(f"{request.session.sid}:{audience}".encode()).hexdigest()
        return request.make_json_response({
            "identity": identity, "signed_in": not user._is_public(),
            "enabled": website.sudo().b2b_ai_enabled, "ready": website._b2b_ai_ready() == "ready",
            "csrf": request.csrf_token(),
        }, headers=[("Cache-Control", "no-store")])

    @http.route("/ai-assistant/api", type="http", auth="public", website=True,
                methods=["POST"], csrf=True, sitemap=False)
    def api(self, action="", payload="{}", **kw):
        headers = [("Cache-Control", "no-store")]
        if request.env.user._is_public():
            return request.make_json_response({"ok": False, "message": "Your session has expired. Please sign in again."}, headers=headers, status=401)
        try:
            if len(payload) > 12000:
                raise ValidationError("This request is too large.")
            values = json.loads(payload)
            if not isinstance(values, dict):
                raise ValidationError("Invalid request.")
            service = request.env["b2b.ai.service"]
            website = request.website
            with request.env.cr.savepoint():
                if action == "list":
                    data = service._list(website)
                elif action == "new":
                    data = service._view(service._new(website), website)
                else:
                    session = service._owned(values.get("session_id"), website)
                    if action == "get":
                        data = service._view(session, website)
                    elif action == "ask":
                        data = service._enqueue(session, website, values.get("text"), values.get("key"), values.get("revision"))
                    elif action == "facts":
                        service._update_facts(session, website, values.get("revision"), values.get("facts"))
                        data = service._view(session, website)
                    elif action == "delete":
                        service._lock(website)
                        # Archive to retain usage accounting; deleting a project
                        # must never reset the customer's daily request budget.
                        session.active = False
                        data = {}
                    else:
                        raise ValidationError("Unknown assistant action.")
            return request.make_json_response({"ok": True, "data": data}, headers=headers)
        except (AccessError, UserError, ValidationError) as exc:
            return request.make_json_response({"ok": False, "message": str(exc)}, headers=headers, status=400)
        except (ValueError, TypeError):
            return request.make_json_response({"ok": False, "message": "Invalid request. Please reload this page."}, headers=headers, status=400)
        except Exception as exc:
            _logger.warning("Partner Hub AI route failed (%s)", type(exc).__name__)
            return request.make_json_response({"ok": False, "message": "The assistant could not complete this request. Please try again or contact our team."}, headers=headers, status=503)
