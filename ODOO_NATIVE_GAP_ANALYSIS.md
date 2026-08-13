# Odoo 19 Native Gap Analysis

Status: **Approved and implemented; Odoo.sh validation pending**

Baseline: Lucky Tone Partner Hub V4.1 Final

Reviewed: 2026-08-13

## Decision rule

Every feature follows this order:

1. configure an Odoo 19 native capability;
2. inherit the native model, view, controller or template when a small gap
   remains;
3. create a custom model only when the first two options cannot represent the
   business process safely.

`NATIVE` means configuration or presentation work only. `EXTENSION` means an
Odoo-native source of truth with a small inherited field, rule, service or UI
layer. `CUSTOM` means a Partner Hub-specific model justified below.

## Capability analysis

| Business capability | Odoo 19 native capability | Result | Proposed implementation | Type | Official evidence |
|---|---|---:|---|---|---|
| Customer and contacts | Contacts / `res.partner` | Meets | Reuse existing companies and contacts | NATIVE | [Users and portal](https://www.odoo.com/documentation/19.0/applications/general/users.html) |
| Portal identity | Portal / customer accounts | Meets | Invitation-only portal; separate customer and employee entry | NATIVE | [Customer accounts](https://www.odoo.com/documentation/19.0/applications/websites/ecommerce/customer_accounts.html), [Portal access](https://www.odoo.com/documentation/19.0/applications/general/users/user_portals/portal_access.html) |
| B2B approval | No dedicated Partner Hub approval flag | Gap | Add tracked `b2b_approved` to `res.partner`; approval method restricted to manager role | EXTENSION | [Security](https://www.odoo.com/documentation/19.0/developer/reference/backend/security.html) |
| Customer segment | Contacts categories do not provide deterministic Partner Hub visibility semantics | Gap | Create configurable `b2b.customer.segment`; link it to commercial partners | CUSTOM taxonomy | [ORM](https://www.odoo.com/documentation/19.0/developer/reference/backend/orm.html) |
| Product master and variants | `product.template` / `product.product` | Meets | Reuse Products; no B2B product master | NATIVE | [Products](https://www.odoo.com/documentation/19.0/applications/websites/ecommerce/configuration/products.html) |
| Website categories | `product.public.category` | Meets | Reuse native eCommerce categories | NATIVE | [Products](https://www.odoo.com/documentation/19.0/applications/websites/ecommerce/configuration/products.html) |
| Brand filter | No stable standard product-brand taxonomy identified in Odoo 19 core | Gap | Add a small configurable brand taxonomy linked to `product.template`; verify installed Enterprise modules before creation | CUSTOM taxonomy, provisional | [Odoo 19 product source](https://github.com/odoo/odoo/blob/19.0/addons/product/models/product_template.py) |
| Application filter | Product tags do not safely express a separate customer-facing application facet | Gap | Add configurable application taxonomy linked to `product.template`; do not duplicate product data | CUSTOM taxonomy, provisional | [Products](https://www.odoo.com/documentation/19.0/applications/websites/ecommerce/configuration/products.html) |
| Product tags | Product tag facilities | Partial | Reuse standard tags where available; validate website exposure in Development | NATIVE/EXTENSION | [Products](https://www.odoo.com/documentation/19.0/applications/websites/ecommerce/configuration/products.html) |
| Product gallery and video | eCommerce media / `product.image` | Meets | Render standard media in Lucky Tone QWeb gallery | NATIVE UI | [Odoo 19 website_sale source](https://github.com/odoo/odoo/blob/19.0/addons/website_sale/models/product_template.py) |
| Product documents | `product.document` backed by `ir.attachment` | Meets base requirement | Render standard documents; add only version/language or segment fields confirmed missing | NATIVE/EXTENSION | [Odoo 19 product source](https://github.com/odoo/odoo/blob/19.0/addons/product/models/product_template.py), [Sale portal document check](https://github.com/odoo/odoo/blob/19.0/addons/sale/controllers/portal.py) |
| Customer-specific pricing | Pricelists and customer assignment | Meets | Assign pricelist to customer; calculate again on the server | NATIVE | [Prices](https://www.odoo.com/documentation/19.0/applications/websites/ecommerce/configuration/prices.html) |
| Segment-derived pricelist | Not required when each customer has an assigned pricelist | Deferred | Do not build initially; reconsider only if administrators require automatic segment mapping | NONE | [Prices](https://www.odoo.com/documentation/19.0/applications/websites/ecommerce/configuration/prices.html) |
| Price visibility states | Native price hiding plus website configuration is partial | Partial | Thin settings/service layer for visible, login, contact and quote states; never send unauthorized prices | EXTENSION | [eCommerce configuration](https://www.odoo.com/documentation/19.0/applications/websites/ecommerce/configuration.html) |
| Segment product visibility | Native publication is not segment-aware | Gap | Add visibility mode and allowed segments to `product.template`; enforce in reusable server-side domains/services | EXTENSION | [Products](https://www.odoo.com/documentation/19.0/applications/websites/ecommerce/configuration/products.html) |
| Catalog, cart and checkout | `website_sale`, `sale.order`, checkout | Meets business engine | Reuse routes/services where safe; replace presentation with Lucky Tone templates and components | NATIVE UI | [eCommerce](https://www.odoo.com/documentation/19.0/applications/websites/ecommerce.html), [Checkout](https://www.odoo.com/documentation/19.0/applications/websites/ecommerce/checkout.html) |
| Order creation | `sale.order` / `sale.order.line` | Meets | Standard cart creates quotation/order; configured no-online-payment flow | NATIVE | [Order handling](https://www.odoo.com/documentation/19.0/applications/websites/ecommerce/order_handling.html) |
| Order Portal | Standard Sales Portal | Meets | Extend visual shell and add ERP timeline after ownership validation | NATIVE/EXTENSION | [Customer accounts](https://www.odoo.com/documentation/19.0/applications/websites/ecommerce/customer_accounts.html) |
| Sample request | No native process matches sample approval and ERP synchronization | Gap | Create request and line models with controlled state methods and chatter | CUSTOM | No equivalent native model identified |
| After-sales intake | Helpdesk tickets and Portal | Meets with fields | Website form creates `helpdesk.ticket`; add only confirmed missing request/product/serial/order fields | NATIVE/EXTENSION | [Helpdesk after-sales](https://www.odoo.com/documentation/19.0/applications/services/helpdesk/advanced/after_sales.html) |
| Repair | Repairs and Helpdesk integration | Meets | Create and manage `repair.order` from Helpdesk | NATIVE | [Helpdesk after-sales](https://www.odoo.com/documentation/19.0/applications/services/helpdesk/advanced/after_sales.html), [Repairs](https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/repairs/repair_orders.html) |
| Replacement/return | eCommerce Portal return and reverse transfer | Meets base flow | Reuse native return; add no replacement inventory engine | NATIVE | [Order handling](https://www.odoo.com/documentation/19.0/applications/websites/ecommerce/order_handling.html) |
| ERP write queue | No Partner Hub-specific reliable external write queue | Gap | Create generic integration job, cron worker, adapter interface and mock adapter | CUSTOM | [Scheduled actions](https://www.odoo.com/documentation/19.0/developer/reference/backend/actions.html) |
| ERP order progress | External source of truth | Gap | Secure service calls adapter after Odoo order ownership check; no browser-to-ERP access | CUSTOM integration | [External JSON-2 API](https://www.odoo.com/documentation/19.0/developer/reference/external_api.html) |
| Audit | Chatter and tracked fields | Mostly meets | Use tracking first; defer `b2b_audit` until export/delete/configuration gaps are demonstrated | NATIVE, deferred gap | [Mixins](https://www.odoo.com/documentation/19.0/developer/reference/backend/mixins.html) |
| RBAC | Groups, ACL, record rules and field groups | Meets mechanism | Define additive Partner Hub groups around standard app permissions | NATIVE/EXTENSION | [Access rights](https://www.odoo.com/documentation/19.0/applications/general/users/access_rights.html), [Security](https://www.odoo.com/documentation/19.0/developer/reference/backend/security.html) |
| Custom frontend | Website, QWeb and frontend assets | Meets platform | Lucky Tone design system in `web.assets_frontend`; Owl only for complex state | NATIVE UI | [QWeb](https://www.odoo.com/documentation/19.0/developer/reference/frontend/qweb.html), [Assets](https://www.odoo.com/documentation/19.0/developer/reference/frontend/assets.html) |

## Approved custom data candidates

These models represent real gaps and do not duplicate Odoo master data:

- `b2b.customer.segment`: configurable B2B classification.
- `b2b.product.brand`: provisional taxonomy, created only after Development
  confirms no installed native equivalent.
- `b2b.product.application`: provisional customer-facing filter taxonomy.
- `b2b.sample.request` and `b2b.sample.request.line`: sample workflow.
- `b2b.integration.job`: generic asynchronous ERP work item.

No custom customer, product, order, media, resource, service, repair, return,
portal or user master is approved.

## Odoo.sh Development validation list

The repository does not contain Odoo Enterprise source or an installed database.
The first Development build must verify:

1. exact technical module names and dependency graph for Helpdesk, Repairs and
   product documents;
2. exact fields and views of `product.document`, `product.image`,
   `helpdesk.ticket` and `repair.order`;
3. whether any installed Enterprise module provides product brand/application;
4. whether Marketing can maintain eCommerce media without gaining sensitive
   product or price write access; otherwise use a narrow controlled wizard;
5. portal return availability for the selected product types and inventory
   configuration;
6. no-payment checkout state (quotation sent versus confirmed order) agreed with
   Sales and ERP;
7. native export restrictions and whether a server-side export guard is needed;
8. Product Documents download behavior for public, portal and access-token
   routes before adding segment restrictions;
9. all inherited view XML IDs against the exact Odoo 19 build.

## Architecture decision

Proceed with `b2b_management`, `b2b_core`, `b2b_website`, `b2b_sample` and
`b2b_erp_connector`. Do not create `b2b_resource`, `b2b_service`, `b2b_order`,
`b2b_media`, `b2b_product`, `b2b_customer` or `b2b_audit` in phase one unless a
documented Development validation proves a new gap.
