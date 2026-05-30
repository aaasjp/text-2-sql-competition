#!/bin/bash

# Evaluation script for dev set

db_root_path='./data/dev_databases/'
num_cpus=4
meta_time_out=30.0

# Predicted SQL path - modify this to your output file
predicted_sql_path='./exp_result/deepseek_output/predict_mini_dev_dev_DeepSeek-V4-Flash_cot_SQLite.json'

# Dev set paths
ground_truth_path='./data/dev_gold.sql'
diff_json_path='./data/dev.jsonl'

echo "Evaluating on dev set..."

python3 -u ./eval/evaluation_ex.py \
    --db_root_path ${db_root_path} \
    --predicted_sql_path ${predicted_sql_path} \
    --ground_truth_path ${ground_truth_path} \
    --num_cpus ${num_cpus} \
    --output_log_path ./eval_result.txt \
    --diff_json_path ${diff_json_path} \
    --meta_time_out ${meta_time_out} \
    --sql_dialect SQLite

echo "Evaluation completed! Results saved to ./eval_result.txt"