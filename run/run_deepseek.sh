#!/bin/bash

# DeepSeek Text-to-SQL Script
# Usage: bash run/run_deepseek.sh [dev|test]

# 选择数据集：dev (100题) 或 test (400题)
DATASET=${1:-dev}

if [ "$DATASET" = "dev" ]; then
    eval_path='./data/dev.json'
elif [ "$DATASET" = "test" ]; then
    eval_path='./data/test.json'
else
    echo "Usage: bash run/run_deepseek.sh [dev|test]"
    exit 1
fi

db_root_path='./data/dev_databases/'

# 运行参数
use_knowledge='True'
mode='mini_dev'
cot='True'
num_threads=10
sql_dialect='SQLite'
data_output_path='./exp_result/deepseek_output/'

echo "Running DeepSeek on $DATASET set (model from .env MODEL or --engine)..."
echo "Threads: $num_threads, Knowledge: $use_knowledge, COT: $cot"

python3 -u ./src/deepseek_request.py \
    --db_root_path ${db_root_path} \
    --mode ${mode}_${DATASET} \
    --eval_path ${eval_path} \
    --data_output_path ${data_output_path} \
    --use_knowledge ${use_knowledge} \
    --chain_of_thought ${cot} \
    --num_processes ${num_threads} \
    --sql_dialect ${sql_dialect}

echo "Done! Results saved to ${data_output_path}"