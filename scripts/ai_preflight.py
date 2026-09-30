"""Read-only AI prerequisites; never print connection or provider secrets."""
import argparse
import configparser
import json

import psycopg2

parser = argparse.ArgumentParser()
parser.add_argument('--config', required=True)
parser.add_argument('--database', required=True)
args = parser.parse_args()
config = configparser.ConfigParser(interpolation=None)
config.read(args.config)
options = config['options']
connection = psycopg2.connect(
    host=options.get('db_host', 'localhost'), port=options.get('db_port', '5432'),
    user=options['db_user'], password=options['db_password'], dbname=args.database,
)
connection.set_session(readonly=True, autocommit=True)
with connection.cursor() as cursor:
    cursor.execute("SELECT name, default_version, installed_version FROM pg_available_extensions WHERE name='vector'")
    result = {'vector': cursor.fetchall()}
    cursor.execute("SELECT name,state FROM ir_module_module WHERE name IN ('ai','ai_app','ai_website_livechat','b2b_website') ORDER BY name")
    result['modules'] = cursor.fetchall()
    cursor.execute("SELECT count(*) FROM ir_config_parameter WHERE key='ai.openai_key' AND coalesce(value,'') NOT IN ('','False')")
    result['openai_key_configured'] = bool(cursor.fetchone()[0])
    cursor.execute("SELECT datname FROM pg_database WHERE datname LIKE 'b2b%%' ORDER BY datname")
    result['databases'] = [row[0] for row in cursor.fetchall()]
print(json.dumps(result, ensure_ascii=False))
connection.close()
