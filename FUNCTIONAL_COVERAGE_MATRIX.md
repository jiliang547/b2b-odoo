# Functional Coverage Matrix

Status: **Implemented; Odoo.sh Development validation pending**

| Requirement | Page / entry | Backend source | Type | Permission / test | Status |
|---|---|---|---|---|---|
| Homepage, header, footer | `/` | Website/QWeb | EXTENSION UI | public render, responsive/manual | Implemented |
| Search and filters | `/products` | product/category/tag + minimal taxonomies | NATIVE/EXTENSION | visibility before count/results | Implemented |
| Pagination/empty states | `/products/page/*` | Portal pager | EXTENSION UI | 24/page, no denied counts | Implemented |
| Product detail | `/products/<slug>` | `product.template` | EXTENSION UI | denied direct URL 404 test | Implemented |
| Gallery/video | Detail | `product.image` | NATIVE UI | follows product rule | Implemented |
| Specifications | Detail | Product + minimal field | EXTENSION | sanitized HTML | Implemented |
| Related products | Detail | native alternatives | NATIVE UI | visibility re-filtered | Implemented |
| Customer final price | Catalog/detail/cart | Pricelist | NATIVE | server calculation | Implemented |
| Price states | Catalog/detail | Website settings | EXTENSION | denied payload has no price test | Implemented |
| Product/Segment visibility | All product access | Product rule/service | EXTENSION | controller + ORM + cart tests | Implemented |
| Cart quantity/remove | `/shop/cart` | `website_sale` | NATIVE UI | current cart; price gate | Implemented |
| Checkout/order submit | `/shop/checkout` | `sale.order` | NATIVE UI | approval/product/price recheck | Implemented |
| No-online-payment flow | Odoo configuration | Payment/Sales | NATIVE config | state requires business validation | Development gate |
| Resources/metadata | Detail/download | Product Documents | NATIVE/EXTENSION | product + document authorization | Implemented |
| Sample request | Detail, `/sample/request` | custom sample gap | CUSTOM | ownership/input/line tests | Implemented |
| Sample review | B2B Management | sample state methods | CUSTOM | operator/manager separation | Implemented |
| Sample ERP push | Cron/job | integration queue | CUSTOM | idempotency/retry tests | Implemented |
| After-sales intake | `/service` | `helpdesk.ticket` | EXTENSION UI | owned order/product + upload checks | Implemented |
| After-sales status | `/my` Tickets | Helpdesk Portal | NATIVE | Enterprise Customer A/B test | Development gate |
| Repair/return/replacement | Helpdesk backend | Repairs/reverse transfer | NATIVE | enable team features/test bridge | Development gate |
| My Account | `/my` | Portal | NATIVE/EXTENSION | sample/service cards, noindex | Implemented |
| My Orders | `/my/orders` | Sales Portal | NATIVE | native ownership | Implemented |
| ERP progress | order detail link | normalized ERP DTO | CUSTOM boundary | own-order/IDOR/unavailable tests | Implemented |
| Guest tracking | none | — | DISABLED | login-only route | Implemented |
| Design system | customer pages | QWeb/SCSS/JS | EXTENSION UI | reusable components | Implemented |
| Responsive/accessibility | customer pages | frontend assets | UI | keyboard/mobile acceptance | Implemented baseline |
| SEO/noindex | public/Portal pages | Website/QWeb | NATIVE UI | Portal and tracking noindex | Implemented baseline |
| Safe errors/states | core flows | controller/service mapping | EXTENSION | no traceback/raw ERP | Implemented |
| RBAC/audit | backend | groups/ACL/rules/chatter | NATIVE/EXTENSION | role matrix acceptance | Implemented baseline |
| Management App | backend app | client action/native actions | EXTENSION UI | internal groups | Implemented |

“Development gate” means the code intentionally reuses an Enterprise-native
feature whose exact installed bridge/configuration cannot be executed in this
source-only workspace. It is not replaced by speculative custom models.
