"""
CnAStockDataProvider — A-share data provider backed by a-stock-data (28 endpoints, 13 sources).

Integrates simonlin1212/a-stock-data's comprehensive A-share data toolkit with
TradingAgents-AShare's multi-agent analysis system. Provides fallback coverage
for data that akshare doesn't cover well: research reports, capital flow/ownership,
lockup expiry, filings, and richer fundamentals.

Usage: configured via data_vendors in .env / config.yaml.
  DataVendor: cn_market_data = cn_akshare, cn_a_stock_data
"""

import logging
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from .base import BaseMarketDataProvider
from .a_stock_data_core import (
    tdx_client, tencent_quote, baidu_kline_with_ma,
    eastmoney_reports, eastmoney_industry_reports, download_pdf,
    ths_eps_forecast, iwencai_search, iwencai_query,
    ths_hot_reason, hsgt_realtime, eastmoney_concept_blocks,
    eastmoney_fund_flow_minute, dragon_tiger_board, lockup_expiry,
    industry_comparison, daily_dragon_tiger,
    margin_trading, block_trade, holder_num_change, dividend_history,
    stock_fund_flow_120d,
    eastmoney_stock_news, eastmoney_global_news,
    eastmoney_stock_info, sina_financial_report,
    cninfo_announcements,
    forward_pe, pe_digestion, calc_peg, full_valuation,
)

_logger = logging.getLogger(__name__)


