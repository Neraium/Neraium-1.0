"""Read-only runtime schema contracts. Catalog mismatches never trigger repair.

Contracts are reviewed snapshots of the authoritative migrations on a clean
fixture, not snapshots of production. Additional objects are allowed; required
objects, definitions and ledger state must remain compatible.
"""
from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
import re
import sqlite3
from typing import Any


class SchemaIncompatibilityError(RuntimeError):
    """Safe object-level diagnostics; never include connection details or data."""


@lru_cache(maxsize=None)
def load_contract(name: str) -> dict[str, Any]:
    return json.loads(Path(__file__).with_name("schema_contracts").joinpath(f"{name}.json").read_text())


def _normalize(definition: str, schema: str = "") -> str:
    if schema:
        definition = definition.replace(f'"{schema}".', '').replace(f'{schema}.', '')
    definition = re.sub(r'\bIF NOT EXISTS\s+', '', definition, flags=re.I)
    return re.sub(r'\s+', ' ', definition).strip().rstrip(';')


def postgres_catalog(connection: Any, schema: str) -> dict[str, Any]:
    """SELECT-only catalog inventory; includes disabled/invalid integrity guards."""
    from psycopg.rows import tuple_row
    result: dict[str, Any] = {key: {} for key in ("tables", "indexes", "constraints", "sequences", "functions", "triggers")}
    with connection.cursor(row_factory=tuple_row) as cursor:
        cursor.execute("""
            SELECT c.relname, a.attname, format_type(a.atttypid, a.atttypmod),
                   a.attnotnull, a.attidentity, a.attgenerated, pg_get_expr(d.adbin,d.adrelid)
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            JOIN pg_attribute a ON a.attrelid=c.oid
            LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
            WHERE n.nspname=%s AND c.relkind IN ('r','p')
              AND a.attnum>0 AND NOT a.attisdropped
            ORDER BY c.relname,a.attnum
        """, (schema,))
        for table, column, data_type, not_null, identity, generated, default in cursor.fetchall():
            result["tables"].setdefault(table, {})[column] = [data_type, not_null, identity, generated, _normalize(default, schema) if default else None]
        cursor.execute("""
            SELECT c.relname, pg_get_indexdef(c.oid), i.indisvalid, i.indisready
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            JOIN pg_index i ON i.indexrelid=c.oid WHERE n.nspname=%s
        """, (schema,))
        for name, definition, valid, ready in cursor.fetchall():
            result["indexes"][name] = [_normalize(definition, schema), valid, ready]
        cursor.execute("""
            SELECT c.relname, k.conname, pg_get_constraintdef(k.oid), k.convalidated
            FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s
        """, (schema,))
        for table, name, definition, valid in cursor.fetchall():
            result["constraints"][f"{table}.{name}"] = [_normalize(definition, schema), valid]
        cursor.execute("""
            SELECT c.relname, format_type(s.seqtypid,NULL),s.seqincrement,s.seqmin,s.seqmax,s.seqcycle,
                   t.relname,a.attname
            FROM pg_sequence s JOIN pg_class c ON c.oid=s.seqrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            LEFT JOIN pg_depend d ON d.classid='pg_class'::regclass AND d.objid=c.oid AND d.deptype IN ('a','i')
            LEFT JOIN pg_class t ON t.oid=d.refobjid
            LEFT JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum=d.refobjsubid
            WHERE n.nspname=%s
        """, (schema,))
        for row in cursor.fetchall():
            result["sequences"][row[0]] = list(row[1:])
        cursor.execute("""
            SELECT p.proname,pg_get_function_identity_arguments(p.oid),
                   pg_get_function_result(p.oid),l.lanname,p.prosrc,p.prosecdef
            FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
            JOIN pg_language l ON l.oid=p.prolang WHERE n.nspname=%s
        """, (schema,))
        for name, args, returns, language, source, definer in cursor.fetchall():
            result["functions"][f"{name}({args})"] = [returns, language, _normalize(source, schema), definer]
        cursor.execute("""
            SELECT c.relname,t.tgname,pg_get_triggerdef(t.oid),t.tgenabled
            FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname=%s AND NOT t.tgisinternal
        """, (schema,))
        for table, name, definition, enabled in cursor.fetchall():
            result["triggers"][f"{table}.{name}"] = [_normalize(definition, schema), enabled]
    return result


