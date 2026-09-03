import logging
from urllib.parse import urlparse

import werkzeug

from odoo import _, fields, http, tools
from odoo.addons.auth_signup.controllers.main import AuthSignupHome
from odoo.addons.auth_signup.models.res_users import SignupError
from odoo.exceptions import UserError, ValidationError
from odoo.http import request
from odoo.tools import email_normalize


_logger = logging.getLogger(__name__)


class PartnerHubAuth(AuthSignupHome):
    @staticmethod
    def _integer_param(value):
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    def _registration_options(self, qcontext):
        interest_parent = request.env.ref(
            "b2b_website.partner_category_product_interests",
            raise_if_not_found=False,
        )
        qcontext.update({
            "countries": request.env["res.country"].sudo().search([], order="name"),
            "customer_types": request.env["b2b.customer.type"].sudo().search(
                [("active", "=", True)], order="sequence, name"
            ),
            "product_interests": (
                request.env["res.partner.category"].sudo().search(
                    [("parent_id", "=", interest_parent.id)], order="name"
                ) if interest_parent else request.env["res.partner.category"]
            ),
            "terms_version": "2026-09",
        })
        for key in (
            "job_title", "company_name", "country_id", "company_phone", "mobile",
            "customer_type_id", "company_website", "product_interest_id", "terms",
        ):
            qcontext[key] = request.params.get(key)
        return qcontext

    @staticmethod
    def _account_exists(login):
        return bool(
            login
            and request.env["res.users"].sudo().with_context(active_test=False).search_count(
                request.env["res.users"]._get_login_domain(login),
                limit=1,
            )
        )

    def _validated_registration_values(self, qcontext):
        values = self._prepare_signup_values(qcontext)
        full_name = (qcontext.get("name") or "").strip()[:160]
        login = email_normalize((qcontext.get("login") or "").strip())
        job_title = (qcontext.get("job_title") or "").strip()[:160]
        company_name = (qcontext.get("company_name") or "").strip()[:200]
        company_phone = (qcontext.get("company_phone") or "").strip()[:64]
        mobile = (qcontext.get("mobile") or "").strip()[:64]
        company_website = (qcontext.get("company_website") or "").strip()[:500]
        if company_website and not urlparse(company_website).scheme:
            company_website = "https://" + company_website
        if company_website and urlparse(company_website).scheme not in ("http", "https"):
            raise ValidationError(_("Please enter a valid company website."))

        country = request.env["res.country"].sudo().browse(
            self._integer_param(qcontext.get("country_id"))
        ).exists()
        customer_type = request.env["b2b.customer.type"].sudo().browse(
            self._integer_param(qcontext.get("customer_type_id"))
        ).exists()
        if customer_type and not customer_type.active:
            customer_type = request.env["b2b.customer.type"]
        product_interest = request.env["res.partner.category"].sudo().browse(
            self._integer_param(qcontext.get("product_interest_id"))
        ).exists()
        interest_parent = request.env.ref(
            "b2b_website.partner_category_product_interests",
            raise_if_not_found=False,
        )
        if product_interest and product_interest.parent_id != interest_parent:
            raise ValidationError(_("Please select a valid product interest."))
        if not all((full_name, login, job_title, company_name, country, mobile, customer_type)):
            raise ValidationError(_("Please complete all required registration fields."))
        if qcontext.get("terms") != "1":
            raise ValidationError(_("Please accept the Terms of Use and Privacy Policy."))

        values.update({"name": full_name, "login": login, "email": login})
        application_values = {
            "website_id": request.website.id,
            "full_name": full_name,
            "job_title": job_title,
            "company_name": company_name,
            "country_id": country.id,
            "business_email": login,
            "company_phone": company_phone,
            "mobile": mobile,
            "customer_type_id": customer_type.id,
            "company_website": company_website,
            "product_interest_id": product_interest.id,
            "terms_accepted_at": fields.Datetime.now(),
            "terms_version": qcontext["terms_version"],
        }
        return values, application_values

    @http.route()
    def web_login(self, *args, **kw):
        response = super().web_login(*args, **kw)
        if (
            request.httprequest.method == "POST"
            and request.session.uid
            and not kw.get("remember")
        ):
            # Odoo normally persists its session cookie for the global session
            # lifetime. An unchecked Figma "Remember me" keeps it browser-only.
            request.future_response.set_cookie(
                "session_id", request.session.sid, httponly=True
            )
        return response

    @http.route()
    def web_auth_signup(self, *args, **kw):
        qcontext = self.get_auth_signup_qcontext()
        if qcontext.get("token"):
            return super().web_auth_signup(*args, **kw)
        if not qcontext.get("signup_enabled"):
            raise werkzeug.exceptions.NotFound()
        self._registration_options(qcontext)

        if "error" not in qcontext and request.httprequest.method == "POST":
            try:
                user_values, application_values = self._validated_registration_values(qcontext)
                with request.env.cr.savepoint():
                    if self._account_exists(user_values["login"]):
                        raise SignupError()
                    try:
                        user = request.env["res.users"].sudo()._signup_create_user(user_values)
                    except (SignupError, UserError) as error:
                        # A concurrent signup can pass the pre-check and still
                        # hit Odoo's native unique-account guard. Normalize it
                        # to the Partner Hub message without weakening the
                        # database-backed protection.
                        if self._account_exists(user_values["login"]):
                            raise SignupError() from error
                        raise
                    user.write({"active": False})
                    application = request.env["b2b.registration.application"].sudo().create({
                        **application_values,
                        "user_id": user.id,
                        "partner_id": user.partner_id.id,
                    })
                    application.action_send_verification_email()
                qcontext.update({
                    "message": _(
                        "Registration submitted. Check your email to verify your account before partner review."
                    ),
                    "signup_email": application.business_email,
                    "application_name": application.name,
                })
                qcontext.pop("password", None)
                qcontext.pop("confirm_password", None)
            except (UserError, ValidationError) as error:
                qcontext["error"] = error.args[0]
            except (SignupError, AssertionError, ValueError) as error:
                if self._account_exists(qcontext.get("login")):
                    qcontext["error"] = _(
                        "An account already uses this email. Sign in, reset the password, or resend verification."
                    )
                else:
                    _logger.warning("Partner registration failed: %s", error)
                    qcontext["error"] = _("Could not create a new account.")

        response = request.render("auth_signup.signup", qcontext)
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Content-Security-Policy"] = "frame-ancestors 'self'"
        return response

    @http.route(
        "/web/signup/verify",
        type="http",
        auth="public",
        website=True,
        methods=["GET"],
        sitemap=False,
    )
    def verify_registration_email(self, token=None, **kwargs):
        token = (token or "")[:128]
        application, status = request.env["b2b.registration.application"].sudo().verify_email_token(token)
        return request.render("b2b_website.registration_status", {
            "status": status,
            "application": application,
            "email": application.business_email if application else "",
            "no_index": True,
        })

    @http.route(
        "/web/signup/resend",
        type="http",
        auth="public",
        website=True,
        methods=["POST"],
        csrf=True,
        sitemap=False,
    )
    def resend_registration_email(self, email=None, **kwargs):
        normalized = email_normalize((email or "").strip())
        message = _("If this email has an unverified registration, a new verification link has been sent.")
        if normalized:
            application = request.env["b2b.registration.application"].sudo().search([
                ("business_email", "=", normalized),
                ("state", "in", ("awaiting_email", "expired")),
            ], order="create_date desc", limit=1)
            if application:
                try:
                    application.action_send_verification_email()
                except UserError:
                    pass
        return request.render("b2b_website.registration_status", {
            "status": "resent",
            "message": message,
            "email": normalized or "",
            "no_index": True,
        })

    @http.route("/register", type="http", auth="public", website=True, sitemap=False)
    def registration_alias(self, **kwargs):
        return request.redirect_query("/web/signup", kwargs)

    @http.route("/login", type="http", auth="public", website=True, sitemap=False)
    def login_alias(self, **kwargs):
        return request.redirect_query("/web/login", kwargs)
