# Lucky Tone Partner Hub

Lucky Tone Partner Hub is an Odoo 19 Enterprise/Odoo.sh B2B website project.
The implementation follows the V4.1 Final architecture: **Odoo Native First,
thin extensions, and custom models only for confirmed gaps**.

## Current phase

The repository is at the architecture gate. No production business module has
been implemented yet. The following documents define the proposed boundary
between Odoo-native functionality, extensions, and custom development:

- [Odoo native gap analysis](ODOO_NATIVE_GAP_ANALYSIS.md)
- [Functional coverage matrix](FUNCTIONAL_COVERAGE_MATRIX.md)
- [Architecture](ARCHITECTURE.md)
- [RBAC matrix](RBAC_MATRIX.md)
- [Data ownership](DATA_OWNERSHIP.md)
- [System assets](SYSTEM_ASSETS.md)

These documents require business and technical approval before module
implementation begins.

## Target platform

- Odoo 19 Enterprise
- Odoo.sh Development / Staging / Production
- GitHub as code source of truth
- Odoo Website, eCommerce, Portal, Sales, Helpdesk, Repairs and Product
  Documents as native foundations

The exact Enterprise module availability, model fields, view XML IDs and
cross-module behavior must be validated in the first Odoo.sh Development build.
