# Functional Coverage Matrix

Status: **Architecture gate — awaiting approval**

The matrix prevents Odoo Native First from reducing the V4.1 customer scope.
`Planned` means the requirement is assigned to an implementation and test, not
that it has been coded.

| Requirement | Page / entry | Backend source | Type | Permission boundary | Planned test | Status |
|---|---|---|---|---|---|---|
| Homepage | `/` | Website content | NATIVE UI | Public content only | public render and responsive tour | Planned |
| Header/navigation/footer | Global layout | Website/Portal | NATIVE UI | Account links reflect authentication only | desktop/mobile navigation tour | Planned |
| Catalog search | `/products` | `product.template` | EXTENSION UI | visibility domain applied before results | hidden product absent from search | Planned |
| Category filter | `/products` | `product.public.category` | NATIVE UI | same product visibility domain | category pagination | Planned |
| Brand filter | `/products` | provisional brand taxonomy | CUSTOM taxonomy | only visible products returned | brand filter isolation | Gate decision |
| Tag filter | `/products` | native product tags where usable | NATIVE/EXTENSION | same product visibility domain | tag filter | Development validation |
| Application filter | `/products` | application taxonomy | CUSTOM taxonomy | only visible products returned | application filter | Gate decision |
| Pagination/empty/error states | `/products` | Website pager/service | EXTENSION UI | no count leakage | empty and invalid filter cases | Planned |
| Product detail | `/products/<slug>` | `product.template` | EXTENSION UI | 404/no-permission before rendering | direct URL isolation | Planned |
| Gallery/video | Product detail | `product.image` / eCommerce media | NATIVE UI | follows product visibility | media switching and mobile tour | Planned |
| Technical specifications | Product detail | standard product fields plus minimal confirmed fields | NATIVE/EXTENSION | follows product visibility | rendered data and escaping | Planned |
| Related products | Product detail | native related products | NATIVE UI | re-filter every related product | related-product leakage test | Planned |
| Customer final price | Catalog/detail/cart | Pricelist | NATIVE service | calculate for authenticated commercial partner | Dealer A/B price isolation | Planned |
| Price state | Catalog/detail | website settings | EXTENSION | unauthorized numeric value never serialized | guest/login/contact/quote states | Planned |
| Add to cart | Product detail | `website_sale` | NATIVE UI | product/customer/price revalidated | hidden product cannot be added | Planned |
| Cart quantities/remove | `/shop/cart` styled experience | `sale.order` | NATIVE UI | current website order only | quantity, remove, empty cart | Planned |
| Checkout/order submit | standard checkout with Lucky Tone styling | `website_sale`, `sale.order` | NATIVE UI | partner, product, price and address revalidated | submit success/failure/replay | Planned |
| No-online-payment order flow | Checkout | Sales/eCommerce configuration | NATIVE config | internal confirmation rules | quotation/order state test | Business confirmation |
| Product resources | Product detail | `product.document` / `ir.attachment` | NATIVE/EXTENSION UI | product and document access checked server-side | unauthorized download/IDOR | Planned |
| Resource metadata | Product detail | standard document fields plus minimal version/language fields if absent | EXTENSION | follows document access | type/version/language render | Development validation |
| Sample request form | Product detail and `/sample/request` | `b2b.sample.request*` | CUSTOM | portal customer and visible product | validation and ownership | Planned |
| Sample backend review | B2B Management | sample models | CUSTOM | operator review; manager approve/reject | state and approval ACL | Planned |
| Sample ERP push | Scheduled worker | `b2b.integration.job` | CUSTOM | internal worker only | retry/idempotency/errors | Planned |
| After-sales form | `/service` | `helpdesk.ticket` | EXTENSION UI | portal user; owned/visible product/order | valid ticket creation | Planned |
| After-sales Portal | `/my` ticket pages | Helpdesk Portal | NATIVE UI | commercial-partner ticket isolation | Customer A/B isolation | Planned |
| Repair | Backend Helpdesk/Repairs | `repair.order` | NATIVE | After-sales/Repair groups | ticket-to-repair test | Planned |
| Replacement/return | Portal/backend | stock return/reverse transfer | NATIVE | owned delivered order | unauthorized return denied | Planned |
| My Account | `/my` | Portal | NATIVE UI | authenticated portal user | card visibility and noindex | Planned |
| My Orders | Portal | Sales Portal | NATIVE UI | standard ownership/token checks | Customer A/B order isolation | Planned |
| ERP order timeline | Order detail | ERP adapter DTO | CUSTOM integration UI | Odoo order ownership before ERP query | own order, unavailable, partial response | Planned |
| Guest order tracking | none in phase one | — | DISABLED | login required | public route unavailable | Planned |
| Accessibility | All customer pages | design system | UI | semantic and keyboard behavior | labels, focus, alt, status text | Planned |
| Responsive behavior | All customer pages | design system | UI | same server permissions | desktop/tablet/mobile tours | Planned |
| SEO | public pages | website SEO metadata | NATIVE UI | portal/customer-only pages noindex | canonical/meta/noindex | Planned |
| Error and retry states | All core flows | service error mapping | EXTENSION UI | no traceback, host, secret or raw ERP error | safe error rendering | Planned |
| RBAC | Backend | groups/ACL/rules/field groups | EXTENSION | cumulative role combinations tested | role matrix suite | Planned |
| Audit | Backend/chatter | `mail.thread`, tracking | NATIVE | authorized internal users | tracked state/approval changes | Planned |

## Phase-one exclusions

AI runtime, LangGraph runtime, online payment, independent React applications,
microservices, Kafka, Elasticsearch, guest order lookup and a second admin are
not phase-one deliverables.
