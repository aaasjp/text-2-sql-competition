# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Text2SQL competition project (Text2SQL Scaffold 挑战赛). The goal is to build a reliable SQL generation system around a general LLM, without model training or fine-tuning.

**Target**: Given natural language questions and database schema information, generate correct SQLite SQL queries.

## Architecture

### Two SQL Generation Approaches

1. **Direct API Approach** (`src/deepseek_request.py`): Single-shot prompt to LLM with schema and question
2. **Agent Approach** (`working/smolagent_text2sql.py`): Multi-step ToolCallingAgent with database exploration tools

### Key Directories

```
├── data/
│   ├── dev_databases/       # 11 SQLite databases
│   ├── dev.json             # Dev set (100 questions)
│   └── test.json            # Test set (400 questions)
├── src/                     # Direct API approach
│   ├── deepseek_request.py  # Main API request script
│   ├── prompt.py            # Prompt generation
│   └── table_schema.py      # Schema extraction
├── working/                 # Agent approach & utilities
│   ├── smolagent_text2sql.py # ToolCallingAgent implementation
│   └── smolagents/          # Local smolagents installation
├── eval/                    # Evaluation
│   ├── evaluation_ex.py     # Main evaluation script
│   └── evaluation_utils.py  # Utilities
└── run/                     # Execution scripts
    ├── run_deepseek.sh      # Run direct API approach
    └── run_eval.sh           # Run evaluation
```

## Running the Project

### Setup
```bash
pip install openai tqdm func_timeout python-dotenv
cd working && pip install -r requirements.txt
```

Configure API key in `working/.env`:
```
API_KEY=your_api_key
MODEL=DeepSeek-V4-Flash
BASE_URL=https://api.deepseek.com
```

### Direct API Approach

```bash
# Generate SQL on dev set
bash run/run_deepseek.sh dev

# Generate SQL on test set
bash run/run_deepseek.sh test

# Evaluate results
bash run/run_eval.sh
```

### Agent Approach

```bash
# Single question
python working/smolagent_text2sql.py --db_id <db_id> --question "..." --question-id <id>

# Run all dev questions
python working/smolagent_text2sql.py --question all --workers 4

# Run specific database
python working/smolagent_text2sql.py --db_id debit_card_specializing --question all
```

### Evaluation

```bash
python eval/evaluation_ex.py \
    --predicted_sql_path exp_result/deepseek_output/predict_*.json \
    --ground_truth_path data/dev_gold.sql \
    --db_root_path data/dev_databases/ \
    --diff_json_path data/dev.jsonl \
    --dev_json_path data/dev.json
```

## Databases (11 total)

| Database | Domain |
|----------|--------|
| debit_card_specializing | Bank card transactions |
| financial | Financial accounts & loans |
| california_schools | California school data |
| student_club | Student club management |
| thrombosis_prediction | Medical thrombosis data |
| european_football_2 | European football |
| formula_1 | F1 racing |
| superhero | Superhero data |
| codebase_community | Code community forum |
| card_games | Card game data |
| toxicology | Toxicology molecules |

## Evaluation

- **Metric**: Execution Accuracy (EX) - SQL results must match ground truth
- **Difficulty levels**: Simple (30%), Moderate (50%), Challenging (20%)
- **Output format**: `SQL\t----- bird -----\tdb_id`
- **Error log**: `working/evaluate_error_log.jsonl`

## Common Issues

1. **Empty predictions**: Complex questions may result in empty SQL outputs
2. **Date format mismatches**: Ground truth uses specific formats (e.g., `2019-08-20` vs `2019-8-20`)
3. **Enum value mapping**: Some fields have specific value representations (e.g., `negative/0` vs `-`)