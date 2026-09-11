"""Build standard PO catalogs from an AI translation worksheet; no runtime service.

Usage: python scripts/build_frontend_translations.py worksheet.tsv
The worksheet has source, Spanish, French and Arabic columns separated by tabs.
Use --missing to list remaining customer-facing terms for translation.
"""
import argparse
import copy
import csv
import re
from pathlib import Path
import polib

ROOT = Path(__file__).resolve().parents[1]
LANGUAGES = ("es", "fr", "ar")

def normalize(value):
    return " ".join(value.split())

def segments(value):
    return re.split(r'(<[^>]+>)', value)

def needs_translation(value):
    value = re.sub(r'%\([^)]+\)s|%s|\{\{.*?\}\}', '', value)
    return bool(re.search(r'[a-zA-Z]', value)) and normalize(value) not in {
        'POWER &amp; GRACE', 'POWER &amp; GRACE PARTNER HUB', 'POWER & GRACE', 'POWER & GRACE PARTNER HUB',
        'Power &amp; Grace', 'Lucky Tone', 'Partner Hub', 'SKU', 'SKU:', 'PDF', 'ERP', 'MOQ',
        'MB', 'IP65', 'CE', 'RoHS', 'ISO 9001', 'WhatsApp', 'OEM', 'ODM', 'ZIP', 'STEP',
        '/contact', '0s', 'John Doe', 'name@company.com', 'www.company.com',
    }

def customer_facing(entry, module):
    if module != "b2b_website":
        return any("odoo-python" in entry.comment or "selection" in loc or
                   "b2b.customer.type,name" in loc or "b2b.product" in loc
                   for loc, _ in entry.occurrences)
    backend = ("_views", "security.", "ir.model", "mail.message.subtype", "ir.actions", "ir.ui.menu")
    return any((loc.startswith("code:") and "/tests/" not in loc) or
               (loc.startswith("model_terms:ir.ui.view,") and not any(word in loc for word in backend)) or
               "mail.template" in loc or "b2b.faq" in loc or "res.partner.category" in loc or
               "selection:" in loc for loc, _ in entry.occurrences)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("worksheet", nargs="?")
    parser.add_argument("--missing", action="store_true")
    parser.add_argument("--native", help="Optional native Odoo addons folder for exact-match translations")
    args = parser.parse_args()
    translations = {}
    # Reuse previously reviewed PO segments when completing composite QWeb terms.
    known = [{} for _ in LANGUAGES]
    for index, language in enumerate(LANGUAGES):
        for path in sorted((ROOT / "custom_addons").glob(f"*/i18n/{language}.po")):
            for entry in polib.pofile(str(path)):
                original, translated = segments(entry.msgid), segments(entry.msgstr)
                if len(original) == len(translated):
                    for src, dst in zip(original, translated):
                        if not src.startswith('<') and normalize(src) and normalize(dst):
                            known[index].setdefault(normalize(src), normalize(dst))
    for term in set.intersection(*(set(values) for values in known)):
        translations[term] = [values[term] for values in known]
    if args.native:
        native = [{} for _ in LANGUAGES]
        for index, language in enumerate(LANGUAGES):
            for path in sorted(Path(args.native).glob(f"*/i18n/{language}.po")):
                for entry in polib.pofile(str(path)):
                    if entry.msgstr and not entry.obsolete and not entry.fuzzy:
                        native[index].setdefault(normalize(entry.msgid), entry.msgstr)
        for term in set.intersection(*(set(values) for values in native)):
            translations[term] = [values[term] for values in native]
    if args.worksheet:
        with open(args.worksheet, encoding="utf-8") as stream:
            for row in csv.reader(stream, delimiter="\t", quoting=csv.QUOTE_NONE):
                if not row or row[0].startswith("#"):
                    continue
                if len(row) != 4:
                    raise ValueError(f"Expected four columns: {row!r}")
                translations[normalize(row[0].replace("\\n", "\n"))] = [v.replace("\\n", "\n") for v in row[1:]]
    missing = set()
    for pot_path in sorted((ROOT / "custom_addons").glob("*/i18n/*.pot")):
        module = pot_path.stem
        template = polib.pofile(str(pot_path))
        for index, language in enumerate(LANGUAGES):
            po_path = pot_path.with_name(language + ".po")
            catalog = polib.pofile(str(po_path)) if po_path.exists() else polib.POFile()
            catalog.metadata = dict(template.metadata, **{
                "Language": language,
                "Last-Translator": "Partner Hub AI translation",
                "Content-Transfer-Encoding": "8bit",
                "Plural-Forms": "nplurals=6; plural=n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 : n%100>=11 && n%100<=99 ? 4 : 5;" if language == "ar" else "nplurals=2; plural=(n > 1);" if language == "fr" else "nplurals=2; plural=(n != 1);",
            })
            for source in template:
                entry = catalog.find(source.msgid)
                parts = segments(source.msgid)
                unknown = [normalize(part) for part in parts if not part.startswith('<') and needs_translation(part) and normalize(part) not in translations]
                translated = None
                if not unknown:
                    translated = []
                    for lang_index in range(3):
                        translated.append(''.join(
                            part if part.startswith('<') or normalize(part) not in translations else
                            re.sub(r'\S[\s\S]*\S|\S', lambda match: translations[normalize(part)][lang_index], part, count=1)
                            for part in parts
                        ))
                if translated and (customer_facing(source, module) or source.msgid in translations):
                    if not entry:
                        entry = copy.deepcopy(source)
                        catalog.append(entry)
                    entry.msgstr = translated[index]
                    entry.occurrences = source.occurrences
                    entry.comment = source.comment
                    entry.flags = [flag for flag in source.flags if flag != "fuzzy"]
                if customer_facing(source, module) and not (entry and entry.msgstr):
                    missing.update(unknown)
            if not args.missing:
                catalog.save(str(po_path))
                print(f"{module}/{language}: {len(catalog.translated_entries())} translated terms")
    if args.missing:
        for term in sorted(missing):
            print(term.replace("\n", "\\n"))
        print(f"REMAINING: {len(missing)}")

if __name__ == "__main__":
    main()
