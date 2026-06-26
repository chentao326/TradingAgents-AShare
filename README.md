# TradingAgents-AShare + a-stock-data 数据增强版

本分支在 [KylinMountain/TradingAgents-AShare](https://github.com/KylinMountain/TradingAgents-AShare)（14 Agent 多智能体 A 股投研系统）的基础上，整合了 [simonlin1212/a-stock-data](https://github.com/simonlin1212/a-stock-data)（7 层架构 · 28 端点 · 13 数据源），为 Agent 团队补上了研报检索、融资融券、大宗交易、限售解禁、巨潮公告等原本缺失的数据能力。

> **原仓库**：https://github.com/KylinMountain/TradingAgents-AShare
> **本分支**：https://github.com/chentao326/TradingAgents-AShare/tree/feat/a-stock-data-integration
> **数据源**：[simonlin1212/a-stock-data](https://github.com/simonlin1212/a-stock-data)（⭐5.5k，Apache 2.0）

---

## 与原仓库的对比

| 维度 | 原仓库 | 本分支（数据增强版） |
|------|--------|---------------------|
| 数据源 | akshare + baostock | akshare + baostock + **a-stock-data（13 源）** |
| 端点数 | akshare 封装层 | 新增 **28 个直连端点**（无中间依赖） |
| 研报检索 | 无 | ✅ 个股研报 + 行业研报 + NL 语义搜索 + PDF 下载 |
| 一致预期 EPS | 无 | ✅ 同花顺机构一致预期 |
| 融资融券 | 无 | ✅ 日级融资/融券明细 |
| 大宗交易 | 无 | ✅ 成交价/量 + 溢价率 + 买卖方营业部 |
| 股东户数 | 无 | ✅ 季度变化 + 筹码集中度 |
| 分红历史 | 无 | ✅ 每股派息/送股/转增 + 进度 |
| 限售解禁 | 无 | ✅ 历史解禁 + 未来 90 天预警 |
| 概念板块 | 单源 | ✅ 行业/概念/地域全板块（一次请求拿全） |
| 公告检索 | 无 | ✅ 巨潮 cninfo 沪深北全量公告（6198 只股映射） |
| 行情源 | akshare（东财 HTTP） | **mootdx TCP（不封 IP）+ 腾讯（不封 IP）+ 百度K线** |
| 估值引擎 | 无 | ✅ 前向 PE / PEG / PE 消化年数自动计算 |
| 北向资金 | 无 | ✅ 实时分钟级沪深港通流向 |
| Agent 工具 | 13 个 | **26 个**（+13 个新工具） |
| 数据降级 | 无降级链 | akshare → baostock → **a-stock-data** → yfinance |
| 反爬措施 | 基础 | 东财统一限流 `em_get()`（间隔 ≥1s + 抖动） |

---

## 新增数据能力详解

### 研报层（原仓库完全没有）

所有 6 位分析师 + 研究员可以直接调取研报：

| 端点 | 能力 | 来源 |
|------|------|------|
| `get_research_reports` | 个股研报列表 + 评级 + 三年 EPS 预测 | 东财 reportapi |
| `get_industry_reports` | 行业研报（全行业或按行业码过滤） | 东财 reportapi |
| `get_consensus_eps` | 机构一致预期 EPS | 同花顺 |
| `search_reports_nl` | 自然语言跨主题研报检索（如“人形机器人 丝杠”） | iwencai |

### 资金面 / 筹码层（原仓库完全没有）

聪明钱分析师新增的工具：

| 端点 | 能力 | 来源 |
|------|------|------|
| `get_margin_trading` | 融资融券明细（融资余额/买入/偿还，融券余额/卖出/偿还） | 东财 datacenter |
| `get_block_trades` | 大宗交易（成交价/量，溢价率，买卖方营业部） | 东财 datacenter |
| `get_holder_count` | 股东户数变化（筹码集中度，户均持股） | 东财 datacenter |
| `get_dividend_history` | 分红送转历史（每股派息/送股/转增） | 东财 datacenter |

### 其他关键补充

| 端点 | 能力 | 来源 |
|------|------|------|
| `get_lockup_expiry` | 限售解禁日历（历史 + 未来预警） | 东财 push2 |
| `get_concept_blocks` | 个股全板块归属（行业/概念/地域 + BK码 + 龙头股） | 东财 slist |
| `get_filings` | 巨潮公告（沪深北全量，动态 orgId 映射） | 巨潮 cninfo |
| `get_valuation` | 前向 PE / PEG / PE 消化年数 | 自研公式 |
| `get_northbound_flow` | 北向资金实时分钟级流向 | 同花顺 |

### 行情层升级

| 端点 | 原仓库 | 本分支 |
|------|--------|--------|
| K线数据 | 东财 HTTP（有封 IP 风险） | mootdx TCP（不封 IP） + 腾讯（不封 IP） |
| 实时报价 | 东财/新浪 | 腾讯（PE/PB/市值/换手率/涨跌停）/ 百度K线（自带 MA5/10/20） |
| 行业板块 | 同花顺 401 → 东财 | 东财 push2（零鉴权，字段更丰富） |
| 资金流向 | 东财/百度（偶发失效） | 东财 push2（分钟级 + 120日历史） |

---

## 数据流架构

原 akshare 通路完全保留。新增的 cn\_a\_stock\_data 作为第三降级层，只在前面都失败时才触发：

```
TradingAgents Agent 请求数据
        │
        ▼
  cn_akshare (主力，akshare 封装层)
        │ 失败
        ▼
  cn_baostock (备用，baostock 封装层)
        │ 失败
        ▼
  cn_a_stock_data (★ 本分支新增，28 个直连端点)
        │ 失败
        ▼
  yfinance / alpha_vantage (海外数据兜底)
```

所有东财接口统一走 `em_get()` 限流入口（间隔 ≥1s + 随机抖动 + 会话复用），批量调用自带防封。

---

## Agent 工具分配变化

| Agent | 原仓库工具 | 新增工具（本分支） |
|-------|-----------|-------------------|
| 基本面分析师 | 财报三表 + 公司信息 | **研报检索、一致预期、估值计算、公告查询** |
| 聪明钱分析师 | 资金流向 + 龙虎榜 + 技术指标 | **融资融券、大宗交易、股东户数变化** |
| 宏观分析师 | 板块资金流 + 新闻 | **北向资金、行业研报** |

---

## 跟原仓库的用法差异

**零差异。** Agent 团队自动工作。你不需要改任何操作习惯。

原来你在前端输入“分析一下 600519 短线”，14 个 Agent 照常跑——唯一区别是现在的分析师手里多了研报、融资融券、估值数据。如果 akshare 某次拿不到数据，系统自动降级用 a-stock-data 的端点。

想确认新数据在生效？去 Docker 日志看 provider-trace：

```
[provider-trace] method=get_margin_trading symbol='600519.SH' vendor=cn_a_stock_data status=hit
```

---

## 快速上手

### 方式一：从本分支构建镜像（含全部数据增强）

```bash
git clone https://github.com/chentao326/TradingAgents-AShare.git
cd TradingAgents-AShare
git checkout feat/a-stock-data-integration

docker build -t tradingagents-ashare:a-stock-data .
docker run -d -p 8000:8000 --name tradingagents \
  -v $(pwd)/data:/app/data \
  -e DATABASE_URL="sqlite:///./data/tradingagents.db" \
  -e TA_APP_SECRET_KEY="*** rand -base64 32)" \
  tradingagents-ashare:a-stock-data
```

### 方式二：源码启动

```bash
git clone https://github.com/chentao326/TradingAgents-AShare.git
cd TradingAgents-AShare
git checkout feat/a-stock-data-integration

# 后端
uv sync
uv run python -m uvicorn api.main:app --port 8000

# 前端（可选，首次需要）
cd frontend && npm install && npm run build && cd ..
```

访问 `http://localhost:8000`。

---

## 依赖变化

```diff
requirements.txt / pyproject.toml 新增:
+ mootdx >= 0.10  # 通达信 TCP 行情（不封 IP）
```

---

## 文件结构变化

```
tradingagents/dataflows/providers/
  cn_akshare_provider.py         # 原文件，未改动
  cn_baostock_provider.py        # 原文件，未改动
  a_stock_data_core.py           # ★ 新增：提取自 a-stock-data SKILL.md，43 个数据函数
  cn_a_stock_data_provider.py    # ★ 新增：Provider 类，实现标准接口 + 14 个扩展方法
  registry.py                    # 修改：注册 cn_a_stock_data

tradingagents/dataflows/
  interface.py                   # 修改：新增 7 个数据分类

tradingagents/agents/utils/
  a_stock_data_tools.py          # ★ 新增：13 个 LangChain 工具绑定
  agent_utils.py                 # 修改：导入新工具

tradingagents/graph/
  trading_graph.py               # 修改：Agent 工具分配 + 导入新工具
```

---

## 许可

本项目基于 [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) (Apache 2.0) 二次开发。新增模块 (`api/`, `frontend/`) 及核心逻辑修改采用 `PolyForm Noncommercial 1.0.0`。本分支增加的文件采用 Apache 2.0（与 a-stock-data 上游保持一致）。

---

## 特别鸣谢

- [KylinMountain/TradingAgents-AShare](https://github.com/KylinMountain/TradingAgents-AShare) — 14 Agent 多智能体投研系统
- [simonlin1212/a-stock-data](https://github.com/simonlin1212/a-stock-data) — A 股全栈数据工具包（⭐5.5k）
- [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) — 多智能体交易框架原型

---

## 声明

本项目仅供学习研究，不构成投资建议。证券市场有风险，投资需谨慎。
