# 评估错误分析报告

基于 `working/evaluate_error_log.jsonl` 全部 **45 条**错误记录的总结。

## 总体结论

| 维度 | 情况 |
|------|------|
| 错误类型 | **100% 为 `result_mismatch`**（结果不一致） |
| 超时 / 语法报错 | **0 条** |
| 含义 | 预测 SQL 和标准 SQL **都能成功执行**，但返回的结果集与标准答案不同 |

也就是说，这 45 条错误都不是「SQL 写错跑不起来」，而是「SQL 能跑，但语义/写法与标准答案不一致导致 EX 判错」。

---

## 按根因分类

> 各类别存在重叠，同一错误可能同时属于多个类别。

### 1. 返回列不对（多列、少列、列顺序不同）— 约 15 条

模型常把问题理解成「顺便多返回一些信息」，但 EX 评估要求结果集**完全一致**（列数、列顺序、列值都要匹配）。

典型例子：

| question_id | 问题摘要 | 预测 vs 标准 |
|-------------|----------|--------------|
| 1356 | President 所在 department | 预测返回 `first_name, last_name, department`，标准只要 `department` |
| 1376 | 最高 spend-to-budget 比的事件 | 预测多返回 `spend_to_budget_ratio`，标准只要 `event_name` |
| 1389 | 最低 cost 的事件 | 预测返回 `event_name + lowest_cost`，标准只要 `event_name` |
| 1533 | 2012年8月 consumption 状态 | 预测返回 `CustomerID + Consumption`，标准只要 `Consumption` |
| 866 | 圈速 1:27 的车手 | 预测只返回 `url`，标准要 `forename, surname, url` |
| 865 | 完赛车手中年龄最大 | 预测多返回 `driverId, dob` |
| 892 / 994 | 积分/得分相关 | 列顺序或聚合列与标准不一致 |
| 96 | 1993 年最高贷款账户 | 预测返回 `account_id + amount`，标准只要 `account_id` |
| 1427 | MU 215 Guest Speaker 预算类别 | 预测只返回 `category`，标准返回 `category, type` |

---

### 2. 选错表 / 关联路径错误 — 约 8 条

| question_id | 问题摘要 | 错误说明 |
|-------------|----------|----------|
| 1350 | Post Cards 购买事件的状态 | 从 `event.status` 取，标准从 `budget.event_status` 取 |
| 892 | 积分最高的车手 | 用 `results` 累积分，标准用 `driverStandings` |
| 1014 | 意大利赛道 lap record | 用 `lapTimes` 算最快圈，标准用 `results.FastestLapTime` 复杂解析 |
| 1168 | 最老 SJS 患者检验日期 | `Diagnosis='SJS'` 写在 `Examination`，标准在 `Patient` |
| 694 | 某帖子最新 10 条评论 | 按发帖人 `users` 关联/排序，标准应按评论人和评论时间 |
| 201 | 双键分子中碳的比例 | `atom → connected → bond`，标准 `atom → bond`（经 `molecule_id`） |

---

### 3. 聚合 / 计数方式不同 — 约 10 条

| question_id | 问题摘要 | 错误说明 |
|-------------|----------|----------|
| 1505 | 欧元客户 consumption > 1000 人数 | `COUNT(DISTINCT CustomerID)` vs 标准 `COUNT(*)`（JOIN 后行数不同，391 vs 2730） |
| 1362 | Orange County, Virginia 城市数 | `COUNT(DISTINCT city)` vs `COUNT(city)` |
| 672 | 英国用户 favorite >= 4 | `COUNT(DISTINCT user)` vs `COUNT(user)`（一用户多帖时不同） |
| 1037 / 1068 / 1031 | 足球球员年龄/评分/百分比 | Player 与 Player_Attributes JOIN 产生多行，影响 AVG/百分比 |
| 1255 | 异常 IgM 最常见疾病 | `Diagnosis` 取自 `Laboratory` 而非 `Patient` |

---

### 4. 领域值 / 外部知识理解偏差 — 约 6 条

| question_id | 问题摘要 | 错误说明 |
|-------------|----------|----------|
| 1267 / 1275 | 正常 anti-SM / anti-centromere / anti-SSB | 预测用 `'-'`、`'+-'`，标准用 `'negative'`、`'0'` |
| 1362 | Orange County 城市数 | county 写 `'Orange'`，标准 `'Orange County'` |
| 587 | humor 标签帖子 | `Tags LIKE '%<humor>%'` vs 精确 `Tags = '<humor>'` |
| 1350 | 2019/8/20 购买记录 | 日期 `'2019-8-20'` vs `'2019-08-20'`（可能匹配不到行） |

