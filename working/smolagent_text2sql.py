#!/usr/bin/env python3
"""smolagents Text2SQL Demo — 使用 ToolCallingAgent + BIRD SQLite 数据库。"""

import argparse
import json
import sqlite3
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
import os
from tqdm import tqdm

WORKING_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = WORKING_DIR.parent
DB_ROOT = PROJECT_ROOT / "data" / "dev_databases"
DEV_JSON = PROJECT_ROOT / "data" / "dev.json"
PREDICTIONS_DIR = WORKING_DIR / "predictions"
PREDICTION_SQL_PATH = PREDICTIONS_DIR / "prediction_sql.json"
BIRD_SQL_SEP = "\t----- bird -----\t"
AGENT_OUT_DIR = PROJECT_ROOT / "exp_result" / "agent_out"
RUN_AGENT_LOG = WORKING_DIR / "run_agent.log"
SMOLAGENTS_SRC = WORKING_DIR / "smolagents" / "src"

_prediction_lock = threading.Lock()
_run_log_lock = threading.Lock()


class _TeeStream:
    """同时写入终端与 run_agent.log（线程安全）。"""

    def __init__(self, stream, log_path: Path):
        self._stream = stream
        self._log_path = log_path

    def write(self, data: str) -> int:
        if not data:
            return 0
        self._stream.write(data)
        with _run_log_lock:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(data)
        return len(data)

    def flush(self) -> None:
        self._stream.flush()

    def isatty(self) -> bool:
        return self._stream.isatty()

    def fileno(self) -> int:
        return self._stream.fileno()


def setup_run_logging() -> tuple[object, object]:
    """启用 run_agent.log；返回原始 stdout/stderr 供恢复。"""
    RUN_AGENT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with _run_log_lock:
        with open(RUN_AGENT_LOG, "a", encoding="utf-8") as f:
            f.write(f"\n{'=' * 60}\n")
            f.write(f"[{datetime.now().isoformat(timespec='seconds')}] session start\n")
            f.write(f"{'=' * 60}\n")
    orig_out, orig_err = sys.stdout, sys.stderr
    sys.stdout = _TeeStream(orig_out, RUN_AGENT_LOG)
    sys.stderr = _TeeStream(orig_err, RUN_AGENT_LOG)
    return orig_out, orig_err


def teardown_run_logging(orig_out: object, orig_err: object) -> None:
    sys.stdout.flush()
    sys.stderr.flush()
    sys.stdout, sys.stderr = orig_out, orig_err
    with _run_log_lock:
        with open(RUN_AGENT_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat(timespec='seconds')}] session end\n")

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


def _save_prediction_sql(db_id: str, question_id: int, sql: str) -> None:
    with _prediction_lock:
        PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)
        path = PREDICTION_SQL_PATH

        records: list[dict] = []
        if path.exists():
            with open(path, encoding="utf-8") as f:
                records = json.load(f)

        entry = {"question_id": question_id, "db_id": db_id, "sql": sql}
        for i, rec in enumerate(records):
            if rec.get("question_id") == question_id:
                records[i] = entry
                break
        else:
            records.append(entry)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)


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


def build_sql_tools(db_id: str, question_id: int):
    """为指定数据库与 question_id 创建 smolagents 工具集。"""

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
    def get_table_schema(table_names: list[str]) -> str:
        """获取一张或多张表的 CREATE TABLE 语句。

        Args:
            table_names: 表名列表，可一次传入多张表
        """
        if not table_names:
            return "错误: table_names 不能为空"

        conn = sqlite3.connect(get_db_path(db_id))
        cursor = conn.cursor()
        sections: list[str] = []
        for table_name in table_names:
            cursor.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,),
            )
            row = cursor.fetchone()
            if not row:
                sections.append(f"-- {table_name}\n表 '{table_name}' 不存在")
            else:
                sections.append(f"-- {table_name}\n{row[0]}")
        conn.close()
        return "\n\n".join(sections)

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

    @tool
    def record_final_sql(sql: str) -> str:
        """记录产生最终答案的 SQL 查询。在调用 final_answer 之前必须调用此工具。

        Args:
            sql: 产生最终查询结果的 SELECT 语句
        """
        _save_prediction_sql(db_id, question_id, sql)
        return f"已记录 question_id={question_id} 的最终 SQL"

    return [list_db_tables, get_table_schema, execute_sql, record_final_sql]


