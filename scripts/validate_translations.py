"""Check shipped native PO files for broken placeholders, markup and coverage."""
from collections import Counter
from pathlib import Path
import re
import polib

from build_frontend_translations import customer_facing

root = Path(__file__).resolve().parents[1] / "custom_addons"
count = 0
for template in root.glob("*/i18n/*.pot"):
    terms = polib.pofile(str(template))
    for language in ("es", "fr", "ar"):
        catalog = polib.pofile(str(template.with_name(language + ".po")), check_for_duplicates=True)
        for source in terms:
            if not customer_facing(source, template.stem):
                continue
            entry = catalog.find(source.msgid)
            assert entry and entry.msgstr and not entry.fuzzy, (template.stem, language, source.msgid)
        for entry in catalog:
            placeholder = r'%(?:\([^)]+\))?[#0 +\-]*\d*(?:\.\d+)?[sdfg]|#\{[^}]+\}|\{\{[^}]+\}\}'
            assert Counter(re.findall(placeholder, entry.msgid)) == Counter(re.findall(placeholder, entry.msgstr)), (language, entry.msgid)
            assert re.findall(r'<[^>]+>', entry.msgid) == re.findall(r'<[^>]+>', entry.msgstr), (language, entry.msgid)
            count += 1
print(f"OK: {count} native translation entries; placeholders, markup and frontend coverage checked")
