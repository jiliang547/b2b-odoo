# Data Ownership

Status: **Implemented policy; named business owners required before Production**

Data ownership means responsibility for correctness and lifecycle. It does not
automatically grant unrestricted access, deletion or export rights.

| Data domain | Source of truth | Business owner | Daily maintainer | Technical custodian | Approval / escalation |
|---|---|---|---|---|---|
| Customer company/contact | Odoo Contacts | Sales | assigned Sales | IT | Sales Manager for key structural changes |
| Customer segment/approval | Odoo Partner Hub extension | Sales Manager | authorized Sales Manager | IT | Sales Manager / GM policy |
| Pricelist and price rules | Odoo Pricelist | Sales Manager | designated pricing role | IT | special price manager / GM policy |
| Product master and variants | Odoo Products | Product | Product team | IT | Product Manager |
| Technical specifications | Odoo Products | Product | Product team | IT | Product Manager |
| Product documents | Odoo Product Documents | Product | Product team | IT | Product Manager; Legal/Quality where applicable |
| Images/video/marketing content | Odoo eCommerce Media / Website | Marketing | Marketing | IT | Marketing Manager |
| Website categories/taxonomies | Odoo eCommerce + thin extension | Product/Marketing | agreed owner by taxonomy | IT | Product + Marketing alignment |
| Sale order | Odoo Sales until ERP handoff | Sales | Sales/authorized customer | IT | Sales Manager |
| Fulfillment/production/shipping | Existing ERP | PMC/Operations | PMC/ERP operators | IT/ERP team | Operations owner |
| Sample request | Odoo custom sample | Sales | Sales/operator | IT | Sales Manager approval |
| ERP synchronization job | Odoo integration layer | IT/ERP process owner | integration managers | IT | business owner for replay impact |
| Helpdesk/RMA ticket | Odoo Helpdesk | After-sales | After-sales | IT | After-sales Manager |
| Repair order | Odoo Repairs | After-sales/Repair team | Repair team | IT | After-sales Manager |
| Return/replacement movement | Odoo Inventory | Operations/After-sales | authorized Inventory/After-sales | IT | Inventory/After-sales policy |
| User accounts and roles | Odoo Users/Groups | Company Super Admin | designated access administrator | IT | Company owner / security policy |
| ERP credentials | Odoo/Odoo.sh protected configuration | Company/IT | minimum designated admins | IT | credential owner and rotation policy |
| Production backups | Odoo.sh | Company | designated platform admins | IT | company recovery policy |

## Source-of-truth boundary

### Odoo owns

Partner Hub identity, customers/contacts used by the Hub, product content,
website content, Pricelists, quotations/orders, samples, Helpdesk, repairs,
Portal permissions and Partner Hub configuration.

### ERP owns

Only the domains confirmed by the real ERP contract, expected to include
fulfillment, production/PMC progress, shipping and ERP identifiers. Inventory,
finance and customer master ownership must not be assumed before interface and
governance review.

## Operating principles

- IT provides platform custody and integrations; IT is not the default uploader
  or editor for every business domain.
- Production fixes do not silently overwrite business-owned data.
- Bulk imports, merges, deletion and replay of ERP jobs require owner approval
  proportional to impact.
- Mapping identifiers are references, not a second copy of the ERP master.
- Staging uses production-like data only under approved sanitization and access
  controls; Development uses test/demo data.
