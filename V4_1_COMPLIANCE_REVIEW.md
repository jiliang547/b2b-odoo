# V4.1 Compliance Review

Review date: 2026-08-13

## Outcome

The repository implements the V4.1 phase-one architecture in five Odoo modules.
No second customer, product, order, media, resource, Portal, Helpdesk, Repair or
Return master was created. Customer-facing pages use a dedicated Lucky Tone
QWeb/SCSS design system while native Odoo models remain authoritative.

## Requirement trace

| V4.1 area | Result | Evidence |
|---|---|---|
| Homepage/global layout | Implemented | Partner layout, responsive navigation/footer, homepage sections |
| Catalog/search/filters/pager | Implemented | `/products`, centralized domain and 24-item pager |
| Detail/gallery/video/specifications | Implemented | Native product/media data with responsive switching |
| Customer pricing/states | Implemented | Native Pricelist calculation and state-only denied payloads |
| Segment visibility | Implemented | Controller/service, native public ORM rules, cart revalidation |
| Resources | Implemented | Native Product Documents, metadata extension and authorized stream |
| Cart/checkout/order | Implemented | Native website_sale with visual extension and approval guards |
| Samples | Implemented | Custom gap model, Portal pages, backend workflow and ERP job |
| After-sales | Implemented | `/service` creates native Helpdesk ticket; native Portal/Repair/Return retained |
| My Account/orders | Implemented | Native Portal plus sample card/pages and ERP link |
| ERP order progress | Implemented boundary | Authorized normalized DTO and unavailable state; real contract pending |
| B2B Management App | Implemented | App icon, dashboard, metrics, menus and native shortcuts |
| RBAC/data ownership | Implemented baseline | Additive groups, ACLs, rules, method checks and chatter |
| Responsive/accessibility/states | Implemented baseline | Tokens/components/media queries/labels/focus/empty/error/success states |
| Automated tests | Implemented source suite | Core, sample, ERP and website security tests |
| Environment/asset ownership docs | Implemented | Deployment, security, ownership and system-asset documents |

## Logic audit findings resolved

1. Portal sample-line create permission was too broad. It is now denied, with a
   narrowly elevated nested create only after parent payload validation.
2. Controller-only product filtering could be bypassed by generic ORM reads.
   Product template and variant public rules now include the B2B policy.
3. Brand/application reverse fields could reveal hidden product IDs/counts.
   They are internal-only; the controller uses a safe visibility-constrained
   sudo taxonomy query.
4. Native shop/cart could reveal numeric prices outside custom templates.
   Shop/detail redirect to Partner Hub; cart/checkout/payment and order lines
   revalidate price, approval and product policy server-side.
5. ERP job computed fields caused per-record searches. They now batch-load jobs.
6. Concurrent enqueue could race the pre-check. A unique constraint plus
   savepoint fallback now returns the existing idempotent job.
7. Failure callbacks could interrupt the worker. They are isolated and logged.
8. Service contact/company/phone snapshots were not persisted. Dedicated
   Helpdesk extension fields now retain them with submission time.
9. ERP status fields were insufficiently normalized for future adapters. Values
   are now allowlisted, length-bounded and order identity is server-owned.

## Intentionally unresolved external facts

These are not code omissions that can be safely guessed:

- real ERP endpoint, authentication, schemas and status dictionary;
- exact Enterprise Helpdesk/Repair bridge and inherited view behavior in the
  customer's Odoo.sh build;
- approved no-online-payment order state;
- company-specific taxonomy overlap and departmental standard-group assignment.

The code contains a mock adapter and explicit Development gates for these facts.
Production ERP remains disabled until the contract exists. Any Odoo.sh XML-ID
compatibility adjustment should remain a thin extension and must not replace a
native business engine.
