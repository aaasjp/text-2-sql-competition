#!/usr/bin/env python3
"""smolagents Text2SQL Demo — 使用 ToolCallingAgent + BIRD SQLite 数据库。"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from dotenv import load_dotenv
import os

WORKING_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = WORKING_DIR.parent
DB_ROOT = PROJECT_ROOT / "data" / "dev_databases"
DEV_JSON = PROJECT_ROOT / "data" / "dev.json"
SMOLAGENTS_SRC = WORKING_DIR / "smolagents" / "src"

load_dotenv(WORKING_DIR / ".env")

try:
    from smolagents import OpenAIModel, ToolCallingAgent, tool
except ImportError:
    if SMOLAGENTS_SRC.is_dir():
        sys.path.insert(0, str(SMOLAGENTS_SRC))
        from smolagents import OpenAIModel, ToolCallingAgent, tool
    else:
        raise SystemExit(
            "未找到 smolagents，请先安装:\n"
            "  cd working && pip install -r requirements.txt"
        ) from None


def get_db_path(db_id: str) -> Path:
    db_path = DB_ROOT / db_id / f"{db_id}.sqlite"
    if not db_path.exists():
        raise FileNotFoundError(f"数据库不存在: {db_path}")
    return db_path


def get_llm_config() -> dict[str, str | None]:
    return {
        "api_key": os.environ.get("API_KEY"),
        "base_url": os.environ.get("BASE_URL"),
        "model": os.environ.get("MODEL", "DeepSeek-V4-Flash"),
    }


def build_sql_tools(db_id: str):
    """为指定数据库创建 smolagents 工具集。"""

    @tool
    def list_db_tables() -> str:
        """列出当前数据库中的所有表名。"""
        conn = sqlite3.connect(get_db_path(db_id))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall() if row[0] != "sqlite_sequence"]
        conn.close()
        return ", ".join(tables)

    @tool
    def get_table_schema(table_name: str) -> str:
        """获取指定表的 CREATE TABLE 语句。

        Args:
            table_name: 表名
        """
        conn = sqlite3.connect(get_db_path(db_id))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return f"表 '{table_name}' 不存在"
        return row[0]

    @tool
    def execute_sql(sql: str) -> str:
        """在当前 SQLite 数据库上执行 SELECT 查询并返回结果。

        Args:
            sql: 要执行的 SELECT 语句
        """
        if not sql.strip().upper().startswith("SELECT"):
            return "错误: 仅允许 SELECT 查询"

        conn = sqlite3.connect(get_db_path(db_id))
        cursor = conn.cursor()
        try:
            cursor.execute(sql)
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
        except sqlite3.Error as e:
            conn.close()
            return f"SQL 执行错误: {e}"
        conn.close()

        if not rows:
            return "（无结果）"

        lines = [" | ".join(columns)]
        for row in rows[:30]:
            lines.append(" | ".join(str(v) for v in row))
        if len(rows) > 30:
            lines.append(f"... 共 {len(rows)} 行")
        return "\n".join(lines)

    return [list_db_tables, get_table_schema, execute_sql]


def build_agent(
    db_id: str,
    max_steps: int = 50,
    planning_interval: int | None = None,
) -> ToolCallingAgent:
    cfg = get_llm_config()
    if not cfg["api_key"]:
        raise SystemExit("请在 working/.env 中配置 API_KEY")

    model = OpenAIModel(
        model_id=cfg["model"],
        api_base=cfg["base_url"],
        api_key=cfg["api_key"],
        temperature=0.0,
    )

    return ToolCallingAgent(
        tools=build_sql_tools(db_id),
        model=model,
        max_steps=max_steps,
        planning_interval=planning_interval,
        verbosity_level=2,
    )


def load_dev_sample(index: int = 0) -> dict:
    with open(DEV_JSON, encoding="utf-8") as f:
        samples = json.load(f)
    if index < 0 or index >= len(samples):
        raise IndexError(f"dev 样本索引越界: {index}，共 {len(samples)} 条")
    return samples[index]


def build_task(question: str, db_id: str, evidence: str | None = None) -> str:
    parts = [
        f"You are working with SQLite database '{db_id}'.",
        "Use the provided tools to explore schema, run SQL, and answer the question.",
        "When done, call final_answer with the query result.",
        f"\nQuestion: {question}",
    ]
    if evidence:
        parts.append(f"\nExternal Knowledge: {evidence}")
    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser(description="smolagents Text2SQL Demo")
    parser.add_argument("--db_id", help="数据库 ID，如 debit_card_specializing")
    parser.add_argument("--question", help="自然语言问题")
    parser.add_argument("--evidence", default="", help="外部知识提示")
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        help="使用 dev.json 中第 N 条样本（0-based）",
    )
    parser.add_argument("--max-steps", type=int, default=10, help="Agent 最大步数")
    parser.add_argument(
        "--planning-interval",
        type=int,
        default=None,
        help="规划间隔步数，1 表示每步 action 前都规划；不传则关闭 planning",
    )
    args = parser.parse_args()

    if args.sample is not None:
        sample = load_dev_sample(args.sample)
        db_id = sample["db_id"]
        question = sample["question"]
        evidence = sample.get("evidence", "")
        print(f"使用 dev 样本 #{args.sample} (question_id={sample['question_id']})")
    else:
        db_id = args.db_id or "debit_card_specializing"
        question = args.question or (
            "What is the ratio of customers who pay in EUR "
            "against customers who pay in CZK?"
        )
        evidence = args.evidence

    print(f"数据库: {db_id}")
    print(f"模型:   {get_llm_config()['model']}")
    print(f"问题:   {question}\n")

    agent = build_agent(
        db_id,
        max_steps=args.max_steps,
        planning_interval=args.planning_interval,
    )
    result = agent.run(build_task(question, db_id, evidence or None))

    print("\n" + "=" * 50)
    print("最终答案:")
    print(result)


if __name__ == "__main__":
    main()
