# System Assets Register

Status: **Template requiring company owner assignment**

Do not put passwords, API keys, recovery codes or bearer tokens in this file or
any Git revision. Store them in approved company-controlled systems.

| Asset | Company owner | Technical admin | Recovery method | MFA | Environment | Purpose / notes |
|---|---|---|---|---|---|---|
| GitHub organization/account | TBD company role | TBD named admin | company-controlled recovery email and backup owner | Required | All | Repository ownership and access review |
| `jiliang547/b2b-odoo` repository | Must be transferred/confirmed as company-controlled | TBD maintainers | GitHub owner recovery and repository mirror | Required for admins | All | Code source of truth; currently public |
| Odoo Enterprise subscription | TBD company legal owner | TBD subscription admin | Odoo account recovery/support contract | Required | All | Odoo 19 Enterprise entitlement |
| Odoo.sh project | TBD company owner | TBD platform admins | Odoo account/support plus documented project recovery | Required | Dev/Staging/Prod | Build, deploy, databases and backups |
| Production database | Company | minimum Production admins | Odoo.sh backups and tested restore procedure | Required | Production | Live business data |
| Staging database | Company | platform/test admins | rebuild from approved source and sanitized backup | Required | Staging | UAT and release verification |
| Development databases | Company | developers | rebuild from Git and test data | Required | Development | Module development and automated tests |
| Domain registrar | Company | TBD DNS admins | registrar recovery and lock procedure | Required | Production | Domain ownership |
| DNS/CDN account | Company | TBD DNS/platform admins | provider recovery and exported configuration | Required | Production | DNS, TLS and optional media delivery |
| ERP API service account | Company | minimum integration admins | ERP owner reset/rotation process | Required where supported | per environment | Least-privilege integration identity |
| ERP sandbox | Company | integration team | ERP sandbox recreation procedure | Required | Dev/Staging | Adapter and UAT testing |
| Transactional email account | Company | platform/email admins | provider recovery and DNS records backup | Required | per environment | Invitations, orders and notifications |
| Secret/password manager | Company | security-designated admins | documented break-glass recovery | Required | All | Odoo.sh/ERP/provider secrets |
| Backup/restore runbook | Company | platform admins | controlled offline/exported copy | N/A | Production | Recovery steps and test evidence |
| Monitoring/error reporting | Company | platform/support admins | provider recovery and config export | Required | Staging/Prod | Availability and sanitized diagnostics |
| Video/CDN provider, if used | Company | Marketing + platform admins | provider recovery and asset inventory | Required | Production | Large public media; private content needs access control |

## Required controls before Production

1. Replace every `TBD` with a company role and at least two recoverable named
   administrators where appropriate.
2. Confirm the GitHub repository and Odoo.sh project are company-controlled.
3. Enable MFA for all owner/admin accounts and prohibit shared daily root use.
4. Record credential rotation intervals outside Git.
5. Test database restoration and document date, owner and result.
6. Verify Development, Staging and Production use distinct ERP credentials and
   endpoints.
7. Review public repository exposure before any integration configuration is
   committed; secrets and customer data are never permitted in Git.
