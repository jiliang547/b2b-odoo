"""Create only the disposable pgvector development database (never the 8070 DB)."""
import psycopg2
from psycopg2 import sql

DB = "b2b_ai_test_20260918"
connection = psycopg2.connect(host="127.0.0.1", port=15432, dbname="postgres", user="postgres", password="ai_local_isolated_test")
connection.autocommit = True
with connection.cursor() as cursor:
    cursor.execute("SELECT 1 FROM pg_roles WHERE rolname='ai_test'")
    if not cursor.fetchone():
        cursor.execute("CREATE ROLE ai_test LOGIN CREATEDB PASSWORD 'ai_local_isolated_test'")
    cursor.execute("SELECT 1 FROM pg_database WHERE datname=%s", [DB])
    if not cursor.fetchone():
        cursor.execute(sql.SQL("CREATE DATABASE {} OWNER ai_test").format(sql.Identifier(DB)))
connection.close()
connection = psycopg2.connect(host="127.0.0.1", port=15432, dbname=DB, user="postgres", password="ai_local_isolated_test")
connection.autocommit = True
with connection.cursor() as cursor:
    cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
print("Isolated AI database ready on 127.0.0.1:15432; live 8070 database unchanged.")
connection.close()
