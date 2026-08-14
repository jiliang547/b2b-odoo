# Lucky Tone Partner Hub

Production-oriented Odoo 19 Enterprise modules for a secure B2B customer
website and internal operations application. The implementation follows the
V4.1 Final baseline: Odoo Native First, thin extensions, explicit ownership,
server-side authorization, and custom models only for confirmed gaps.

## Modules

| Module | Purpose |
|---|---|
| `b2b_core` | Customer approval/segments, product visibility, resource policy, price-state service and website settings |
| `b2b_erp_connector` | Idempotent asynchronous ERP jobs, retry/dead-letter workflow, adapter boundary and safe status DTO |
| `b2b_sample` | Sample request/line models, Portal isolation, approval workflow and ERP handoff |
| `b2b_website` | Lucky Tone homepage, catalog/detail, media/resources, samples, service intake, Portal and ERP order tracking |
| `b2b_management` | Installable backend application, dashboard and business navigation |

## Native sources of truth

- Customers and contacts: `res.partner`
- Products and variants: `product.template` / `product.product`
- Pricing: Odoo Pricelists; browser-submitted prices are never trusted
- Gallery/video: Odoo eCommerce `product.image`
- Resources: `product.document` / `ir.attachment`
- Orders/cart/checkout: `website_sale` and `sale.order`
- Service tickets: Helpdesk; repairs and returns remain native Odoo workflows
- Customer identity and account: Odoo Portal

Only sample requests, customer/brand/application taxonomies and the generic ERP
job queue are custom business models.

## Target environment

- Odoo 19 Enterprise on Odoo.sh
- GitHub source, with Development → Staging → Production promotion
- Required Odoo apps: Website, eCommerce, Sales, Portal, Helpdesk and Repairs

Add this repository to Odoo.sh, install `b2b_management`, and let Odoo resolve
the remaining module dependencies. Complete the environment-specific checklist
in [DEPLOYMENT.md](DEPLOYMENT.md) before accepting customer traffic.

## Documentation

- [Architecture](ARCHITECTURE.md)
- [Native gap analysis](ODOO_NATIVE_GAP_ANALYSIS.md)
- [Functional coverage](FUNCTIONAL_COVERAGE_MATRIX.md)
- [RBAC](RBAC_MATRIX.md)
- [Data ownership](DATA_OWNERSHIP.md)
- [Security](SECURITY.md)
- [Odoo model map](ODOO_MODELS.md)
- [ERP integration](ERP_INTEGRATION.md)
- [Deployment](DEPLOYMENT.md)
- [Testing](TESTING.md)
- [V4.1 compliance review](V4_1_COMPLIANCE_REVIEW.md)

The real ERP wire contract and exact Enterprise bridge/view behavior cannot be
proven in a source-only environment. Those items are isolated behind the
adapter and explicitly listed as Odoo.sh Development validation gates; they do
not cause speculative production API behavior.