def sqlite_catalog(connection: sqlite3.Connection) -> dict[str, Any]:
    result: dict[str, Any] = {key: {} for key in ("tables", "indexes", "foreign_keys", "triggers")}
    objects = connection.execute("SELECT type,name,tbl_name,sql FROM sqlite_master").fetchall()
    for kind, name, table, definition in objects:
        quoted = '"' + name.replace('"', '""') + '"'
        if kind == "table":
            result["tables"][name] = {row[1]: [row[2], row[5]] for row in connection.execute(f"PRAGMA table_info({quoted})")}
            result["foreign_keys"][name] = sorted([list(row[1:]) for row in connection.execute(f"PRAGMA foreign_key_list({quoted})")])
            for row in connection.execute(f"PRAGMA index_list({quoted})"):
                index_quote = '"' + row[1].replace('"', '""') + '"'
                columns = [list(item[2:]) for item in connection.execute(f"PRAGMA index_xinfo({index_quote})") if item[-1]]
                # Autoindex names change when a migration rebuilds a legacy table.
                key = row[1] if row[3] == 'c' else f"{name}:{row[3]}:{columns}"
                index_sql = next((o[3] for o in objects if o[1] == row[1]), None)
                result["indexes"][key] = [row[2], row[4], columns, _normalize(index_sql) if index_sql else None]
        elif kind == "trigger":
            result["triggers"][name] = _normalize(definition)
    return result


def _compare(actual: dict[str, Any], contract: dict[str, Any], label: str) -> None:
    objects = contract["objects"]
    for category in ["tables", *(key for key in objects if key != "tables")]:
        required = objects[category]
        for name, expected in required.items():
            found = actual.get(category, {}).get(name)
            if category == "tables" and isinstance(found, dict):
                for column, specification in expected.items():
                    value = found.get(column)
                    # Legacy PostgreSQL auth timestamps are explicitly supported.
                    compatible = value == specification
                    if isinstance(specification[0], list) and value:
                        compatible = value[0] in specification[0] and value[1:] == specification[1:]
                    if not compatible:
                        raise SchemaIncompatibilityError(f"schema_incompatible:{label}:column:{name}.{column}")
            elif found != expected:
                raise SchemaIncompatibilityError(f"schema_incompatible:{label}:{category}:{name}")


def verify_postgres(connection: Any, schema: str, name: str) -> None:
    from psycopg import sql
    connection.execute(sql.SQL("SET LOCAL search_path TO {}, pg_catalog").format(sql.Identifier(schema)))
    contract = load_contract(name)
    _compare(postgres_catalog(connection, schema), contract, schema)
    with connection.cursor() as cursor:
        cursor.execute(sql.SQL("SELECT {} FROM {}.{}").format(
            sql.Identifier(contract["ledger_column"]), sql.Identifier(schema), sql.Identifier(contract["ledger_table"])))
        rows = cursor.fetchall()
    if {row[0] for row in rows} != set(contract["migration_ids"]):
        raise SchemaIncompatibilityError(f"schema_incompatible:{schema}:migration_state:{contract['ledger_table']}")


def verify_sqlite_file(path: Path, name: str) -> None:
    # mode=ro prevents even creation of an empty file on a missing database.
    try:
        connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    except sqlite3.OperationalError:
        raise SchemaIncompatibilityError(f"schema_incompatible:{name}:database_missing") from None
    try:
        connection.execute("PRAGMA query_only = ON")
        contract = load_contract(name)
        _compare(sqlite_catalog(connection), contract, name)
        if not contract.get("ledger_table"):
            return
        rows = connection.execute(f'SELECT "{contract["ledger_column"]}" FROM "{contract["ledger_table"]}"').fetchall()
        if {row[0] for row in rows} != set(contract["migration_ids"]):
            raise SchemaIncompatibilityError(f"schema_incompatible:{name}:migration_state")
    finally:
        connection.close()
