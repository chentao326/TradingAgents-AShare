"""
A-stock-data tool wrappers for TradingAgents agents.
Provides LangChain @tool bindings for a-stock-data's extended data sources.
"""
from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_research_reports(
    symbol: Annotated[str, "股票代码，格式如 600519.SH"],
    max_pages: Annotated[int, "最大页数"] = 5,
) -> str:
    """获取个股研究报告列表（带评级和EPS预测），来自东方财富。"""
    return route_to_vendor("get_research_reports", symbol, max_pages)


@tool
def get_industry_reports(
    industry_code: Annotated[str, "东财行业码（* = 全行业）"] = "*",
    max_pages: Annotated[int, "最大页数"] = 5,
) -> str:
    """获取行业研究报告列表，来自东方财富。industry_code='*' 拉全行业。"""
    return route_to_vendor("get_industry_reports", industry_code, max_pages)


@tool
def get_consensus_eps(
    symbol: Annotated[str, "股票代码，格式如 600519.SH"],
) -> str:
    """获取机构一致预期EPS（同花顺），用于估值计算。"""
    return route_to_vendor("get_consensus_eps", symbol)


@tool
def search_reports_nl(
    query: Annotated[str, "自然语言搜索关键词，如 '人形机器人 丝杠 减速器'"],
    size: Annotated[int, "返回条数"] = 50,
) -> str:
    """通过iwencai语义搜索研报，支持自然语言跨主题检索。"""
    return route_to_vendor("search_reports_nl", query, size)


@tool
def get_margin_trading(
    symbol: Annotated[str, "股票代码，格式如 600519.SH"],
) -> str:
    """获取融资融券明细：融资余额/买入/偿还，融券余额/卖出/偿还。"""
    return route_to_vendor("get_margin_trading", symbol)


@tool
def get_block_trades(
    symbol: Annotated[str, "股票代码，格式如 600519.SH"],
) -> str:
    """获取大宗交易历史：成交价/量、溢价率、买卖方营业部。"""
    return route_to_vendor("get_block_trades", symbol)


@tool
def get_holder_count(
    symbol: Annotated[str, "股票代码，格式如 600519.SH"],
) -> str:
    """获取股东户数变化趋势（筹码集中度）：季度股东数 + 环比变化 + 户均持股。"""
    return route_to_vendor("get_holder_count", symbol)


@tool
def get_dividend_history(
    symbol: Annotated[str, "股票代码，格式如 600519.SH"],
) -> str:
    """获取分红送转历史：每股派息/送股/转增 + 进度状态。"""
    return route_to_vendor("get_dividend_history", symbol)


@tool
def get_lockup_expiry(
    symbol: Annotated[str, "股票代码，格式如 600519.SH"],
    forward_days: Annotated[int, "未来查询天数"] = 90,
) -> str:
    """获取限售解禁日历：历史解禁 + 未来指定天数的待解禁预警。"""
    return route_to_vendor("get_lockup_expiry", symbol, forward_days)


@tool
def get_concept_blocks(
    symbol: Annotated[str, "股票代码，格式如 600519.SH"],
) -> str:
    """获取个股所属全部板块（行业/概念/地域）+ BK码 + 涨跌幅 + 龙头股。"""
    return route_to_vendor("get_concept_blocks", symbol)


@tool
def get_filings(
    symbol: Annotated[str, "股票代码，格式如 600519.SH"],
) -> str:
    """获取公司公告（巨潮 cninfo），沪深北交所全量。"""
    return route_to_vendor("get_filings", symbol)


@tool
def get_valuation(
    symbol: Annotated[str, "股票代码，格式如 600519.SH"],
) -> str:
    """综合估值分析：前向PE、PEG、PE消化年数、一致预期EPS。"""
    return route_to_vendor("get_valuation", symbol)


@tool
def get_northbound_flow() -> str:
    """获取北向资金（沪深港通）实时分钟级流向数据。"""
    return route_to_vendor("get_northbound_flow")
