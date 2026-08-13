# Architecture

Status: **Approved and implemented; Odoo.sh validation pending**

## Context

```text
External B2B customer                         Internal employee
        |                                             |
        v                                             v
Lucky Tone Website / Portal                     Odoo Backend
        |                                             |
        +-------------------+-------------------------+
                            v
                    Business service layer
                            |
               +------------+-------------+
               |            |             |
               v            v             v
          Odoo native   Thin extensions   Custom gaps
          Products      Visibility        Samples
          Pricelists    Price state       ERP jobs
          Sales         Ticket fields     Taxonomies
          Portal        Secure routes
          Helpdesk
          Repairs
          Documents
               |            |             |
               +------------+-------------+
                            v
                         Odoo ORM
                            |
                     PostgreSQL managed
                       by Odoo/Odoo.sh
                            |
                            v
                  ERP adapter and existing ERP
```

GitHub is the code source of truth. Odoo.sh builds Git revisions into isolated
Development, Staging and Production environments. A build/restart is not a
substitute for installing or upgrading an Odoo module in the database.

## Classification

### NATIVE

- Contacts and customer identity: `res.partner` / `res.users` / Portal.
- Products and variants: `product.template` / `product.product`.
- Pricing: `product.pricelist` and rules.
- Media: eCommerce `product.image` facilities.
- Documents: `product.document` and `ir.attachment`.
- Cart, checkout and orders: `website_sale` and `sale.order`.
- After-sales master: `helpdesk.ticket`.
- Repair: `repair.order`.
- Return/replacement inventory operations: standard returns/reverse transfers.
- Audit baseline: chatter and tracked fields.

### EXTENSION

- Partner approval and segment relations on `res.partner`.
- Segment visibility and customer-facing taxonomy relations on products.
- B2B price-state settings without replacing Pricelist.
- Lucky Tone QWeb/SCSS/JS presentation and Portal extensions.
- Minimal missing Helpdesk fields.
- Secure product-document rendering/download checks if segment restrictions are
  enabled.
- ERP references/timeline presentation on standard orders.

### CUSTOM

- Customer segment taxonomy.
- Provisional brand and application taxonomies, pending Development validation.
- Sample request and lines.
- Generic ERP integration jobs, adapter configuration and safe logs.

## Modules and dependencies

```text
b2b_management (installable application and navigation)
    +-- b2b_website
    +-- b2b_sample
    +-- b2b_erp_connector
    +-- b2b_core

b2b_website
    +-- b2b_core
    +-- b2b_sample
    +-- b2b_erp_connector
    +-- website / website_sale / portal / helpdesk / repair (native)

b2b_sample
    +-- b2b_core
    +-- b2b_erp_connector
    +-- mail / product (native)

b2b_erp_connector
    +-- b2b_core
    +-- sale_management / mail (native)

b2b_core
    +-- contacts / product / website_sale / mail (native)
```

Exact Enterprise technical dependencies are validated in Odoo.sh Development
before manifests are finalized. No reverse dependency from a low-level module
to `b2b_management` is allowed.

## Responsibilities

### `b2b_management`

One installable app (`application=True`) with icon, dashboard and links to
Partner Hub-specific records. Standard Customers, Products, Sales, Helpdesk,
Repairs and Users remain in their native apps; the dashboard only links to them.

### `b2b_core`

Groups, customer segments, partner approval, product visibility, optional
brand/application taxonomies, B2B settings and reusable product/price/document
authorization services.

### `b2b_website`

Lucky Tone design system, layout, catalog, product detail, Portal cards, ERP
timeline, sample and after-sales presentation. Controllers validate input and
delegate to services; templates never make final authorization decisions.

### `b2b_sample`

Sample request models, controlled state transitions, sequence, backend views,
Portal ownership and creation of ERP jobs after approval.

### `b2b_erp_connector`

Adapter contract, mock adapter, generic jobs, cron worker, retry/backoff,
idempotency, response validation and redacted technical logs. It never exposes
credentials or raw ERP responses to the browser.

## Request flows

### Catalog and price

```text
GET /products
 -> validate filter values
 -> ProductService.visible_domain(current partner, website)
 -> paginated ORM query
 -> native Pricelist computes allowed final prices
 -> render only allowed records and price state
```

### Order

```text
Product -> native cart -> checkout
 -> validate approved partner, visibility, quantity and address
 -> native server-side Pricelist calculation
 -> sale.order / sale.order.line
 -> configured confirmation trigger creates idempotent ERP job
```

### Sample

```text
Portal POST with CSRF
 -> validate visible product and bounded input
 -> create submitted sample owned by commercial partner
 -> manager approves through business method
 -> create ERP job after transaction
 -> cron processes job through adapter
```

### After-sales

```text
Portal POST /service with CSRF
 -> validate owned/visible product and optional order
 -> create standard helpdesk.ticket with minimal extension fields
 -> Helpdesk Portal status
 -> native repair or return process when required
```

### ERP order timeline

```text
Portal order detail
 -> standard order access/ownership check
 -> OrderService builds customer context
 -> ERPAdapter.get_order_status
 -> validated normalized DTO
 -> safe timeline or unavailable state
```

## Proposed routes

| Route | Auth | Method | Purpose |
|---|---|---|---|
| `/products` | public/user | GET | Paginated visible catalog |
| `/products/<slug>` | public/user | GET | Visible product detail |
| `/products/document/<id>/download` | public/user | GET | Authorized document stream; access token only where native flow requires it |
| `/sample/request` | user | GET/POST | Sample form and CSRF-protected submission |
| `/my/samples` | user | GET | Current commercial partner samples |
| `/my/samples/<id>` | user | GET | Owned sample detail |
| `/service` | user | GET/POST | CSRF-protected Helpdesk intake |
| `/my/orders/<id>/erp-status` | user | GET | Owned-order ERP DTO/timeline |

Native cart, checkout, order, Helpdesk Portal and return routes are inherited or
styled rather than duplicated. Guest order tracking is disabled in phase one.

## Security boundaries

- ACL and record rules are authoritative; menu/button hiding is supplemental.
- Portal rules use `commercial_partner_id` where company-wide access is agreed.
- Every ID from a route or form is checked for existence and access.
- Product visibility is applied to catalog, search, detail, related products,
  cart validation, samples and documents.
- Prices are recalculated server-side and unauthorized numeric values are not
  serialized.
- Ordinary HTTP writes retain CSRF protection.
- `sudo()` is exceptional, narrowly scoped and followed by explicit filtering.
- Sensitive configuration fields use manager groups and secrets never enter Git.

## ERP reliability

Jobs move through `pending -> processing -> success` or retryable `failed`, then
`dead` after the configured limit. A unique idempotency key prevents duplicate
successful submissions. Retries use bounded exponential backoff. Claiming work
must be concurrency-safe; the exact locking implementation is chosen and tested
against Odoo 19. Safe summaries are allowlists, not raw payload dumps.

## Future AI

```text
LangGraph / AI agent
 -> authenticated least-privilege tool/API
 -> the same Product, Sample, Document and Order services
 -> Odoo ORM / ERP adapter
```

AI receives neither PostgreSQL access nor administrator credentials. Odoo 19
JSON-2 or small `/b2b/api/v1/*` endpoints can be evaluated after phase one.