class CnAStockDataProvider(BaseMarketDataProvider):
    """A-share provider backed by a-stock-data (direct HTTP/ TCP API)."""

    @property
    def name(self) -> str:
        return "cn_a_stock_data"

    # ── helpers ──

    def _normalize_symbol(self, symbol: str) -> str:
        """Extract 6-digit A-share code from e.g. 600519.SH or 000858.SZ."""
        import re
        s = symbol.strip().lower()
        m = re.search(r"(\d{6})", s)
        if not m:
            raise ValueError(f"cn_a_stock_data requires a 6-digit A-share code, got: {symbol}")
        return m.group(1)

    def _to_json_str(self, obj: Any) -> str:
        """Convert any object to a readable JSON string."""
        import json
        try:
            return json.dumps(obj, ensure_ascii=False, indent=2, default=str)
        except Exception:
            return str(obj)

    # ── core interface: BaseMarketDataProvider ──

    def get_stock_data(self, symbol: str, start_date: str, end_date: str) -> str:
        """OHLCV + MA5/10/20 via baidu_kline_with_ma, fallback tdx_client."""
        code = self._normalize_symbol(symbol)
        parts = [f"## Stock Data: {symbol} ({start_date} ~ {end_date})"]

        # Try baidu_kline_with_ma first (richer: includes MAs)
        try:
            kline = baidu_kline_with_ma(code, start_time=start_date)
            if kline:
                from .a_stock_data_core import get_prefix
                prefix = get_prefix(code)
                parts.append(f"### K-line (Baidu, with MA5/MA10/MA20)")
                recent = list(kline.keys())[-60:]
                for date_str in recent:
                    bar = kline[date_str]
                    parts.append(
                        f"  {date_str} | O:{bar.get('open','N/A'):>8}  "
                        f"H:{bar.get('high','N/A'):>8}  L:{bar.get('low','N/A'):>8}  "
                        f"C:{bar.get('close','N/A'):>8}  V:{bar.get('vol','N/A'):>10}  "
                        f"MA5:{bar.get('ma5','N/A'):>8}  MA10:{bar.get('ma10','N/A'):>8}  "
                        f"MA20:{bar.get('ma20','N/A'):>8}"
                    )
                return "\n".join(parts)
        except Exception as exc:
            _logger.warning("baidu_kline_with_ma failed, fallback tdx_client: %s", exc)

        # Fallback: tdx_client
        try:
            from .a_stock_data_core import get_prefix
            prefix = get_prefix(code)
            tdx = tdx_client()
            df = tdx.get_k_data(code, start=start_date, end=end_date)
            if df is not None and not df.empty:
                parts.append(f"### K-line (TDX TCP, {len(df)} bars)")
                cols = [c for c in ['date', 'open', 'high', 'low', 'close', 'volume'] if c in df.columns]
                df_str = df.tail(60)[cols].to_string(index=False)
                parts.append(df_str)
            else:
                parts.append("No K-line data available from TDX either.")
        except Exception as exc:
            parts.append(f"TDX also failed: {type(exc).__name__}: {exc}")

        return "\n".join(parts)

    def get_indicators(
        self, symbol: str, indicator: str, curr_date: str, look_back_days: int
    ) -> str:
        """Technical indicators via TDX K-line data."""
        code = self._normalize_symbol(symbol)
        parts = [f"## Indicator: {indicator} for {symbol} (as of {curr_date})"]

        try:
            from .a_stock_data_core import get_prefix
            prefix = get_prefix(code)
            # Calculate start date based on look_back_days
            curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
            start_dt = (curr_dt - timedelta(days=max(look_back_days, 260))).strftime("%Y-%m-%d")

            tdx = tdx_client()
            df = tdx.get_k_data(code, start=start_dt, end=curr_date)
            if df is None or df.empty:
                return f"No K-line data available for {symbol} to compute indicators."

            # Calculate indicators using stockstats
            from stockstats import wrap
            stock = wrap(df)
            stock_data = stock.tail(20)

            parts.append(f"### Latest 20 bars with {indicator}")
            # Dynamically check if the indicator column exists
            indicator_col = indicator.lower().replace(" ", "_")
            if indicator_col in stock_data.columns:
                df_show = stock_data[["close", indicator_col]].tail(10)
                parts.append(df_show.to_string())
            else:
                # Return available indicators
                avail = [c for c in stock_data.columns if c != "close"]
                parts.append(f"Indicator '{indicator}' not found. Available: {avail[:20]}...")
        except Exception as exc:
            parts.append(f"Error computing indicators: {type(exc).__name__}: {exc}")

        return "\n".join(parts)

    def get_fundamentals(self, ticker: str, curr_date: str = None) -> str:
        """Fundamentals via eastmoney_stock_info + sina_financial_report."""
        code = self._normalize_symbol(ticker)
        parts = [f"## Fundamentals: {ticker}"]
        date_str = curr_date or datetime.now().strftime("%Y-%m-%d")

        # Company info
        try:
            info = eastmoney_stock_info(code)
            if info:
                parts.append(f"### Company Profile")
                for k, v in info.items():
                    parts.append(f"  {k}: {v}")
        except Exception as exc:
            parts.append(f"  Company info: {type(exc).__name__}: {exc}")

        # Recent financial data
        try:
            report = sina_financial_report(code, report_type="lrb", num=4)
            if report:
                parts.append(f"\n### Income Statement (recent 4 quarters)")
                for r in report:
                    parts.append(f"  {r.get('date','N/A')} | "
                                f"Revenue:{r.get('operating_revenue','N/A')}  "
                                f"NetProfit:{r.get('net_profit','N/A')}")
            else:
                parts.append("\n  (No income statement data)")
        except Exception as exc:
            parts.append(f"\n  Income statement: {type(exc).__name__}: {exc}")

        return "\n".join(parts)

    def get_balance_sheet(
        self, ticker: str, freq: str = "quarterly", curr_date: str = None
    ) -> str:
        """Balance sheet via sina_financial_report."""
        code = self._normalize_symbol(ticker)
        parts = [f"## Balance Sheet: {ticker}"]
        try:
            report = sina_financial_report(code, report_type="zcfzb", num=4)
            if report:
                for r in report:
                    parts.append(f"  {r.get('date','N/A')}: "
                                f"TotalAssets:{r.get('total_assets','N/A')}  "
                                f"TotalLiab:{r.get('total_liabilities','N/A')}  "
                                f"Equity:{r.get('total_equity','N/A')}")
            else:
                parts.append("  (No balance sheet data)")
        except Exception as exc:
            parts.append(f"  Error: {type(exc).__name__}: {exc}")
        return "\n".join(parts)

    def get_cashflow(
        self, ticker: str, freq: str = "quarterly", curr_date: str = None
    ) -> str:
        """Cash flow statement via sina_financial_report."""
        code = self._normalize_symbol(ticker)
        parts = [f"## Cash Flow: {ticker}"]
        try:
            report = sina_financial_report(code, report_type="xjllb", num=4)
            if report:
                for r in report:
                    parts.append(f"  {r.get('date','N/A')}: "
                                f"OperatingCF:{r.get('operating_cash_flow','N/A')}  "
                                f"InvestingCF:{r.get('investing_cash_flow','N/A')}  "
                                f"FinancingCF:{r.get('financing_cash_flow','N/A')}")
            else:
                parts.append("  (No cash flow data)")
        except Exception as exc:
            parts.append(f"  Error: {type(exc).__name__}: {exc}")
        return "\n".join(parts)

    def get_income_statement(
        self, ticker: str, freq: str = "quarterly", curr_date: str = None
    ) -> str:
        """Income statement via sina_financial_report."""
        code = self._normalize_symbol(ticker)
        parts = [f"## Income Statement: {ticker}"]
        try:
            report = sina_financial_report(code, report_type="lrb", num=8)
            if report:
                for r in report:
                    parts.append(f"  {r.get('date','N/A')}: "
                                f"Revenue:{r.get('operating_revenue','N/A')}  "
                                f"Cost:{r.get('operating_cost','N/A')}  "
                                f"NetProfit:{r.get('net_profit','N/A')}")
            else:
                parts.append("  (No income statement data)")
        except Exception as exc:
            parts.append(f"  Error: {type(exc).__name__}: {exc}")
        return "\n".join(parts)

    def get_news(self, ticker: str, start_date: str, end_date: str) -> str:
        """Stock news via eastmoney_stock_news."""
        code = self._normalize_symbol(ticker)
        parts = [f"## News: {ticker} ({start_date} ~ {end_date})"]
        try:
            news = eastmoney_stock_news(code, page_size=20)
            if news:
                for i, item in enumerate(news, 1):
                    parts.append(
                        f"  {i}. [{item.get('date','N/A')}] {item.get('title','N/A')}"
                    )
                    if item.get('summary'):
                        parts.append(f"     {item['summary'][:120]}")
            else:
                parts.append("  (No news data)")
        except Exception as exc:
            parts.append(f"  Error: {type(exc).__name__}: {exc}")
        return "\n".join(parts)

    def get_global_news(
        self, curr_date: str, look_back_days: int = 7, limit: int = 50
    ) -> str:
        """Global finance news via eastmoney_global_news."""
        parts = [f"## Global Finance News (as of {curr_date})"]
        try:
            news = eastmoney_global_news(page_size=limit)
            if news:
                for i, item in enumerate(news[:limit], 1):
                    parts.append(
                        f"  {i}. [{item.get('date','N/A')}] {item.get('title','N/A')}"
                    )
            else:
                parts.append("  (No global news data)")
        except Exception as exc:
            parts.append(f"  Error: {type(exc).__name__}: {exc}")
        return "\n".join(parts)

    def get_insider_transactions(self, symbol: str) -> str:
        """Insider transactions — uses a-stock-data's margin_trading as proxy."""
        code = self._normalize_symbol(symbol)
        parts = [f"## Insider/Margin Activity: {symbol}"]
        try:
            data = margin_trading(code, page_size=10)
            if data:
                for item in data[:10]:
                    parts.append(
                        f"  {item.get('date','N/A')}: "
                        f"融资余额:{item.get('rzye','N/A')}  "
                        f"融资买入:{item.get('rzmre','N/A')}  "
                        f"融券余额:{item.get('rqye','N/A')}  "
                        f"融券卖出:{item.get('rqmcl','N/A')}"
                    )
            else:
                parts.append("  (No margin trading data)")
        except Exception as exc:
            parts.append(f"  Error: {type(exc).__name__}: {exc}")
        return "\n".join(parts)

    def get_realtime_quotes(self, symbols: list[str]) -> str:
        """Real-time quotes via tencent_quote."""
        import json
        parts = [f"## Real-time Quotes"]
        codes = [self._normalize_symbol(s) for s in symbols]
        try:
            quotes = tencent_quote(codes)
            if quotes:
                result = {}
                for code, q in quotes.items():
                    result[code] = {
                        "price": q.get("price"),
                        "open": q.get("open"),
                        "high": q.get("high"),
                        "low": q.get("low"),
                        "previous_close": q.get("pre_close"),
                        "change": q.get("change"),
                        "change_pct": q.get("change_pct"),
                        "volume": q.get("volume"),
                        "amount": q.get("amount"),
                    }
                return json.dumps(result, ensure_ascii=False, indent=2)
            else:
                return json.dumps({})
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    # ── cn_market_data category (board fund flow, LHB, hot stocks) ──

    def get_board_fund_flow(self) -> str:
        """Sector fund flow / industry comparison."""
        parts = ["## Board Fund Flow (Industry Comparison)"]
        try:
            data = industry_comparison(top_n=20)
            if data and "industries" in data:
                parts.append(f"  {data.get('trade_date', 'N/A')}")
                for ind in data["industries"][:15]:
                    parts.append(
                        f"  {ind.get('name','N/A'):12s} | "
                        f"涨跌:{ind.get('change_pct','N/A'):>6}%  "
                        f"上涨:{ind.get('up_count','N/A')}  "
                        f"下跌:{ind.get('down_count','N/A')}"
                    )
            else:
                parts.append("  (No industry comparison data)")
        except Exception as exc:
            parts.append(f"  Error: {type(exc).__name__}: {exc}")
        return "\n".join(parts)

    def get_individual_fund_flow(self, symbol: str) -> str:
        """Individual stock fund flow via eastmoney_fund_flow_minute + 120d."""
        code = self._normalize_symbol(symbol)
        parts = [f"## Fund Flow: {symbol}"]

        # Minute-level today
        try:
            minute = eastmoney_fund_flow_minute(code)
            if minute:
                latest = minute[-1] if minute else {}
                parts.append(
                    f"  Today (latest minute): "
                    f"主力净流入:{latest.get('main_net','N/A')}  "
                    f"超大单:{latest.get('super_large_net','N/A')}  "
                    f"大单:{latest.get('large_net','N/A')}  "
                    f"中单:{latest.get('medium_net','N/A')}  "
                    f"小单:{latest.get('small_net','N/A')}"
                )
            else:
                parts.append("  (No minute-level fund flow)")
        except Exception as exc:
            parts.append(f"  Minute flow error: {type(exc).__name__}: {exc}")

        # 120-day history
        try:
            history = stock_fund_flow_120d(code)
            if history:
                parts.append(f"\n  ### 120-Day Fund Flow (last 15)")
                for item in history[-15:]:
                    parts.append(
                        f"  {item.get('date','N/A')}: "
                        f"主力净流:{item.get('main_net','N/A')}  "
                        f"小单净流:{item.get('small_net','N/A')}"
                    )
        except Exception as exc:
            parts.append(f"  120d flow error: {type(exc).__name__}: {exc}")

        return "\n".join(parts)

    def get_lhb_detail(self, symbol: str, date: str) -> str:
        """Dragon-tiger board detail via dragon_tiger_board."""
        code = self._normalize_symbol(symbol)
        parts = [f"## Dragon-Tiger Board: {symbol} (as of {date})"]
        try:
            data = dragon_tiger_board(code, date, look_back=30)
            if data:
                if data.get("records"):
                    for r in data["records"][:5]:
                        parts.append(
                            f"  {r.get('date','N/A')}: "
                            f"净买额:{r.get('net_buy','N/A')}  "
                            f"买入额:{r.get('buy_amount','N/A')}  "
                            f"卖出额:{r.get('sell_amount','N/A')}  "
                            f"机构买入:{r.get('inst_buy','N/A')}"
                        )
                if data.get("top_buyers"):
                    parts.append("\n  Top Buyers:")
                    for b in data["top_buyers"][:5]:
                        parts.append(f"    {b.get('name','N/A')}: {b.get('buy_amount','N/A')}")
                if data.get("top_sellers"):
                    parts.append("\n  Top Sellers:")
                    for s in data["top_sellers"][:5]:
                        parts.append(f"    {s.get('name','N/A')}: {s.get('sell_amount','N/A')}")
            else:
                parts.append("  (No dragon-tiger data for this period)")
        except Exception as exc:
            parts.append(f"  Error: {type(exc).__name__}: {exc}")
        return "\n".join(parts)

    def get_zt_pool(self, date: str) -> str:
        """Limit-up stocks via daily_dragon_tiger (surrogate for ZT pool)."""
        parts = [f"## Limit-Up / Strong Stocks: {date}"]
        try:
            data = daily_dragon_tiger(trade_date=date)
            if data and data.get("stocks"):
                for s in data["stocks"][:10]:
                    parts.append(
                        f"  {s.get('code','N/A')} {s.get('name','N/A')}: "
                        f"净买额:{s.get('net_buy','N/A')}  "
                        f"原因:{s.get('reason','N/A')}"
                    )
            else:
                # Fall back to ths_hot_reason
                hot = ths_hot_reason(date=date)
                if hot is not None and not hot.empty:
                    for _, row in hot.head(15).iterrows():
                        parts.append(
                            f"  {row.get('code','N/A')} {row.get('name','N/A')}: "
                            f"{row.get('reason','N/A')}"
                        )
                else:
                    parts.append("  (No hot stock data for this date)")
        except Exception as exc:
            parts.append(f"  Error: {type(exc).__name__}: {exc}")
        return "\n".join(parts)

    def get_hot_stocks_xq(self) -> str:
        """Hot stocks via ths_hot_reason."""
        parts = ["## Hot Stocks (THS Reason Tags)"]
        try:
            hot = ths_hot_reason()
            if hot is not None and not hot.empty:
                for _, row in hot.head(20).iterrows():
                    parts.append(
                        f"  {row.get('code','N/A')} {row.get('name','N/A')}: "
                        f"{row.get('reason','N/A')}  "
                        f"涨跌幅:{row.get('change_pct','N/A')}%"
                    )
            else:
                parts.append("  (No hot stock data)")
        except Exception as exc:
            parts.append(f"  Error: {type(exc).__name__}: {exc}")
        return "\n".join(parts)

    # ── NEW: Research Reports (beyond standard interface) ──

    def get_research_reports(self, symbol: str, max_pages: int = 5) -> str:
        """Research reports from Eastmoney."""
        code = self._normalize_symbol(symbol)
        parts = [f"## Research Reports: {symbol}"]
        try:
            reports = eastmoney_reports(code, max_pages=max_pages)
            if reports:
                for i, r in enumerate(reports[:10], 1):
                    parts.append(
                        f"  {i}. {r.get('title','N/A')} "
                        f"({r.get('org_name','N/A')}, {r.get('date','N/A')})"
                    )
                    if r.get('rating'):
                        parts.append(f"     评级: {r['rating']}  "
                                    f"EPS预测: E1={r.get('eps_1','N/A')} "
                                    f"E2={r.get('eps_2','N/A')} "
                                    f"E3={r.get('eps_3','N/A')}")
            else:
                parts.append("  (No research reports)")
        except Exception as exc:
            parts.append(f"  Error: {type(exc).__name__}: {exc}")
        return "\n".join(parts)

    def get_industry_reports(self, industry_code: str = "*", max_pages: int = 5) -> str:
        """Industry research reports from Eastmoney."""
        parts = [f"## Industry Reports (code={industry_code})"]
        try:
            reports = eastmoney_industry_reports(industry_code=industry_code, max_pages=max_pages)
            if reports:
                for i, r in enumerate(reports[:10], 1):
                    parts.append(
                        f"  {i}. {r.get('title','N/A')} "
                        f"({r.get('org_name','N/A')}, {r.get('date','N/A')})"
                    )
                    if r.get('rating'):
                        parts.append(f"     行业: {r.get('industry_name','N/A')}  "
                                    f"评级: {r['rating']}")
            else:
                parts.append("  (No industry reports)")
        except Exception as exc:
            parts.append(f"  Error: {type(exc).__name__}: {exc}")
        return "\n".join(parts)

    def get_consensus_eps(self, symbol: str) -> str:
        """Consensus EPS from THS."""
        code = self._normalize_symbol(symbol)
        parts = [f"## Consensus EPS: {symbol}"]
        try:
            df = ths_eps_forecast(code)
            if df is not None and not df.empty:
                parts.append(df.to_string(index=False))
            else:
                parts.append("  (No consensus EPS data)")
        except Exception as exc:
            parts.append(f"  Error: {type(exc).__name__}: {exc}")
        return "\n".join(parts)

    def search_reports_nl(self, query: str, size: int = 50) -> str:
        """Natural language report search via iwencai."""
        parts = [f"## Report Search: {query}"]
        try:
            results = iwencai_search(query, size=size)
            if results:
                for r in results[:10]:
                    parts.append(
                        f"  {r.get('title','N/A')} ({r.get('date','N/A')})"
                    )
            else:
                parts.append("  (iwencai returned no results)")
        except Exception as exc:
            parts.append(f"  Error: {type(exc).__name__}: {exc}")
        return "\n".join(parts)

    # ── NEW: Capital Flow / Ownership ──

    def get_margin_trading(self, symbol: str) -> str:
        """Margin trading details."""
        code = self._normalize_symbol(symbol)
        parts = [f"## Margin Trading: {symbol}"]
        try:
            data = margin_trading(code, page_size=20)
            if data:
                for item in data[:15]:
                    parts.append(
                        f"  {item.get('date','N/A')}: "
                        f"融资余额:{item.get('rzye','N/A')}  "
                        f"融资买入:{item.get('rzmre','N/A')}  "
                        f"融资偿还:{item.get('rzche','N/A')}  "
                        f"融券余额:{item.get('rqye','N/A')}"
                    )
            else:
                parts.append("  (No margin trading data)")
        except Exception as exc:
            parts.append(f"  Error: {type(exc).__name__}: {exc}")
        return "\n".join(parts)

    def get_block_trades(self, symbol: str) -> str:
        """Block trade history."""
        code = self._normalize_symbol(symbol)
        parts = [f"## Block Trades: {symbol}"]
        try:
            data = block_trade(code, page_size=15)
            if data:
                for item in data[:10]:
                    parts.append(
                        f"  {item.get('date','N/A')}: "
                        f"成交价:{item.get('price','N/A')}  "
                        f"成交量:{item.get('volume','N/A')}  "
                        f"溢价率:{item.get('premium','N/A')}%  "
                        f"买方:{item.get('buyer','N/A')}  "
                        f"卖方:{item.get('seller','N/A')}"
                    )
            else:
                parts.append("  (No block trade data)")
        except Exception as exc:
            parts.append(f"  Error: {type(exc).__name__}: {exc}")
        return "\n".join(parts)

    def get_holder_count(self, symbol: str) -> str:
        """Shareholder count change (chip concentration)."""
        code = self._normalize_symbol(symbol)
        parts = [f"## Shareholder Count: {symbol}"]
        try:
            data = holder_num_change(code, page_size=10)
            if data:
                for item in data:
                    parts.append(
                        f"  {item.get('date','N/A')}: "
                        f"股东数:{item.get('holder_num','N/A')}  "
                        f"环比:{item.get('change_pct','N/A')}%  "
                        f"户均持股:{item.get('avg_shares','N/A')}"
                    )
            else:
                parts.append("  (No shareholder count data)")
        except Exception as exc:
            parts.append(f"  Error: {type(exc).__name__}: {exc}")
        return "\n".join(parts)

    def get_dividend_history(self, symbol: str) -> str:
        """Dividend history."""
        code = self._normalize_symbol(symbol)
        parts = [f"## Dividend History: {symbol}"]
        try:
            data = dividend_history(code, page_size=15)
            if data:
                for item in data:
                    parts.append(
                        f"  {item.get('date','N/A')}: "
                        f"每股派息:{item.get('cash_dividend','N/A')}  "
                        f"送股:{item.get('bonus_shares','N/A')}  "
                        f"转增:{item.get('transfer_shares','N/A')}  "
                        f"进度:{item.get('progress','N/A')}"
                    )
            else:
                parts.append("  (No dividend data)")
        except Exception as exc:
            parts.append(f"  Error: {type(exc).__name__}: {exc}")
        return "\n".join(parts)

    # ── NEW: Lockup / Concept / Filings ──

    def get_lockup_expiry(self, symbol: str, forward_days: int = 90) -> str:
        """Lockup share expiry calendar."""
        code = self._normalize_symbol(symbol)
        parts = [f"## Lockup Expiry: {symbol} (next {forward_days}d)"]
        try:
            from datetime import date
            data = lockup_expiry(code, date.today().strftime("%Y-%m-%d"), forward_days=forward_days)
            if data:
                if data.get("historical"):
                    parts.append("  Historical:")
                    for h in data["historical"][:5]:
                        parts.append(f"    {h.get('date','N/A')}: {h.get('volume','N/A')} shares")
                if data.get("upcoming"):
                    parts.append("  Upcoming:")
                    for u in data["upcoming"]:
                        parts.append(
                            f"    {u.get('date','N/A')}: "
                            f"{u.get('volume','N/A')} shares "
                            f"({u.get('ratio','N/A')}% of float)"
                        )
                else:
                    parts.append("  (No upcoming lockup expiry)")
            else:
                parts.append("  (No lockup data)")
        except Exception as exc:
            parts.append(f"  Error: {type(exc).__name__}: {exc}")
        return "\n".join(parts)

    def get_concept_blocks(self, symbol: str) -> str:
        """All sector/concept/region blocks for a stock."""
        code = self._normalize_symbol(symbol)
        parts = [f"## Concept & Sector Blocks: {symbol}"]
        try:
            blocks = eastmoney_concept_blocks(code)
            if blocks:
                for category in ["industry", "concept", "region"]:
                    items = blocks.get(category, [])
                    if items:
                        parts.append(f"\n  [{category.upper()}]")
                        for b in items[:10]:
                            parts.append(
                                f"    {b.get('name','N/A')}({b.get('bk_code','N/A')}): "
                                f"{b.get('change_pct','N/A')}%  "
                                f"龙头:{b.get('leading_stock','N/A')}"
                            )
            else:
                parts.append("  (No block data)")
        except Exception as exc:
            parts.append(f"  Error: {type(exc).__name__}: {exc}")
        return "\n".join(parts)

    def get_filings(self, symbol: str) -> str:
        """Company filings from cninfo."""
        code = self._normalize_symbol(symbol)
        parts = [f"## Filings: {symbol}"]
        try:
            announcements = cninfo_announcements(code, page_size=15)
            if announcements:
                for i, a in enumerate(announcements[:10], 1):
                    parts.append(
                        f"  {i}. {a.get('title','N/A')} ({a.get('date','N/A')})"
                    )
            else:
                parts.append("  (No filing data)")
        except Exception as exc:
            parts.append(f"  Error: {type(exc).__name__}: {exc}")
        return "\n".join(parts)

    def get_valuation(self, symbol: str) -> str:
        """Full valuation: forward PE, PEG, PE digestion years."""
        code = self._normalize_symbol(symbol)
        parts = [f"## Valuation: {symbol}"]
        try:
            val = full_valuation(code)
            if val:
                for k, v in val.items():
                    if isinstance(v, dict):
                        parts.append(f"  {k}:")
                        for sk, sv in v.items():
                            parts.append(f"    {sk}: {sv}")
                    else:
                        parts.append(f"  {k}: {v}")
            else:
                parts.append("  (Valuation data unavailable)")
        except Exception as exc:
            parts.append(f"  Error: {type(exc).__name__}: {exc}")
        return "\n".join(parts)

    def get_northbound_flow(self) -> str:
        """Northbound (HK Stock Connect) real-time flow."""
        parts = ["## Northbound Flow (HK Stock Connect)"]
        try:
            df = hsgt_realtime()
            if df is not None and not df.empty:
                parts.append(df.to_string(index=False))
            else:
                parts.append("  (No northbound flow data)")
        except Exception as exc:
            parts.append(f"  Error: {type(exc).__name__}: {exc}")
        return "\n".join(parts)

    def get_full_market_dragon_tiger(self, trade_date: str = None) -> str:
        """Full market dragon-tiger board ranking."""
        parts = [f"## Full Market Dragon-Tiger Board"]
        try:
            data = daily_dragon_tiger(trade_date=trade_date, min_net_buy=0)
            if data and data.get("stocks"):
                parts.append(f"  Trade date: {data.get('trade_date', 'N/A')}")
                for i, s in enumerate(data["stocks"][:10], 1):
                    parts.append(
                        f"  {i}. {s.get('code','N/A')} {s.get('name','N/A')}: "
                        f"净买额:{s.get('net_buy','N/A')}  "
                        f"原因:{s.get('reason','N/A')}"
                    )
            else:
                parts.append("  (No dragon-tiger data)")
        except Exception as exc:
            parts.append(f"  Error: {type(exc).__name__}: {exc}")
        return "\n".join(parts)
