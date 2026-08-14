"""Source-only checks that do not require an Odoo registry or database."""

from __future__ import annotations

import ast
import py_compile
import re
import sys
from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
ADDONS = ROOT / "custom_addons"
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"ghp_[A-Za-z0-9]{30,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
)


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    modules = sorted(path.parent for path in ADDONS.glob("*/__manifest__.py"))
    if not modules:
        fail("No Odoo modules found")

    xml_count = 0
    python_count = 0
    for module in modules:
        manifest_path = module / "__manifest__.py"
        manifest = ast.literal_eval(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("version", "").split(".", 1)[0] != "19":
            fail(f"{module.name}: version is not an Odoo 19 version")
        for relative in manifest.get("data", []):
            if not (module / relative).is_file():
                fail(f"{module.name}: manifest file is missing: {relative}")
        for bundle in manifest.get("assets", {}).values():
            for asset in bundle:
                asset_path = ADDONS / asset.split("/", 1)[0] / asset.split("/", 1)[1]
                if not asset_path.is_file():
                    fail(f"{module.name}: asset is missing: {asset}")

        ids: set[str] = set()
        for path in module.rglob("*.xml"):
            xml_count += 1
            root = ElementTree.parse(path).getroot()
            for element in root.iter():
                xml_id = element.attrib.get("id")
                if xml_id and xml_id in ids:
                    fail(f"{module.name}: duplicate XML id {xml_id}")
                if xml_id:
                    ids.add(xml_id)

        for path in module.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            python_count += 1
            py_compile.compile(path, doraise=True)

    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts or path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                fail(f"Possible committed secret in {path.relative_to(ROOT)}")

    print(f"OK: {len(modules)} modules, {python_count} Python files, {xml_count} XML files")


if __name__ == "__main__":
    main()
