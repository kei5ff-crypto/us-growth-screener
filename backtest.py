"""Point-in-time cohort backtest for historical growth-stock scores.

Input rows represent stocks eligible on a rebalance date. Scores and forward returns
must be constructed without using information unavailable on that date.
Optional benchmark_return_pct is the benchmark's return over the same forward window.
This module does NOT retrieve historical SEC filings or correct survivorship bias.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import pandas as pd

REQUIRED = {"date", "ticker", "score", "forward_return_pct"}

def load_candidates(file_path):
    df = pd.read_csv(file_path)
    missing = REQUIRED - set(df.columns)
    if missing:
        raise ValueError(f"필수 열 누락: {sorted(missing)}")
    df["date"] = pd.to_datetime(df["date"], errors="raise")
    df["ticker"] = df["ticker"].astype(str).str.upper().str.strip()
    for col in ["score", "forward_return_pct", "benchmark_return_pct"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["date", "ticker", "score", "forward_return_pct"])
    df = df[df["ticker"] != ""].drop_duplicates(["date", "ticker"], keep="last")
    if df.empty:
        raise ValueError("평가 가능한 데이터가 없습니다.")
    if not df["score"].between(0, 100).all():
        raise ValueError("score는 0~100 범위여야 합니다.")
    return df.sort_values(["date", "score"], ascending=[True, False]).reset_index(drop=True)

def _max_drawdown(returns):
    wealth = (1 + returns / 100).cumprod()
    peak = wealth.cummax()
    return float(((wealth / peak) - 1).min() * 100)

def evaluate_point_in_time(file_path, top_fraction=0.20, cost_bps=20):
    """Equal-weight top-score cohort per date; cost is deducted once per rebalance.

    `cost_bps` is a simple one-way portfolio friction assumption per rebalance,
    not a turnover-derived estimate. Set to 0 for gross returns.
    """
    if not 0 < top_fraction <= 1:
        raise ValueError("top_fraction은 0 초과 1 이하이어야 합니다.")
    if cost_bps < 0:
        raise ValueError("cost_bps는 음수일 수 없습니다.")
    df = load_candidates(file_path)
    picks = []
    for date, group in df.groupby("date", sort=True):
        group = group.sort_values(["score", "ticker"], ascending=[False, True])
        n = max(1, int(len(group) * top_fraction + 0.999999))
        chosen = group.head(n).copy()
        chosen["cohort_weight"] = 1.0 / len(chosen)
        picks.append(chosen)
    selected = pd.concat(picks, ignore_index=True)
    by_date = selected.groupby("date").agg(
        stocks=("ticker", "count"),
        gross_return_pct=("forward_return_pct", "mean"),
        score_mean=("score", "mean"),
    ).sort_index()
    by_date["estimated_cost_pct"] = cost_bps / 100.0
    by_date["net_return_pct"] = by_date["gross_return_pct"] - by_date["estimated_cost_pct"]

    if "benchmark_return_pct" in selected.columns:
        bench = selected.groupby("date")["benchmark_return_pct"].mean().reindex(by_date.index)
        by_date["benchmark_return_pct"] = bench
        by_date["excess_return_pct"] = by_date["net_return_pct"] - bench
    else:
        by_date["benchmark_return_pct"] = float("nan")
        by_date["excess_return_pct"] = float("nan")

    net = by_date["net_return_pct"].astype(float)
    summary = {
        "input_rows": int(len(df)),
        "selected_observations": int(len(selected)),
        "rebalance_dates": int(len(by_date)),
        "top_fraction": float(top_fraction),
        "cost_bps_per_rebalance": float(cost_bps),
        "mean_gross_return_pct": float(by_date["gross_return_pct"].mean()),
        "mean_net_return_pct": float(net.mean()),
        "median_net_return_pct": float(net.median()),
        "positive_cohort_rate_pct": float((net > 0).mean() * 100),
        "cumulative_compounded_net_return_pct": float(((1 + net / 100).prod() - 1) * 100),
        "max_drawdown_pct": _max_drawdown(net),
        "mean_benchmark_return_pct": float(by_date["benchmark_return_pct"].mean()) if by_date["benchmark_return_pct"].notna().any() else None,
        "mean_excess_return_pct": float(by_date["excess_return_pct"].mean()) if by_date["excess_return_pct"].notna().any() else None,
    }
    return summary, by_date, selected

def main():
    parser = argparse.ArgumentParser(description="Point-in-time growth-stock cohort backtest")
    parser.add_argument("csv", help="historical point-in-time candidate CSV")
    parser.add_argument("--top-fraction", type=float, default=0.20, help="top-score fraction (default 0.20)")
    parser.add_argument("--cost-bps", type=float, default=20, help="estimated friction per rebalance in bps (default 20)")
    parser.add_argument("--out-prefix", default="backtest_result", help="output file prefix")
    args = parser.parse_args()
    summary, by_date, selected = evaluate_point_in_time(args.csv, args.top_fraction, args.cost_bps)
    prefix = Path(args.out_prefix)
    by_date.to_csv(f"{prefix}_by_date.csv", encoding="utf-8-sig")
    selected.to_csv(f"{prefix}_selected.csv", index=False, encoding="utf-8-sig")
    Path(f"{prefix}_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"저장: {prefix}_by_date.csv, {prefix}_selected.csv, {prefix}_summary.json")

if __name__ == "__main__":
    main()
