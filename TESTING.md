# Testing

## Automated coverage

Tests use Odoo's `TransactionCase` and `HttpCase` with post-install tags.

| Area | Cases |
|---|---|
| Product policy | Segment allow/deny, hidden product exclusion, native shop domain, generic ORM bypass prevention |
| Pricing | Unapproved payload contains a state and no numeric price |
| Samples | Forced ownership/state, nested line creation, direct line denial, company isolation, workflow write guard, approval/job creation |
| ERP | Duplicate idempotency, mock success, missing reference, safe failed state and authorized retry |
| Website/order | Direct cart add without price permission, restricted detail 404, cross-company ERP order status 404 |

Run on Odoo.sh or an Odoo 19 Enterprise checkout:

```bash
odoo-bin -d <test_database> --stop-after-init --test-enable \
  --test-tags /b2b_core,/b2b_erp_connector,/b2b_sample,/b2b_website \
  -i b2b_management
```

The source-only checks run Python bytecode compilation, XML parsing, manifest
file existence, JavaScript syntax parsing and repository secret-pattern scans.
They do not replace a registry/module-install test.

## Required Odoo.sh acceptance scenarios

1. Public, unapproved, approved Dealer and approved Integrator each see only
   permitted products and correct non-price/price state.
2. Dealer and Integrator assigned different Pricelists receive different native
   final prices; HTML/source/JSON for denied users contains no numeric price.
3. Search, category, brand, tag, application, related products, direct URLs,
   generic RPC and cart calls never disclose a denied product.
4. Gallery image/video switching, resources and authorized downloads work on
   desktop, tablet and mobile; unauthorized document IDs return 404.
5. Cart empty/update/remove, checkout validation, submit success/failure and
   repeat submission behave safely with the agreed no-payment configuration.
6. Sample validation, Customer A/B isolation, operator review, manager
   approve/reject and Integration Manager retry match the state machine.
7. Service creates one Helpdesk ticket with contact snapshot and valid
   attachments; other file types, signatures, orders and company IDs are denied.
8. Native Helpdesk Portal, ticket-to-Repair and return/replacement workflows do
   not expose another company.
9. Own-order ERP status shows normalized timeline/unavailable/empty states;
   another company's ID and all public requests return 404/login.
10. Role combinations in `RBAC_MATRIX.md` cannot edit customer approval,
    Pricelist, products, service or ERP secrets outside their responsibilities.

## UX quality

Use keyboard-only navigation, visible focus, labels, image alternative text,
screen-reader status messages and 320/768/1280+ viewport checks. Verify long
names, empty catalogs, no resources, missing timeline, invalid forms, session
expiry and Odoo safe 404/500 pages. Use browser performance tooling to confirm
24-item pagination, thumbnail loading and no large document preload.
