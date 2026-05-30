#!/usr/bin/env python3
"""
DeepSeek API request script for text-to-SQL task
Based on gpt_request.py but adapted for DeepSeek API with thinking mode enabled
"""
import argparse
import json
import os
import threading
from pathlib import Path
from openai import OpenAI
from tqdm import tqdm
import time
from concurrent.futures import ThreadPoolExecutor
import concurrent.futures
from dotenv import load_dotenv

from prompt import generate_combined_prompts_one


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / "working" / ".env")
load_dotenv(PROJECT_ROOT / ".env")

DEEPSEEK_API_KEY = os.environ.get("API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = (
    os.environ.get("BASE_URL")
    or os.environ.get("DEEPSEEK_BASE_URL")
    or "https://api.deepseek.com"
)
DEFAULT_MODEL = os.environ.get("MODEL") or "DeepSeek-V4-Flash"
USE_OFFICIAL_DEEPSEEK_API = "api.deepseek.com" in DEEPSEEK_BASE_URL
SYSTEM_PROMPT = "You are a helpful assistant that generates SQL queries."
PREDICT_LOG_PATH = PROJECT_ROOT / "working" / "predict_log.jsonl"
_log_lock = threading.Lock()


def init_predict_log():
    PREDICT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    PREDICT_LOG_PATH.write_text("")