def build_agent(
    db_id: str,
    question_id: int,
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
        tools=build_sql_tools(db_id, question_id),
        model=model,
        max_steps=max_steps,
        planning_interval=planning_interval,
        verbosity_level=2,
    )


def _eval_output_filename(model: str | None = None) -> str:
    model_id = (model or get_llm_config()["model"] or "agent").replace("/", "__")
    return f"predict_mini_dev_dev_{model_id}_cot_SQLite.json"


def export_predictions_for_eval(
    *,
    prediction_path: Path = PREDICTION_SQL_PATH,
    dev_path: Path = DEV_JSON,
    output_dir: Path = AGENT_OUT_DIR,
    model: str | None = None,
) -> Path:
    """将 prediction_sql.json 转为 BIRD 评估用 JSON（dev.json 下标 -> SQL\\t----- bird -----\\tdb_id）。"""
    with open(dev_path, encoding="utf-8") as f:
        dev_samples = json.load(f)

    predictions_by_qid: dict[int, dict] = {}
    if prediction_path.exists():
        with open(prediction_path, encoding="utf-8") as f:
            for rec in json.load(f):
                predictions_by_qid[rec["question_id"]] = rec

    filled = 0
    result: dict[str, str] = {}
    for index, sample in enumerate(dev_samples):
        db_id = sample["db_id"]
        qid = sample["question_id"]
        pred = predictions_by_qid.get(qid)
        if pred and pred.get("sql", "").strip():
            sql = pred["sql"].strip()
            out_db = pred.get("db_id") or db_id
            result[str(index)] = f"{sql}{BIRD_SQL_SEP}{out_db}"
            filled += 1
        else:
            result[str(index)] = f" {BIRD_SQL_SEP}{db_id}"

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / _eval_output_filename(model)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=4)

    total = len(dev_samples)
    print(
        f"评估 JSON 已导出: {out_path} "
        f"({filled}/{total} 题有预测, {total - filled} 题为占位)"
    )
    return out_path


def load_dev_samples(db_id: str | None = None) -> list[dict]:
    with open(DEV_JSON, encoding="utf-8") as f:
        samples = json.load(f)
    if db_id:
        samples = [s for s in samples if s["db_id"] == db_id]
    return samples


def load_dev_sample(index: int = 0) -> dict:
    samples = load_dev_samples()
    if index < 0 or index >= len(samples):
        raise IndexError(f"dev 样本索引越界: {index}，共 {len(samples)} 条")
    return samples[index]


def build_task(question: str, db_id: str, evidence: str | None = None) -> str:
    parts = [
        f"You are working with SQLite database '{db_id}'.",
        "Use the provided tools to explore schema, run SQL, and answer the question.",
        (
            "Before calling final_answer, you MUST call record_final_sql with "
            "the final SELECT SQL that produces the answer."
        ),
        "When done, call final_answer with the query result.",
        f"\nQuestion: {question}",
    ]
    if evidence:
        parts.append(f"\nExternal Knowledge: {evidence}")
    return "\n".join(parts)


def run_question(
    agent: ToolCallingAgent,
    *,
    question: str,
    db_id: str,
    evidence: str | None = None,
    reset: bool = True,
) -> str:
    return agent.run(build_task(question, db_id, evidence), reset=reset)


def run_one_sample(
    sample: dict,
    *,
    max_steps: int,
    planning_interval: int | None,
) -> tuple[int, bool, str | None]:
    """运行单题，返回 (question_id, succeeded, error_msg)。"""
    question_id = sample["question_id"]
    db_id = sample["db_id"]
    question = sample["question"]
    evidence = sample.get("evidence") or None

    try:
        agent = build_agent(
            db_id,
            question_id,
            max_steps=max_steps,
            planning_interval=planning_interval,
        )
        result = run_question(
            agent,
            question=question,
            db_id=db_id,
            evidence=evidence,
        )
        print(f"[question_id={question_id}] 答案: {result}")
        return question_id, True, None
    except Exception as e:
        print(
            f"[question_id={question_id}] 失败: {e}",
            file=sys.stderr,
        )
        return question_id, False, str(e)


