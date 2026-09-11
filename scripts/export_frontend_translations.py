"""Run with Odoo shell: export native translation templates for the custom apps.

Generated POT files are source catalogs, not a second translation runtime.
"""
from pathlib import Path
from odoo.tools.translate import trans_export

root = Path.cwd() / "custom_addons"
for module in ("b2b_website", "b2b_core", "b2b_sample", "b2b_erp_connector"):
    folder = root / module / "i18n"
    folder.mkdir(exist_ok=True)
    with (folder / (module + ".pot")).open("wb") as output:
        trans_export(False, [module], output, "po", env)
    print("EXPORTED", module)
