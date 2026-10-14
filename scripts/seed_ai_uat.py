"""Run with the Odoo shell ONLY in the named disposable AI database."""
assert env.cr.dbname == "b2b_ai_test_20260918", "Never run UAT seeding in a customer database"
from odoo import Command

website = env["website"].search([], limit=1)
website.write({"name": "Partner Hub AI - Isolated UAT", "b2b_ai_enabled": True,
               "b2b_ai_agent_id": env.ref("b2b_ai.customer_agent").id})
login = "ai-uat@example.test"
user = env["res.users"].search([("login", "=", login)])
if not user:
    company = env["res.partner"].create({"name": "AI UAT Customer", "is_company": True, "b2b_approved": True})
    partner = env["res.partner"].create({"name": "AI UAT Contact", "email": login, "parent_id": company.id})
    user = env["res.users"].with_context(no_reset_password=True).create({
        "name": "AI UAT Customer", "login": login, "password": "AI-UAT-only-20260918!",
        "partner_id": partner.id, "group_ids": [Command.set([env.ref("base.group_portal").id])], "lang": "en_US"})
product = env["product.template"].search([("b2b_model_number", "=", "AI-UAT-CS1")], limit=1)
if not product:
    product = env["product.template"].create({"name": "UAT Ceiling Speaker", "b2b_model_number": "AI-UAT-CS1",
        "description_sale": "A ceiling speaker for indoor paging applications. Confirm system requirements with an engineer.",
        "sale_ok": True, "is_published": True, "b2b_visibility_mode": "all", "list_price": 55, "b2b_default_moq": 2})
category = env["b2b.faq.category"].search([("name", "=", "AI UAT Technical")], limit=1)
if not category:
    category = env["b2b.faq.category"].create({"name": "AI UAT Technical", "website_id": website.id})
    faq = env["b2b.faq.item"].create({"question": "How do I connect Dante equipment?", "answer": "<p>Check the product manual for supported network settings. Confirm the exact product model before connecting Dante equipment.</p>", "category_id": category.id})
    env["b2b.ai.source"].create({"name": "UAT Dante connection guidance", "website_id": website.id, "faq_id": faq.id, "published": True})
env.cr.commit()
admin_login = "ai-admin@example.test"
if not env["res.users"].search_count([("login", "=", admin_login)]):
    env["res.users"].with_context(no_reset_password=True).create({"name": "AI UAT Administrator",
        "login": admin_login, "password": "AI-admin-UAT-20260918!", "lang": "en_US",
        "group_ids": [Command.set([env.ref("base.group_system").id])]})
env.cr.commit()
print("Isolated UAT fixtures ready. No live customer records or API keys modified.")