---

### 5. 布尔 / 是与否的返回形式不同 — 约 2 条

| question_id | 问题摘要 | 错误说明 |
|-------------|----------|----------|
| 1399 | Maya 是否参加 Women's Soccer | 预测 `COUNT(*) > 0`（布尔），标准 `'YES'` / `NULL` 字符串 |
| 565 | 帖子是否 well-finished | 预测 `ClosedDate IS NULL`（0/1），标准 `'well-finished'` / `'NOT well-finished'` |

SQL 逻辑接近，但**结果字面形式不同**，EX 仍判错。

---

### 6. 时间 / 年龄计算方式不同 — 约 4 条

| question_id | 问题摘要 | 错误说明 |
|-------------|----------|----------|
| 1227 | 高胆固醇男性平均年龄 | 预测写死 `2025 - 出生年`，标准用 `date('NOW')` |
| 1031 | 2013–2015 sprint speed >= 97 球员年龄 | `julianday` 算年龄 vs 标准 `DATETIME() - birthday`；还多返回 `player_name` |
| 847 | race 19 Q2 最快圈车手 | 预测加了 `q2 IS NOT NULL`，可能改变人选 |
| 27 | 1991 年后开或 2000 年前关的学校写作分 | `OpenDate > '1991-12-31'` vs `strftime('%Y', OpenDate) > '1991'` |

---

### 7. 条件逻辑 / 运算符优先级 — 约 3 条

| question_id | 问题摘要 | 错误说明 |
|-------------|----------|----------|
| 1247 | 正常 WBC 男性中异常 fibrinogen 人数 | 预测 `(FG 异常) AND (WBC 正常)`，标准 SQL 中 `OR`/`AND` 优先级可能导致条件范围不同 |
| 23 | K-12 与 5–17 岁 enrollment 差 > 30 | 预测 `ABS(差值) > 30`，标准只要求 `K12 - Ages5_17 > 30`（单向） |
| 1243 | 55 岁以上女性异常 PT 百分比 | 百分比分子分母统计口径与 JOIN 方式略有差异 |

---

### 8. 窗口函数 / 排名缺失 — 约 1 条

| question_id | 问题摘要 | 错误说明 |
|-------------|----------|----------|
| 17 | Writing > 499 的学校排名 | 题目要求 Rank schools，预测只 `ORDER BY`，缺少 `RANK() OVER (...)` |

---

### 9. 完全理解错题意 — 约 1 条

| question_id | 问题摘要 | 错误说明 |
|-------------|----------|----------|
| 138 | 1995 年犯罪数第二高地区的男性客户数 | 预测 SQL 与标准 SQL 几乎无关，属于严重题意/模式理解错误 |

---

## 按数据库分布

| db_id | 错误数 | 主要问题 |
|-------|--------|----------|
| formula_1 | 8 | 多返回列、选错表、复杂子查询逻辑 |
| thrombosis_prediction | 8 | 枚举值、年龄计算、JOIN/计数 |
| student_club | 7 | 返回列过多、日期/字段选错 |
| california_schools | 5 | 缺少 RANK、条件/JOIN 差异 |
| european_football_2 | 4 | JOIN 重复行影响聚合 |
| codebase_community | 4 | 返回形式、JOIN 对象、Tags 匹配 |
| toxicology | 3 | 原子/分子统计层级、atom_id 解析 |
| debit_card_specializing | 2 | DISTINCT 计数、返回列 |
| card_games | 2 | 多返回列（ID 列表） |
| financial | 2 | 返回列、138 题意完全错误 |

---

## 改进方向

1. **严格对齐 SELECT 列**：只返回问题要求的列，不多不少、顺序一致。
2. **加强 schema / evidence 利用**：字段枚举（如 SM、SSB）、county 命名、日期格式等外部知识。
3. **注意 JOIN 重复行**：Player_Attributes、posts 等一对多表上的 COUNT/AVG 需防重复计数。
4. **统一输出格式**：是/否类问题按数据集习惯返回字符串，而非布尔值。
5. **复杂题型**：窗口函数、选表（results vs driverStandings vs lapTimes）需要更细的模式识别。

---

## 一句话总结

45 条错误全部是「SQL 能执行但结果不对」，核心是 **返回列不匹配、表/字段选错、聚合与 DISTINCT 用法、领域枚举值和少量完全理解错题意**，没有超时或语法层面的失败。
