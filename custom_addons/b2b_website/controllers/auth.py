import logging
import re
from urllib.parse import urlparse

import werkzeug

from odoo import _, fields, http, tools
from odoo.addons.auth_signup.controllers.main import AuthSignupHome
from odoo.addons.auth_signup.models.res_users import SignupError
from odoo.addons.phone_validation.tools import phone_validation
from odoo.exceptions import UserError, ValidationError
from odoo.http import request
from odoo.tools import email_normalize


_logger = logging.getLogger(__name__)


class PartnerHubAuth(AuthSignupHome):
    @staticmethod
    def _human_validation_error():
        return _(
            "Human verification could not be completed. Please refresh the page and try again."
        )

    @staticmethod
    def _set_auth_response_headers(response):
        response.headers["Cache-Control"] = "no-cache"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Content-Security-Policy"] = "frame-ancestors 'self'"
        return response

    def _render_auth_template(self, template, qcontext):
        return self._set_auth_response_headers(request.render(template, qcontext))

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
        countries = request.env["res.country"].sudo().with_context(lang="en_US").search([], order="name")
        qcontext.update({
            "countries": countries,
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
            "company_phone_country", "mobile_country",
        ):
            qcontext[key] = request.params.get(key)
        default_phone_country = countries.filtered(lambda country: country.code == "US")[:1]
        if default_phone_country:
            for field_name in ("company_phone_country", "mobile_country"):
                qcontext[f"{field_name}_defaulted"] = not qcontext[field_name]
                qcontext[field_name] = qcontext[field_name] or str(default_phone_country.id)
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
        raw_login = (qcontext.get("login") or "").strip()
        login = email_normalize(raw_login)
        if raw_login and not login:
            qcontext["login_error"] = _(
                "Please enter a valid business email address, such as name@company.com."
            )
            raise ValidationError(qcontext["login_error"])
        job_title = (qcontext.get("job_title") or "").strip()[:160]
        company_name = (qcontext.get("company_name") or "").strip()[:200]
        company_phone = self._registration_phone(qcontext, "company_phone")
        mobile = self._registration_phone(qcontext, "mobile")
        company_website = self._registration_website(qcontext.get("company_website"))

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

    @staticmethod
    def _registration_website(value):
        value = (value or "").strip()
        if not value:
            return ""
        if "://" not in value:
            value = "https://" + value
        try:
            parsed = urlparse(value)
            host = (parsed.hostname or "").encode("idna").decode("ascii")
            labels = host.split(".")
            valid = (
                len(value) <= 500 and not re.search(r"[\s\\]", value)
                and parsed.scheme in ("http", "https")
                and not parsed.username and not parsed.password and "@" not in parsed.netloc
                and len(host) <= 253 and len(labels) >= 2
                and all(re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", label) for label in labels)
                and (re.fullmatch(r"[a-zA-Z]{2,63}", labels[-1]) or labels[-1].startswith("xn--"))
                and (parsed.port is None or 1 <= parsed.port <= 65535)
            )
        except (ValueError, UnicodeError):
            valid = False
        if not valid:
            raise ValidationError(_("Please enter a valid company website, such as www.company.com."))
        return value

    def _registration_phone(self, qcontext, field):
        value = (qcontext.get(field) or "").strip()
        if not value:
            return ""
        message = _("Please enter a valid company phone number with its country code.") if field == "company_phone" else _("Please enter a valid mobile number with its country code.")
        if len(value) > 64 or not re.fullmatch(r"\+?[0-9\s().-]+", value):
            raise ValidationError(message)
        selected = qcontext.get(field + "_country") or qcontext.get("country_id")
        country = request.env["res.country"].sudo().browse(self._integer_param(selected)).exists()
        if not country or not country.phone_code:
            raise ValidationError(message)
        value = re.sub(r"[\s().-]", "", value)
        if value.startswith("00"):
            value = "+" + value[2:]
        # Some Odoo country codes include the NANP area code (e.g. +1684).
        if not value.startswith("+") and len(str(country.phone_code)) > 3 and len(value) == 7:
            value = "+" + str(country.phone_code) + value
        try:
            return phone_validation.phone_format(value, country.code, country.phone_code, force_format="E164")
        except UserError:
            raise ValidationError(message) from None

    @http.route()
    def web_login(self, *args, **kw):
        try:
            response = super().web_login(*args, **kw)
        except (UserError, ValidationError):
            # Odoo validates password logins before authentication.  Keep a
            # failed or expired Turnstile challenge inside the branded login
            # page instead of letting the validation exception reach the
            # generic HTTP error page.
            qcontext = self.get_auth_signup_config()
            qcontext.update({
                "login": (request.params.get("login") or "").strip(),
                "redirect": request.params.get("redirect"),
                "error": self._human_validation_error(),
            })
            return self._render_auth_template("web.login", qcontext)
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

    @http.route(captcha=None)
    def web_auth_signup(self, *args, **kw):
        qcontext = self.get_auth_signup_qcontext()
        if qcontext.get("token"):
            if request.httprequest.method == "POST":
                try:
                    request.env["ir.http"]._verify_request_recaptcha_token("signup")
                except (UserError, ValidationError):
                    qcontext["error"] = self._human_validation_error()
                    return self._render_auth_template("auth_signup.signup", qcontext)
            return super().web_auth_signup(*args, **kw)
        if not qcontext.get("signup_enabled"):
            raise werkzeug.exceptions.NotFound()
        self._registration_options(qcontext)

        if "error" not in qcontext and request.httprequest.method == "POST":
            try:
                try:
                    request.env["ir.http"]._verify_request_recaptcha_token("signup")
                except (UserError, ValidationError):
                    qcontext["human_validation_failed"] = True
                    raise
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
                if qcontext.pop("human_validation_failed", False):
                    qcontext["error"] = self._human_validation_error()
                elif not qcontext.get("login_error"):
                    qcontext["error"] = error.args[0]
            except (SignupError, AssertionError, ValueError) as error:
                if self._account_exists(qcontext.get("login")):
                    qcontext["error"] = _(
                        "An account already uses this email. Sign in, reset the password, or resend verification."
                    )
                else:
                    _logger.warning("Partner registration failed: %s", error)
                    qcontext["error"] = _("Could not create a new account.")

        return self._render_auth_template("auth_signup.signup", qcontext)

    @http.route(captcha=None)
    def web_auth_reset_password(self, *args, **kw):
        if request.httprequest.method == "POST":
            try:
                request.env["ir.http"]._verify_request_recaptcha_token(
                    "password_reset"
                )
            except (UserError, ValidationError):
                qcontext = self.get_auth_signup_qcontext()
                qcontext["error"] = self._human_validation_error()
                return self._render_auth_template(
                    "auth_signup.reset_password", qcontext
                )
        return super().web_auth_reset_password(*args, **kw)

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
