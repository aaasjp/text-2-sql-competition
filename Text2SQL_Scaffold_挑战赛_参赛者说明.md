## 比赛目标

本次比赛要求个人参赛者在 48 小时内实现一个 Text2SQL scaffold。参赛者不需要、也不允许进行模型训练或微调。比赛考察的是：如何围绕一个通用大模型设计更可靠的 SQL 生成流程。

你的系统需要根据题目中的自然语言问题和数据库信息，输出一条最终 SQL。评测只看 SQL 执行结果是否正确，不对过程、工具调用次数、trace 质量做额外打分。

---

### 文件目录结构

参赛者将获得以下文件夹：

```
Hackathon/
├── data/                              # 数据目录
│   ├── dev_databases/                 # 数据库目录（11个数据库）
│   ├── dev_tables.json                # Schema元数据
│   ├── dev.json                       # 开发集题目（100道，含答案）
│   ├── dev_gold.sql                   # 开发集标准答案
│   ├── dev.jsonl                      # 开发集难度信息
│   └── test.json                      # 测试集题目（400道，不含答案）
├── src/                               # 源代码目录
│   ├── deepseek_request.py            # API调用脚本
│   ├── prompt.py                      # Prompt生成脚本
│   └── table_schema.py                # Schema提取脚本
├── eval/                              # 评估目录
│   └── evaluation_ex.py               # 评估程序
├── run/                               # 运行脚本目录
│   ├── run_deepseek.sh                # SQL生成脚本
│   └── run_eval.sh                    # 评估脚本
└── exp_result/                        # 输出目录
    └── deepseek_output/               # SQL结果存放位置
```

---

### 数据集划分

| 数据集 | 题目数量 | 用途 | 是否提供答案 |
|--------|----------|------|--------------|
| **dev** | 100 道 | Scaffold设计与验证 | ✓ 提供 `dev_gold.sql` |
| **test** | 400 道 | 最终排名评测 | ❌ 不提供 |

#### dev.json 格式
```json
{
    "question_id": 1471,
    "db_id": "debit_card_specializing",
    "question": "What is the ratio of customers...",
    "evidence": "ratio = count(EUR) / count(CZK)",
    "difficulty": "simple"
}
```

#### dev_gold.sql 格式
```
SELECT ... FROM ...\tdb_id
```

---

### 数据集规模与难度分布

**总体规模**：
- 数据库数量：11 个
- SQL方言：SQLite

**难度分布**：

| 难度 | dev集 | test集 |
|------|-------|--------|
| Simple | 30 (30%) | 118 (29.5%) |
| Moderate | 50 (50%) | 200 (50%) |
| Challenging | 20 (20%) | 82 (20.5%) |

---

### 数据库说明

| 数据库 | 领域 |
|--------|------|
| `debit_card_specializing` | 银行卡消费 |
| `financial` | 金融账户与贷款 |
| `california_schools` | 加州学校教育 |
| `student_club` | 学生社团管理 |
| `thrombosis_prediction` | 血栓预测医疗 |
| `european_football_2` | 欧洲足球联赛 |
| `formula_1` | F1赛车比赛 |
| `superhero` | 超级英雄数据 |
| `codebase_community` | 代码社区论坛 |
| `card_games` | 卡牌游戏 |
| `toxicology` | 毒理学分子 |

---

### 评测方式

执行参赛者生成的SQL与标准答案SQL，对比查询结果是否一致。**只看执行结果，不评价SQL写法或生成过程**。

### 输出格式要求

参赛系统需输出JSON格式文件，每条SQL格式为：
```
SQL\t----- bird -----\t\db_id
```

---

### 快速使用指南

#### 0. 安装依赖

```bash
pip install openai tqdm func_timeout
```

#### 1. 配置API密钥

修改 `src/deepseek_request.py` 第19行：
```python
DEEPSEEK_API_KEY = '你的API密钥'
```

#### 2. 在dev集上运行测试

```bash
bash run/run_deepseek.sh dev
```

#### 3. 在dev集上评估结果

```bash
bash run/run_eval.sh
```

评估结果将输出到 `eval_result.txt`，包含各难度等级的准确率。

#### 4. 在test集上生成最终结果

```bash
bash run/run_deepseek.sh test
```

生成的SQL将保存到 `exp_result/deepseek_output/` 目录。

---

### 提交要求

最终提交时，请提交 `exp_result/deepseek_output/predict_mini_dev_test_*.json` 文件。

参赛者可基于此框架自由改进Prompt设计、Scaffold策略等。