def log_predict_record(record: dict):
    with _log_lock:
        with open(PREDICT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def new_directory(path):
    if not os.path.exists(path):
        os.makedirs(path)


def connect_deepseek(engine, prompt, max_tokens, temperature, stop, client):
    """
    Function to connect to DeepSeek API and get the response.
    Enables thinking mode only for the official DeepSeek API.
    """
    MAX_API_RETRY = 1
    for i in range(MAX_API_RETRY):
        time.sleep(1)
        try:
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
            request_kwargs = {
                "model": engine,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stop": stop,
                "stream": False,
            }
            if USE_OFFICIAL_DEEPSEEK_API:
                request_kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
            result = client.chat.completions.create(**request_kwargs)
            break
        except Exception as e:
            result = "error:{}".format(e)
            print(f"Error on attempt {i+1}: {e}")
            time.sleep(3)
    return result


def decouple_question_schema(datasets, db_root_path):
    question_list = []
    db_path_list = []
    knowledge_list = []
    question_id_list = []
    db_id_list = []
    for i, data in enumerate(datasets):
        question_list.append(data["question"])
        cur_db_path = db_root_path + data["db_id"] + "/" + data["db_id"] + ".sqlite"
        db_path_list.append(cur_db_path)
        knowledge_list.append(data.get("evidence", ""))
        question_id_list.append(data["question_id"])
        db_id_list.append(data["db_id"])

    return question_list, db_path_list, knowledge_list, question_id_list, db_id_list


def generate_sql_file(sql_lst, output_path=None, reasoning_output_path=None):
    """
    Function to save the SQL results and reasoning to files.
    """
    sql_lst.sort(key=lambda x: x[2])
    result = {}
    reasoning_result = {}

    for i, (sql, reasoning, idx) in enumerate(sql_lst):
        result[i] = sql
        reasoning_result[i] = reasoning

    if output_path:
        directory_path = os.path.dirname(output_path)
        new_directory(directory_path)
        json.dump(result, open(output_path, "w"), indent=4)

    if reasoning_output_path:
        directory_path = os.path.dirname(reasoning_output_path)
        new_directory(directory_path)
        json.dump(reasoning_result, open(reasoning_output_path, "w"), indent=4)

    return result


def init_client():
    """
    Initialize the OpenAI client for DeepSeek API.
    """
    if not DEEPSEEK_API_KEY:
        raise SystemExit(
            "未找到 API Key，请在 working/.env 中配置 API_KEY 或 DEEPSEEK_API_KEY"
        )
    return OpenAI(
        api_key=DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_BASE_URL,
    )


def post_process_response(response, db_path):
    """
    Process DeepSeek response, extracting both reasoning and final SQL.
    """
    db_id = db_path.split("/")[-1].split(".sqlite")[0]

    if isinstance(response, str):
        sql = response
        reasoning = ""
    else:
        # Extract reasoning content if available
        reasoning = getattr(response.choices[0].message, 'reasoning_content', '') or ""
        sql = response.choices[0].message.content or ""

    # Clean up the SQL response
    sql = sql.strip()
    reasoning = reasoning.strip()

    # Remove markdown code blocks if present
    if "```" in sql:
        # Extract SQL from code block
        parts = sql.split("```")
        for part in parts:
            part = part.strip()
            if part and not part.startswith("sql") and not part.endswith("```"):
                # This might be the SQL content
                if any(kw in part.upper() for kw in ["SELECT", "FROM", "WHERE", "INSERT", "UPDATE", "DELETE", "CREATE"]):
                    sql = part
                    break
            elif part.startswith("sql"):
                sql = part[3:].strip()

    # Final cleanup - remove any remaining markdown markers
    sql = sql.replace("```sql", "").replace("```", "").strip()

    # Format output
    output = f"{sql}\t----- bird -----\t{db_id}"

    return output, reasoning


def worker_function(question_data):
    """
    Function to process each question.
    """
    prompt, engine, client, db_path, question, i, question_id, db_id = question_data
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    response = connect_deepseek(engine, prompt, 8192, 0, ["--", "\n\n\n"], client)
    sql, reasoning = post_process_response(response, db_path)
    log_predict_record(
        {
            "question_id": question_id,
            "db_id": db_id,
            "index": i,
            "messages": messages,
            "sql": sql,
            "reasoning": reasoning,
        }
    )
    print(f"Processed {i}th question (question_id={question_id}, db_id={db_id}): {question[:50]}...")
    if reasoning:
        print(f"  Reasoning length: {len(reasoning)} chars")
    return sql, reasoning, i


def collect_response_from_deepseek(
    db_path_list,
    question_list,
    engine,
    sql_dialect,
    num_threads=10,
    knowledge_list=None,
    question_id_list=None,
    db_id_list=None,
    num_rows=None,
):
    """
    Collect responses from DeepSeek using multiple threads.
    """
    client = init_client()

    tasks = [
        (
            generate_combined_prompts_one(
                db_path=db_path_list[i],
                question=question_list[i],
                sql_dialect=sql_dialect,
                knowledge=knowledge_list[i] if knowledge_list else None,
                num_rows=num_rows,
            ),
            engine,
            client,
            db_path_list[i],
            question_list[i],
            i,
            question_id_list[i],
            db_id_list[i],
        )
        for i in range(len(question_list))
    ]
    responses = []
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        future_to_task = {
            executor.submit(worker_function, task): task for task in tasks
        }
        for future in tqdm(
            concurrent.futures.as_completed(future_to_task), total=len(tasks)
        ):
            responses.append(future.result())
    return responses


if __name__ == "__main__":
    args_parser = argparse.ArgumentParser()
    args_parser.add_argument("--eval_path", type=str, default="")
    args_parser.add_argument("--mode", type=str, default="dev")
    args_parser.add_argument("--test_path", type=str, default="")
    args_parser.add_argument("--use_knowledge", type=str, default="True")
    args_parser.add_argument("--db_root_path", type=str, default="")
    args_parser.add_argument("--engine", type=str, default="")
    args_parser.add_argument("--data_output_path", type=str)
    args_parser.add_argument("--chain_of_thought", type=str, default="True")
    args_parser.add_argument("--num_processes", type=int, default=3)
    args_parser.add_argument("--num_rows", type=int, default=None)
    args_parser.add_argument("--sql_dialect", type=str, default="SQLite")
    args = args_parser.parse_args()

    engine = args.engine or DEFAULT_MODEL
    eval_data = json.load(open(args.eval_path, "r"))

    question_list, db_path_list, knowledge_list, question_id_list, db_id_list = (
        decouple_question_schema(datasets=eval_data, db_root_path=args.db_root_path)
    )
    assert (
        len(question_list)
        == len(db_path_list)
        == len(knowledge_list)
        == len(question_id_list)
        == len(db_id_list)
    )

    init_predict_log()

    if args.use_knowledge == "True":
        responses = collect_response_from_deepseek(
            db_path_list,
            question_list,
            engine,
            args.sql_dialect,
            args.num_processes,
            knowledge_list,
            question_id_list,
            db_id_list,
            num_rows=args.num_rows,
        )
    else:
        responses = collect_response_from_deepseek(
            db_path_list,
            question_list,
            engine,
            args.sql_dialect,
            args.num_processes,
            question_id_list=question_id_list,
            db_id_list=db_id_list,
            num_rows=args.num_rows,
        )

    if args.chain_of_thought == "True":
        output_name = (
            args.data_output_path
            + "predict_"
            + args.mode
            + "_"
            + engine
            + "_cot"
            + "_"
            + args.sql_dialect
            + ".json"
        )
        reasoning_output_name = (
            args.data_output_path
            + "reasoning_"
            + args.mode
            + "_"
            + engine
            + "_cot"
            + "_"
            + args.sql_dialect
            + ".json"
        )
    else:
        output_name = (
            args.data_output_path
            + "predict_"
            + args.mode
            + "_"
            + engine
            + "_"
            + args.sql_dialect
            + ".json"
        )
        reasoning_output_name = None

    generate_sql_file(sql_lst=responses, output_path=output_name, reasoning_output_path=reasoning_output_name)

    print(
        "Successfully collected results from {} for {} evaluation; SQL dialect {} Use knowledge: {}; Use COT: {}".format(
            engine,
            args.mode,
            args.sql_dialect,
            args.use_knowledge,
            args.chain_of_thought,
        )
    )