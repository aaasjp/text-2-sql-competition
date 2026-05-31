#!/usr/bin/env python3
"""测试单个 sample：输入 sample index，输出完整 LLM 响应。"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
WORKING_DIR = Path(__file__).resolve().parent
DB_ROOT = PROJECT_ROOT / "data" / "dev_databases"

sys.path.insert(0, str(SRC_DIR))

from dotenv import load_dotenv

load_dotenv(WORKING_DIR / ".env")
load_dotenv(PROJECT_ROOT / ".env")

from deepseek_request import (  # noqa: E402
    DEFAULT_MODEL,
    SYSTEM_PROMPT,
    connect_deepseek,
    init_client,
    post_process_response,
)
from prompt import generate_combined_prompts_one  # noqa: E402


def load_sample(index: int, eval_path: Path) -> tuple[int, dict]:
    with open(eval_path, encoding="utf-8") as f:
        data = json.load(f)
    if index < 0 or index >= len(data):
        raise SystemExit(
            f"index={index} 超出范围，数据集 {eval_path} 共 {len(data)} 条 (0~{len(data) - 1})"
        )
    return index, data[index]


def extract_full_response(response) -> dict:
    if isinstance(response, str):
        return {
            "error": response,
            "reasoning": "",
            "content": "",
            "model": None,
            "usage": None,
        }

    msg = response.choices[0].message
    usage = response.usage
    reasoning = (
        getattr(msg, "reasoning_content", None)
        or getattr(msg, "reasoning", None)
        or ""
    )
    return {
        "error": None,
        "model": response.model,
        "reasoning": reasoning,
        "content": msg.content or "",
        "usage": {
            "prompt_tokens": usage.prompt_tokens if usage else None,
            "completion_tokens": usage.completion_tokens if usage else None,
            "total_tokens": usage.total_tokens if usage else None,
        },
    }


def print_text_output(
    index: int, sample: dict, full: dict, sql: str, *, show_prompt: bool, prompt: str
):
    print("=" * 60)
    print("Sample Info")
    print("=" * 60)
    print(f"index       : {index}")
    print(f"question_id : {sample['question_id']}")
    print(f"db_id       : {sample['db_id']}")
    print(f"difficulty  : {sample.get('difficulty', 'N/A')}")
    print(f"question    : {sample['question']}")
    if sample.get("evidence"):
        print(f"evidence    : {sample['evidence']}")

    if show_prompt:
        print("\n" + "=" * 60)
        print("Prompt")
        print("=" * 60)
        print(f"[system]\n{SYSTEM_PROMPT}\n")
        print(f"[user]\n{prompt}")

    print("\n" + "=" * 60)
    print("LLM Response")
    print("=" * 60)
    if full["error"]:
        print(f"ERROR: {full['error']}")
        return

    print(f"model: {full['model']}")
    if full["usage"]:
        u = full["usage"]
        print(
            f"usage: prompt={u['prompt_tokens']}, "
            f"completion={u['completion_tokens']}, total={u['total_tokens']}"
        )

    if full["reasoning"]:
        print("\n--- reasoning ---")
        print(full["reasoning"])

    print("\n--- content ---")
    print(full["content"])

    print("\n" + "=" * 60)
    print("Processed SQL")
    print("=" * 60)
    print(sql)


def main():
    parser = argparse.ArgumentParser(
        description="测试单个 sample 的 DeepSeek LLM 完整输出"
    )
    parser.add_argument("index", type=int, help="样本在数据集中的 index（从 0 开始）")
    parser.add_argument(
        "--dataset",
        choices=["dev", "test"],
        default="dev",
        help="数据集 (default: dev)",
    )
    parser.add_argument(
        "--engine",
        default=None,
        help="模型名，默认从 .env 的 MODEL 读取",
    )
    parser.add_argument("--num_rows", type=int, default=None, help="schema 示例行数")
    parser.add_argument("--sql_dialect", default="SQLite")
    parser.add_argument(
        "--no-knowledge",
        action="store_true",
        help="不使用 evidence 外部知识",
    )
    parser.add_argument(
        "--show-reasoning",
        action="store_true",
        help="调试模式：要求模型在 content 中输出逐步推理过程",
    )
    parser.add_argument(
        "--show-prompt",
        action="store_true",
        help="同时打印发送给 LLM 的完整 prompt",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 格式输出全部结果",
    )
    args = parser.parse_args()

    eval_path = PROJECT_ROOT / "data" / f"{args.dataset}.json"
    index, sample = load_sample(args.index, eval_path)

    db_path = DB_ROOT / sample["db_id"] / f"{sample['db_id']}.sqlite"
    if not db_path.exists():
        raise SystemExit(f"数据库不存在: {db_path}")

    knowledge = None
    if not args.no_knowledge:
        evidence = sample.get("evidence", "")
        knowledge = evidence if evidence else None

    prompt = generate_combined_prompts_one(
        db_path=str(db_path),
        question=sample["question"],
        sql_dialect=args.sql_dialect,
        knowledge=knowledge,
        num_rows=args.num_rows,
        show_reasoning=args.show_reasoning,
    )

    engine = args.engine or DEFAULT_MODEL
    client = init_client()
    response = connect_deepseek(engine, prompt, 8192, 0, ["--", "\n\n\n"], client)

    full = extract_full_response(response)
    sql, _ = post_process_response(response, str(db_path))

    if args.json:
        output = {
            "index": index,
            "sample": sample,
            "engine": engine,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "llm_response": full,
            "processed_sql": sql,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print_text_output(
            index, sample, full, sql, show_prompt=args.show_prompt, prompt=prompt
        )


if __name__ == "__main__":
    main()
