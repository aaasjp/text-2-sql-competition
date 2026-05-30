#!/bin/bash

# Evaluation script for smolagent Text2SQL predictions (exp_result/agent_out)

db_root_path='./data/dev_databases/'
num_cpus=4
meta_time_out=30.0

# Match MODEL in working/.env (default DeepSeek-V4-Flash)
model_name="${MODEL:-DeepSeek-V4-Flash}"
predicted_sql_path="./exp_result/agent_out/predict_mini_dev_dev_${model_name}_cot_SQLite.json"

ground_truth_path='./data/dev_gold.sql'
diff_json_path='./data/dev.jsonl'

if [ ! -f "${predicted_sql_path}" ]; then
  echo "预测文件不存在: ${predicted_sql_path}"
  echo "请先运行: cd working && python smolagent_text2sql.py --question all"
  exit 1
fi

echo "Evaluating agent predictions: ${predicted_sql_path}"

python3 -u ./eval/evaluation_ex.py \
    --db_root_path ${db_root_path} \
    --predicted_sql_path ${predicted_sql_path} \
    --ground_truth_path ${ground_truth_path} \
    --num_cpus ${num_cpus} \
    --output_log_path ./eval_result_agent.txt \
    --diff_json_path ${diff_json_path} \
    --meta_time_out ${meta_time_out} \
    --sql_dialect SQLite

echo "Evaluation completed! Results saved to ./eval_result_agent.txt"
