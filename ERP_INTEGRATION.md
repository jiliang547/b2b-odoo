# ERP Integration

## Current contract boundary

`b2b.erp.service` is the only integration facade. The repository intentionally
contains no invented production endpoint, authentication scheme or formal ERP
status dictionary. `MockERPAdapter` is deterministic and intended only for
Development demonstrations and automated tests.

The connector is disabled by default. Enabling it with the mock adapter creates
mock references; this must never be mistaken for production synchronization.

## Outbound workflow

1. Odoo confirms a sales order, or a B2B Manager approves a sample request.
2. `b2b.integration.job.enqueue()` creates one job using a unique business UUID
   idempotency key. Concurrent duplicate insertions return the existing job.
3. The five-minute cron selects due jobs in bounded batches and locks each row.
4. The adapter receives the Odoo record and idempotency key.
5. Only safe allowlisted response fields are persisted.
6. Failure records a redacted message and exponential next-attempt time; the
   final bounded failure becomes dead-letter.

## Required real-adapter interface

A production adapter must implement:

- `push_sales_order(order, idempotency_key)`
- `push_sample_request(request_record, idempotency_key)`
- `get_order_status(order, customer_context)`

Write results must be dictionaries with `success` and a stable external
`reference`. Status results must provide `order_number`, `status`,
`current_stage` and `timeline`; the service normalizes and length-bounds all
customer-visible values and replaces `order_number` with the already authorized
Odoo order number.

## Contract approval checklist

- Base URL and API version per environment
- OAuth/client credentials, signed request, mTLS or other approved mechanism
- Timeout and retry semantics; retryable versus terminal error mapping
- Request/response JSON schemas and field mapping
- Currency, unit-of-measure, tax and timezone rules
- Idempotency header/body behavior and retention period
- ERP reference and order-status stage dictionary
- Tracking-number semantics
- Rate limits, maintenance windows and observability contacts
- Test fixtures with no production personal data

After approval, add a real adapter without changing website controllers or the
job state machine. Add contract tests, then validate in Development and Staging
before enabling Production.
