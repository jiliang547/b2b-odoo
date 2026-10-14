"""Isolated UI fixture, NOT a model-quality test or production entry point.

Only accepts the disposable database/port. Stubs the native transport in this
process so browser interactions exercise the real UI/controller/workflow without
an API key, outbound model request, or charge. Never imported by the addon.
"""
import json
import sys
import time
from pathlib import Path

SERVER = Path("C:/Program Files/Odoo 19.0e.20260805/server")
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))
import odoo
import odoo.cli
from odoo.tools import config

args = ["-c", str(SERVER / "odoo.conf"), "--addons-path=" + str(SERVER / "odoo/addons") + "," + str(REPO / "custom_addons"),
        "--db_host=127.0.0.1", "--db_port=15432", "--db_user=ai_test", "--db_password=ai_local_isolated_test",
        "-d", "b2b_ai_test_20260918", "--db-filter=^b2b_ai_test_20260918$", "--data-dir=" + str(REPO / "output/ai-data"),
        "--http-port=8072", "--http-interface=127.0.0.1", "--max-cron-threads=1", "--logfile=" + str(REPO / "output/ai-ui-fixture.log")]
config.parse_config(args)
odoo.modules.module.initialize_sys_path()
from odoo.addons.b2b_ai.models.service import BoundedNativeAPI
from odoo.addons.b2b_ai.models.configuration import Website

original_ready = Website._b2b_ai_ready


def fixture_ready(self):
    assert self.env.cr.dbname == "b2b_ai_test_20260918"
    state = original_ready(self)
    return "ready" if state == "key_required" else state


def fixture_token(self):
    assert self.env.cr.dbname == "b2b_ai_test_20260918"
    return "not-a-real-key-ui-fixture-only"


def fixture_request(self, *args, **kwargs):
    assert self.env.cr.dbname == "b2b_ai_test_20260918"
    if kwargs.get("endpoint") != "/responses":
        raise ValueError("This UI fixture does not simulate embeddings")
    payload = json.loads(kwargs["body"]["input"][1]["content"][0]["text"])
    if "SIMULATE_TIMEOUT" in payload.get("question", ""):
        raise TimeoutError("Synthetic transport failure")
    if "SIMULATE_SLOW" in payload.get("question", ""):
        time.sleep(12)
    if "evidence" not in payload:
        answer = {"query": payload["question"][:1500], "facts": []}
    else:
        points = [{"text": "UI TEST FIXTURE — " + item["text"], "source_id": key, "evidence_quote": item["text"][:300]}
                  for key, item in list(payload["evidence"].items())[:2]]
        answer = {"points": points, "product_ids": payload["product_ids"][:2],
                  "question": "UI TEST FIXTURE — Which model and installation area should our team confirm?"}
    return {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(answer)}]}]}


Website._b2b_ai_ready = fixture_ready
BoundedNativeAPI._get_api_token = fixture_token
BoundedNativeAPI._request = fixture_request
sys.argv = ["odoo-bin", *args]
odoo.cli.main()
