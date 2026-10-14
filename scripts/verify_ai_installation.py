"""Reproduce fresh-install and upgrade paths on disposable databases only.

Uses the existing isolated pgvector server, never the local 8070 database.
The baseline tree must be exported from the pre-AI Git commit beforehand.
No provider key is set and no external model call is made.
"""
import argparse
from pathlib import Path
import subprocess
import sys

import psycopg2
from psycopg2 import sql

ROOT = Path(__file__).resolve().parents[1]
SERVER = Path(r"C:\Program Files\Odoo 19.0e.20260805\server")
DATABASES = {"fresh": "b2b_ai_fresh_20260918", "upgrade": "b2b_ai_upgrade_20260918"}


def connect(db, admin=False):
    return psycopg2.connect(host="127.0.0.1", port=15432, dbname=db,
                           user="postgres" if admin else "ai_test", password="ai_local_isolated_test")


def prepare(db):
    conn = connect("postgres", True)
    try:
        conn.autocommit = True
        with conn.cursor() as cr:
            cr.execute("SELECT 1 FROM pg_database WHERE datname=%s", [db])
            if cr.fetchone():
                raise RuntimeError("Refusing to overwrite an existing test database: " + db)
            cr.execute(sql.SQL("CREATE DATABASE {} OWNER ai_test").format(sql.Identifier(db)))
    finally:
        conn.close()
    with connect(db, True) as conn, conn.cursor() as cr:
        cr.execute("CREATE EXTENSION IF NOT EXISTS vector")


def run(db, addons, operation, log):
    command = [sys.executable, str(SERVER / "odoo-bin"), "-c", str(SERVER / "odoo.conf"),
               "--addons-path=" + str(SERVER / "odoo/addons") + "," + str(addons),
               "--db_host=127.0.0.1", "--db_port=15432", "--db_user=ai_test",
               "--db_password=ai_local_isolated_test", "-d", db,
               "--data-dir=" + str(ROOT / "output/ai-data"), "--no-http", "--without-demo=True",
               "--max-cron-threads=0", "--stop-after-init", operation, "b2b_management",
               "--logfile=" + str(ROOT / "output" / log)]
    print("Running", db, operation, "b2b_management (no explicit AI install)", flush=True)
    subprocess.run(command, check=True, cwd=ROOT)


def verify(db, expect_ai):
    with connect(db) as conn, conn.cursor() as cr:
        cr.execute("SELECT name,state FROM ir_module_module WHERE name IN ('b2b_management','b2b_ai','ai','ai_app') ORDER BY name")
        states = dict(cr.fetchall())
        print("Module states:", states, flush=True)
        assert states.get("b2b_management") == "installed", states
        if not expect_ai:
            assert states.get("b2b_ai") != "installed", states
            return
        assert all(states.get(name) == "installed" for name in ("b2b_ai", "ai", "ai_app")), states
        cr.execute("SELECT id,b2b_ai_enabled,b2b_ai_initialized,b2b_ai_agent_id,b2b_ai_user_daily_limit FROM website ORDER BY id")
        sites = cr.fetchall()
        assert sites and all(row[1] and row[2] and row[3] and row[4] == 30 for row in sites), sites
        print("Website defaults:", sites, flush=True)
        cr.execute("SELECT COUNT(*) FROM ir_config_parameter WHERE key='ai.openai_key' AND value NOT IN ('','False')")
        assert cr.fetchone()[0] == 0, "A disposable installation must have no provider key"
        cr.execute("SELECT COUNT(*) FROM b2b_ai_source WHERE published=true")
        print("Published FAQ sources:", cr.fetchone()[0], flush=True)
        cr.execute("SELECT COUNT(*) FROM ai_agent_source")
        assert cr.fetchone()[0] == 0, "Installation must not enqueue paid document indexing"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", choices=DATABASES)
    args = parser.parse_args()
    db = DATABASES[args.scenario]
    prepare(db)
    if args.scenario == "upgrade":
        baseline = ROOT / "output/ai-install-baseline/custom_addons"
        assert baseline.is_dir() and not (baseline / "b2b_ai").exists()
        run(db, baseline, "-i", "ai-legacy-install.log")
        verify(db, False)
        run(db, ROOT / "custom_addons", "-u", "ai-existing-upgrade.log")
    else:
        run(db, ROOT / "custom_addons", "-i", "ai-fresh-install.log")
    verify(db, True)
    print(args.scenario.upper() + " PASS", flush=True)
