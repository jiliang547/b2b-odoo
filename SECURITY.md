# Security Model

## Trust boundaries

The browser controls presentation only. Customer identity, company ownership,
product visibility, numeric price access, document access, cart validity,
sample approval, order ownership and ERP access are decided on the server.

Portal scope is the authenticated contact's `commercial_partner_id`. A caller
cannot broaden that scope by submitting another partner, order, product,
shipping address or request ID.

## Product and price protection

- The native public/Portal product-template rule is extended with B2B approval
  and Segment policy. A matching rule also protects product variants, so direct
  ORM/RPC searches cannot bypass the website controllers.
- `/products`, detail pages, related products, native shop routes and cart
  operations reuse the same policy service.
- Native `/shop` pages redirect to Partner Hub pages. Cart, checkout and payment
  are blocked before rendering when numeric price access is unavailable.
- Prices are calculated by Odoo Pricelists in the request context. Posted price
  values are not accepted by custom controllers, and `sale.order` performs its
  native server-side calculation.

## Resources

Portal users do not receive generic Product Document access. The download route
first validates product visibility, then document policy, and only then uses a
narrow `sudo()` to stream the linked attachment. URL resources allow only HTTP
or HTTPS. Product, document and attachment IDs are never treated as authority.

## Samples

- Portal creation overwrites customer/contact/state ownership fields.
- Product visibility, approval, address ownership, required fields, lengths,
  email and quantity are validated before creation.
- Generic Portal create access to sample lines is denied. Nested lines are
  created under a narrowly elevated, validated parent operation.
- Record rules restrict request and line reads to the commercial company.
- State writes are rejected outside named workflow methods; approval is limited
  to B2B Managers and ERP retry to Integration Managers.

## Service intake and uploads

The service route requires login and an owned confirmed/completed sales order.
The chosen product must occur on that order. Ticket creation is elevated only
after all ownership and input validation succeeds.

Attachments are limited to five files of 10 MB each. Allowed types are PDF,
PNG, JPEG and ZIP, with sanitized filenames and magic-signature checks. Files
are attached directly to the authorized Helpdesk ticket. Deployment should
also configure reverse-proxy request limits and antivirus scanning if required
by company policy.

## ERP and secrets

- Browsers never call ERP directly.
- Writes use unique idempotency keys, row locks, bounded retries and a
  dead-letter state.
- Stored request/response summaries are allowlisted; URLs and common credential
  patterns are redacted from errors.
- The API token is an access-restricted Odoo configuration parameter and is
  never committed. Database backups therefore contain the token and must use
  Odoo.sh access controls, encryption, retention limits and environment-specific
  rotation.
- The bundled adapter is explicitly a disabled-by-default mock. Do not enable a
  production connector until the real contract and secret handling are approved.

## `sudo()` inventory

Every elevation is narrow and follows prior authorization:

1. policy-only reads of the authenticated commercial partner;
2. authorized Product Document lookup/streaming;
3. validated nested sample creation;
4. validated Helpdesk ticket and attachment creation;
5. configuration parameter reads and configured Helpdesk team lookup.

No customer-facing route performs an unrestricted sudo search and then trusts
the returned record without an ownership or visibility check.

## Operational controls

- Use separate Odoo.sh Development, Staging and Production databases/secrets.
- Give employees standard app roles plus only the additive B2B groups needed.
- Review failed/dead ERP jobs, approval chatter and Helpdesk access regularly.
- Do not expose database manager, developer mode or ERP credentials to Portal users.
- Report security issues privately to the company system owner; do not open a
  public issue containing customer data, tokens or exploit details.
