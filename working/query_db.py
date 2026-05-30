#!/usr/bin/env python3
"""查询 BIRD Mini-Dev 数据集中的 SQLite 数据库表。"""

import argparse
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_ROOT = PROJECT_ROOT / "data" / "dev_databases"


def get_db_path(db_id: str) -> Path:
    db_path = DB_ROOT / db_id / f"{db_id}.sqlite"
    if not db_path.exists():
        raise FileNotFoundError(f"数据库不存在: {db_path}")
    return db_path


def list_databases() -> list[str]:
    return sorted(
        d.name for d in DB_ROOT.iterdir() if d.is_dir() and (d / f"{d.name}.sqlite").exists()
    )


def list_tables(db_id: str) -> list[str]:
    conn = sqlite3.connect(get_db_path(db_id))
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in cursor.fetchall() if row[0] != "sqlite_sequence"]
    conn.close()
    return tables


def show_schema(db_id: str, table: str | None = None) -> None:
    conn = sqlite3.connect(get_db_path(db_id))
    cursor = conn.cursor()

    if table:
        cursor.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        )
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"表 '{table}' 在数据库 '{db_id}' 中不存在")
        print(row[0])
    else:
        for t in list_tables(db_id):
            cursor.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                (t,),
            )
            print(cursor.fetchone()[0])
            print()

    conn.close()


def format_table(columns: list[str], rows: list[tuple], max_col_width: int = 40) -> str:
    if not rows:
        return "（无数据）"

    str_rows = [[str(v) if v is not None else "NULL" for v in row] for row in rows]
    widths = [
        min(max(len(col), max(len(r[i]) for r in str_rows)), max_col_width)
        for i, col in enumerate(columns)
    ]

    def clip(text: str, width: int) -> str:
        return text[: width - 1] + "…" if len(text) > width else text

    header = " | ".join(col.ljust(widths[i]) for i, col in enumerate(columns))
    sep = "-+-".join("-" * w for w in widths)
    body = "\n".join(
        " | ".join(clip(r[i], widths[i]).ljust(widths[i]) for i in range(len(columns)))
        for r in str_rows
    )
    return f"{header}\n{sep}\n{body}"


def query_table(db_id: str, table: str, limit: int = 10, offset: int = 0) -> None:
    tables = list_tables(db_id)
    if table not in tables:
        raise ValueError(f"表 '{table}' 不存在，可用表: {', '.join(tables)}")

    safe_table = f"`{table}`" if table.lower() in ("order", "by", "group") else table
    sql = f"SELECT * FROM {safe_table} LIMIT ? OFFSET ?"

    conn = sqlite3.connect(get_db_path(db_id))
    cursor = conn.cursor()
    cursor.execute(sql, (limit, offset))
    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()
    conn.close()

    print(f"数据库: {db_id}  表: {table}  显示 {len(rows)} 行 (limit={limit}, offset={offset})")
    print(format_table(columns, rows))


def execute_sql(db_id: str, sql: str, limit: int = 50) -> None:
    conn = sqlite3.connect(get_db_path(db_id))
    cursor = conn.cursor()
    cursor.execute(sql)

    if cursor.description is None:
        conn.commit()
        print(f"执行成功，影响行数: {cursor.rowcount}")
        conn.close()
        return

    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()[:limit]
    conn.close()

    print(f"数据库: {db_id}  返回 {len(rows)} 行" + (f"（最多显示 {limit} 行）" if len(rows) == limit else ""))
    print(format_table(columns, rows))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="查询 BIRD 数据集中的 SQLite 数据库表")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("dbs", help="列出所有数据库")

    p_tables = sub.add_parser("tables", help="列出指定数据库的所有表")
    p_tables.add_argument("db_id", help="数据库 ID，如 debit_card_specializing")

    p_schema = sub.add_parser("schema", help="查看表结构（CREATE TABLE）")
    p_schema.add_argument("db_id")
    p_schema.add_argument("table", nargs="?", help="表名，省略则显示全部表")

    p_query = sub.add_parser("query", help="查询表数据")
    p_query.add_argument("db_id")
    p_query.add_argument("table")
    p_query.add_argument("-n", "--limit", type=int, default=10, help="返回行数，默认 10")
    p_query.add_argument("-o", "--offset", type=int, default=0, help="偏移量，默认 0")

    p_sql = sub.add_parser("sql", help="执行自定义 SQL")
    p_sql.add_argument("db_id")
    p_sql.add_argument("sql", help="SQL 语句")
    p_sql.add_argument("-n", "--limit", type=int, default=50, help="最多显示行数，默认 50")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "dbs":
            for db_id in list_databases():
                tables = list_tables(db_id)
                print(f"{db_id}  ({len(tables)} 张表)")
        elif args.command == "tables":
            for t in list_tables(args.db_id):
                print(t)
        elif args.command == "schema":
            show_schema(args.db_id, args.table)
        elif args.command == "query":
            query_table(args.db_id, args.table, args.limit, args.offset)
        elif args.command == "sql":
            execute_sql(args.db_id, args.sql, args.limit)
    except (FileNotFoundError, ValueError, sqlite3.Error) as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
