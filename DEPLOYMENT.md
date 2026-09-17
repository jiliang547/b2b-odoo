# Odoo.sh Deployment

## 1. Development build

1. Connect this GitHub repository to an Odoo.sh Odoo 19 Enterprise project.
2. Push/deploy the implementation branch to Development.
3. Update the Apps list and install `Lucky Tone B2B Management`. Its dependencies
   include multi-company sales and the native Dropship/intercompany modules.
   Existing installations must upgrade `b2b_management` after deploying this
   version; pushing files alone is not a database module upgrade. There is no
   separate multi-company app installation or activation switch for operators.
4. Confirm Enterprise dependencies and the Helpdesk ticket inherited view load.
5. Run the module test suite with `--test-tags /b2b_core,/b2b_erp_connector,/b2b_sample,/b2b_website`.

## 2. Business configuration

Current fulfilment mode is **External ERP**. Use **B2B Management → Business
Setup** for centralized seller/brand setup and batch customer assignment. A
factory, local stock warehouse and internal supply prices are required only
when selecting **Odoo Fulfilment**. The factory setup items below describe that
optional native mode, not prerequisites for External ERP. Each new order keeps
its execution-provider snapshot; pre-existing routed factory orders are migrated
as Odoo fulfilment and are not silently switched. API integration is a separate
workstream; external revisions remain explicitly pending external execution.

- In Website → Settings → Partner Hub → Multi-company Sales Configuration,
  configure permitted legal sellers and the fulfilment provider, and set the
  default account brand to a permitted seller. Routing follows this configuration
  automatically. Odoo fulfilment additionally requires a factory. Partial setup blocks routed ordering; an untouched existing
  website retains its single-company flow. No real companies/accounts are seeded.
- Configure each customer's seller/brand, each seller's native bank journals,
  payment methods and technical Dropship warehouse, and the factory's warehouse,
  intercompany rules and product vendor prices. Routing status is not a declaration
  that these operational settings or acceptance tests are complete.

- Create customer companies/contacts and grant Portal access by invitation.
- Assign the customer's native Odoo Pricelist.
- Configure B2B Segment, approval, product visibility, brand/application,
  publication, eCommerce media and Product Documents.
- In Website settings, select price states and approval requirements.
- Create/select a Helpdesk team and configure it as the Partner Hub team.
- On that team, enable native Returns and Repairs after-sales features; Odoo may
  install the associated Enterprise bridge modules automatically.
- Configure a manual/offline payment or quotation workflow if online payment is
  not part of phase one. Verify the resulting order state with Sales and ERP.
- Leave ERP disabled until the real adapter exists. Mock mode is Development-only.

## 3. Development validation gates

- Exact `helpdesk.ticket` fields and `helpdesk.helpdesk_ticket_view_form` XML ID
- Native Helpdesk Portal company isolation for parent/child contacts
- Helpdesk Returns/Repairs feature installation and ticket smart buttons
- Product Document behavior for uploaded files and URL resources
- Marketing media permissions without product/price over-privilege
- Brand/application overlap with installed Enterprise/localization modules
- Native Portal return eligibility by product and delivery state
- No-payment checkout state and ERP enqueue point
- Cart, checkout, email templates and responsive layout in the selected theme
- Website multi-company/multi-website product rule interaction

Record any required XML ID or field adjustment as a compatibility-only patch;
do not duplicate the native Helpdesk, Repair, Return or product models.

## 4. Staging

- Use sanitized representative customers, segments, pricelists, products,
  media, documents, orders, deliveries and tickets.
- Execute [TESTING.md](TESTING.md), including role-combination and Customer A/B
  isolation tests.
- If a real ERP adapter is available, point only to ERP sandbox credentials and
  verify replay/idempotency, timeout, malformed response and unavailable states.
- Run desktop/tablet/mobile and accessibility checks.

## 5. Production

- Promote the exact Staging commit; do not edit code in Production.
- Set Production-only secrets and rotate any copied sandbox token.
- Confirm ERP is disabled unless go-live approval is explicit.
- Smoke test public catalog, approved/unapproved Portal, cart/order, samples,
  service, document download and own-order tracking.
- Monitor Odoo logs, failed/dead ERP jobs, outgoing mail and Helpdesk assignment.

## Rollback

Use Odoo.sh backups and branch promotion rollback. Do not uninstall modules from
a live database as a rollback mechanism because custom fields and business
records may be removed. Restore the prior tested build/database pair, investigate
in Development, then promote a forward fix.
