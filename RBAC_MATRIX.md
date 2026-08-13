# RBAC Matrix

Status: **Architecture gate — awaiting approval**

Odoo groups are cumulative. This matrix is the target policy and must be mapped
to native Odoo app groups plus small Partner Hub groups. `Scope` always means
the applicable company, sales team, ownership and record rules—not merely a
hidden menu.

Legend: `R` read, `C` create, `W` write, `D` delete, `A` approve, `X` export,
`CFG` configure, `Own` assigned/owned scope, `All` authorized company scope,
`—` denied by default.

| Data / operation | Super Admin | IT / Technical | Sales Manager | Sales | PMC | Product | Marketing | After-sales | Portal customer |
|---|---|---|---|---|---|---|---|---|---|
| Users and access rights | CFG | Dev/Staging CFG; Production temporary | — | — | — | — | — | — | — |
| Contacts/customers | All CRUDX | Production metadata only by default | All RCWX | Own RCW | R needed order scope | R minimal | R minimal | R ticket scope | own company profile R |
| Customer segment/approval | All | technical support, no routine business write | RCWAX | R | R | R | R minimal | R minimal | — |
| Pricelists/rules | All | no routine price access | RCWAX | R assigned results; no rule write | R order result | — | — | — | own computed result only |
| Special price management | All | — | only dedicated manager subgroup | — | — | — | — | — | — |
| Products/general fields | All | technical support | R | R | R | RCW | content-limited entry only | R | visible published R |
| eCommerce media | All | technical support | R | R | R | RW | RCW through validated narrow access | R | visible product R |
| Product documents | All | technical support | R | R | R | RCW | R/public marketing assets only | R service scope | allowed documents R |
| Sales orders | All | production support only | All RCW/X as native permits | Own RCW | All R/W fulfillment fields only | R minimal | — | R referenced order | own company R/create via checkout |
| Sample requests | All | integration support | All RAWX | Own/assigned RCW | R fulfillment scope | R product context | — | R if assigned | own company CR; no approve |
| Helpdesk tickets | All | support metadata | R | Own/customer R | R order scope | R product context | — | All RCW | own company CR through Portal |
| Repairs/returns | All | technical support | R | R own customer | R fulfillment | R technical | — | RCW | own status R/request through allowed flow |
| ERP jobs/logs | All | RCW/retry with secret masking | R business status; manual retry if delegated | R own reference status | R order status; retry if delegated | — | — | R service reference | own normalized status only |
| ERP credentials/settings | All | CFG designated production admins only | — | — | — | — | — | — | — |
| B2B website settings | All | CFG technical | price/business-state CFG if delegated | — | — | product settings if delegated | content/theme settings if delegated | service settings if delegated | — |
| Sensitive export | All | only temporary incident need | dedicated export subgroup | — by default | — by default | — by default | — | — | — |

## Proposed Partner Hub groups

- `group_b2b_operator`: base internal access to Partner Hub menus.
- `group_b2b_manager`: customer approval, sample approval and B2B configuration.
- `group_b2b_special_price_manager`: sensitive Pricelist maintenance.
- `group_b2b_product_manager`: product technical/content responsibility.
- `group_b2b_marketing_media`: narrow media/content responsibility.
- `group_b2b_pmc`: order fulfillment and ERP status responsibility.
- `group_b2b_after_sales`: Helpdesk/repair/return responsibility.
- `group_b2b_integration_manager`: ERP jobs and masked logs.
- `group_b2b_sensitive_export`: explicit sensitive export authorization, only if
  native export controls prove insufficient.

These augment rather than replace standard Sales, Website, Helpdesk, Inventory,
Repairs and Administration groups.

## Required role-combination tests

1. Sales + Marketing cannot edit Pricelist rules or special prices.
2. Product + Marketing can maintain approved content/media without customer or
   price write access.
3. Sales Manager + Sales receives manager scope intentionally, with no system or
   ERP-secret access.
4. After-sales cannot change customer level or Pricelist.
5. PMC cannot change product content or customer level.
6. IT temporary Production elevation is explicit, time-bound operationally and
   audited; removal restores least privilege.
7. Portal users never inherit internal groups and cannot execute public model
   approval methods.

## Unresolved native-security validation

The standard media relation may require Product write permission. If Odoo 19
cannot safely grant Marketing media maintenance without sensitive Product write
access, implement a narrow server-validated wizard/menu rather than broadening
Product ACLs. Export controls require an Odoo.sh test before deciding whether a
custom server-side guard is necessary.
