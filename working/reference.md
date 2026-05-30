参考资料：
数据集
https://huggingface.co/datasets/birdsql/bird_mini_dev

查表：
# 列出所有数据库
python working/query_db.py dbs

# 列出某库的所有表
python working/query_db.py tables debit_card_specializing

# 查看表结构
python working/query_db.py schema debit_card_specializing customers

# 查询表数据（默认 10 行）
python working/query_db.py query debit_card_specializing customers -n 5

# 执行自定义 SQL
python working/query_db.py sql debit_card_specializing "SELECT Currency, COUNT(*) FROM customers GROUP BY Currency"



# 使用 dev.json 第 0 条样本
python working/smolagent_demo.py --sample 0

# 自定义问题
python working/smolagent_demo.py \
  --db_id debit_card_specializing \
  --question "How many customers pay in EUR?"

# 带 evidence 提示
python working/smolagent_demo.py \
  --db_id debit_card_specializing \
  --question "What is the ratio of EUR vs CZK customers?" \
  --evidence "ratio = count(EUR) / count(CZK)"


# smolagent Text2SQL（working/smolagent_text2sql.py）
# 执行日志: working/run_agent.log（含 agent 步骤与终端输出）
# 中间结果: working/predictions/prediction_sql.json
# 运行结束后自动导出评估 JSON: exp_result/agent_out/predict_mini_dev_dev_{MODEL}_cot_SQLite.json

# 串行（默认）
python smolagent_text2sql.py --question all --db_id debit_card_specializing

# 4 线程并行
python smolagent_text2sql.py --question all --db_id debit_card_specializing --workers 4

# 仅跑 agent、不写评估 JSON
python smolagent_text2sql.py --question all --no-export

# 评估 agent 预测（需与 .env 中 MODEL 一致，或设置 MODEL=...）
cd .. && bash run/run_eval_agent.sh