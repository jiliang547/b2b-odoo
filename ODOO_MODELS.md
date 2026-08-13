# Odoo Model Map

| Capability | Model | Implementation |
|---|---|---|
| Company/contact/Portal identity | `res.partner`, `res.users` | Native + approval/Segment extension |
| Customer pricing | `product.pricelist`, `product.pricelist.item` | Native |
| Product/variant | `product.template`, `product.product` | Native + visibility, brand, application, model/spec fields |
| Category/tag | `product.public.category`, `product.tag` | Native |
| Gallery/video | `product.image` | Native |
| Resource | `product.document`, delegated `ir.attachment` | Native + policy/type/version/language fields |
| Cart/order | `sale.order`, `sale.order.line` | Native + ERP reference/job relationship and server guards |
| Customer account/order list | Portal/Sales Portal controllers | Native + sample and ERP tracking entries |
| After-sales | `helpdesk.ticket` | Native + request/product/serial/order/submission snapshot fields |
| Repair/return/replacement | `repair.order`, stock reverse transfer | Native, configured from Helpdesk |
| Sample workflow | `b2b.sample.request`, `b2b.sample.request.line` | Custom confirmed gap |
| ERP queue | `b2b.integration.job` | Custom confirmed gap |
| Customer segment | `b2b.customer.segment` | Custom taxonomy gap |
| Brand/application | `b2b.product.brand`, `b2b.product.application` | Minimal custom taxonomies |

## State machines

Sample:

`draft → submitted → under_review → approved → erp_pending → erp_synced`

Alternative terminal/recovery states are `rejected`, `cancelled` and
`erp_failed → erp_pending` through an authorized retry.

ERP job:

`pending → processing → success`

Failures move to `failed` with exponential backoff, then `dead` after the
configured bounded attempt count. An Integration Manager can explicitly return
`failed` or `dead` jobs to `pending`.

## Ownership keys

- Portal company: `user.partner_id.commercial_partner_id`
- Sample owner: stored `commercial_partner_id`
- Sample line owner: stored related commercial partner
- Sales order owner: `partner_id.commercial_partner_id`
- Helpdesk Portal owner: native Helpdesk partner/Portal rules
- ERP reference: allowlisted model name + record ID; never an arbitrary model

Model and field names were checked against Odoo Community 19.0 source commit
`c2a3908`. Helpdesk Enterprise fields and inherited view IDs remain an Odoo.sh
Development installation check.