def run_all_samples(
    samples: list[dict],
    *,
    max_steps: int,
    planning_interval: int | None,
    workers: int = 1,
) -> tuple[int, int]:
    total = len(samples)
    succeeded = 0
    failed = 0

    if workers <= 1:
        for i, sample in enumerate(samples, start=1):
            question_id = sample["question_id"]
            db_id = sample["db_id"]
            print(
                f"\n[{i}/{total}] question_id={question_id} db_id={db_id}"
            )
            print(f"问题: {sample['question']}\n")
            _, ok, _ = run_one_sample(
                sample,
                max_steps=max_steps,
                planning_interval=planning_interval,
            )
            if ok:
                succeeded += 1
            else:
                failed += 1
        return succeeded, failed

    print(f"并行模式: workers={workers}\n")
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                run_one_sample,
                sample,
                max_steps=max_steps,
                planning_interval=planning_interval,
            ): sample
            for sample in samples
        }
        for future in tqdm(
            as_completed(futures),
            total=len(futures),
            desc="Processing",
        ):
            _, ok, _ = future.result()
            if ok:
                succeeded += 1
            else:
                failed += 1

    return succeeded, failed


def main():
    parser = argparse.ArgumentParser(description="smolagents Text2SQL Demo")
    parser.add_argument("--db_id", help="数据库 ID，如 debit_card_specializing")
    parser.add_argument(
        "--question",
        help='自然语言问题；传入 "all" 批量跑 dev.json 全部题目（可用 --db_id 过滤）',
    )
    parser.add_argument("--evidence", default="", help="外部知识提示")
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        help="使用 dev.json 中第 N 条样本（0-based）",
    )
    parser.add_argument("--max-steps", type=int, default=50, help="Agent 最大步数")
    parser.add_argument(
        "--planning-interval",
        type=int,
        default=None,
        help="规划间隔步数，1 表示每步 action 前都规划；不传则关闭 planning",
    )
    parser.add_argument(
        "--question-id",
        type=int,
        default=None,
        help="问题 ID，用于 record_final_sql 记录（手动模式）",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="批量并行线程数（仅 --question all），1 为串行；过高可能触发 API 限流",
    )
    parser.add_argument(
        "--no-export",
        action="store_true",
        help="运行结束后不导出 exp_result/agent_out 评估 JSON",
    )
    args = parser.parse_args()

    if args.sample is not None and args.question == "all":
        raise SystemExit("--sample 与 --question all 不能同时使用")

    orig_stdout, orig_stderr = setup_run_logging()
    try:
        _run_main(args)
    finally:
        teardown_run_logging(orig_stdout, orig_stderr)


def _run_main(args: argparse.Namespace) -> None:
    print(f"模型: {get_llm_config()['model']}")
    print(f"日志: {RUN_AGENT_LOG}")

    if args.question == "all":
        samples = load_dev_samples(args.db_id)
        if not samples:
            filter_hint = f" db_id={args.db_id}" if args.db_id else ""
            raise SystemExit(f"未找到匹配样本{filter_hint}")
        filter_hint = f" (db_id={args.db_id})" if args.db_id else ""
        print(f"批量模式: 共 {len(samples)} 题{filter_hint}\n")

        succeeded, failed = run_all_samples(
            samples,
            max_steps=args.max_steps,
            planning_interval=args.planning_interval,
            workers=args.workers,
        )

        print("\n" + "=" * 50)
        print(f"批量完成: 成功 {succeeded}，失败 {failed}，共 {len(samples)} 题")
        if not args.no_export:
            export_predictions_for_eval()
        return

    if args.sample is not None:
        sample = load_dev_sample(args.sample)
        db_id = sample["db_id"]
        question = sample["question"]
        evidence = sample.get("evidence", "")
        question_id = sample["question_id"]
        print(f"使用 dev 样本 #{args.sample} (question_id={question_id})")
    else:
        db_id = args.db_id or "debit_card_specializing"
        question = args.question or (
            "What is the ratio of customers who pay in EUR "
            "against customers who pay in CZK?"
        )
        evidence = args.evidence
        question_id = args.question_id
        if question_id is None:
            raise SystemExit("手动模式请通过 --question-id 指定 question_id")

    print(f"数据库: {db_id}")
    print(f"问题:   {question}\n")

    agent = build_agent(
        db_id,
        question_id,
        max_steps=args.max_steps,
        planning_interval=args.planning_interval,
    )
    result = run_question(
        agent,
        question=question,
        db_id=db_id,
        evidence=evidence or None,
    )

    print("\n" + "=" * 50)
    print("最终答案:")
    print(result)

    if not args.no_export:
        export_predictions_for_eval()


if __name__ == "__main__":
    main()
