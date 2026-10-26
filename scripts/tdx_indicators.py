# -*- coding: utf-8 -*-
"""
通达信本机技术指标计算器（纯 Python，无第三方依赖）
==================================================
对指定股票计算最近 N 个交易日（默认 250）的：
  - 收盘价 / 成交量(手) / 成交额(万元) / 当日换手率%
  - MA5 / MA10 / MA20 / MA60 / MA120 及其斜率(回归%, 每日)
  - 均线粘合度 = (max-min)/均值 * 100  （越小越粘合）
  - 量比 = 当日成交量 / 前5日平均成交量
  - 20日平均换手率% = 最近20日换手率均值
  - 60日涨停次数 = 最近60日(含当日)封板收盘天数
  - 60日新高突破 = 当日收盘 > 前60日最高收盘

依赖同目录： tdx_reader.py (日线) / tdx_float.py (流通股本) / stock_names.py (名称,判定ST)

用法：
  python tdx_indicators.py 600513 --days 250 --out reports/600513_250.csv

性能：MA 采用滚动求和；斜率用预计算的均线序列做回归；涨停用前缀和。
      全量 5600+ 日由 ~7.8s 降至亚秒级。
"""
import os
import sys
import csv
from decimal import Decimal, ROUND_HALF_UP

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from tdx_reader import load_daily, date_str        # noqa: E402
from tdx_float import get_float_shares             # noqa: E402


def _round2_half_up(x: float) -> float:
    """交易所口径：四舍五入到分（Python 内置 round 为银行家舍入，低價股会算错）。"""
    return float(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _limit_pct(code: str, name: str = "") -> float:
    """按板块返回涨停幅度（小数）。
    北交所30% / 创业板·科创板20% / 主板10% / 主板ST 5%（创业·科创ST 仍 20%）。"""
    c = code.strip().lower()
    if c.startswith(("sh", "sz", "bj")):
        c = c[2:]
    if c[:2] in ("43", "83", "87", "88", "92") or c[:1] in ("4", "8"):
        return 0.30
    if c.startswith("688") or c.startswith("689") or c.startswith("30"):
        return 0.20
    if "ST" in (name or "").upper():
        return 0.05
    return 0.10


def _is_limit_up(prev_close, close, high, pct_limit):
    """精确判定：收盘价等于涨停价(四舍五入到分)且封板（收盘≈最高）。"""
    if prev_close <= 0:
        return False
    limit_price = _round2_half_up(prev_close * (1 + pct_limit))
    if abs(close - limit_price) > 0.005:
        return False
    return (high - close) < 0.01 * close + 1e-9


def _linreg_slope_pct(series):
    """对一段序列做最小二乘，返回 斜率%/天 = b / mean(y) * 100。"""
    n = len(series)
    if n < 2:
        return None
    xs = list(range(n))
    mx = (n - 1) / 2.0
    my = sum(series) / n
    num = 0.0
    for k in range(n):
        num += (xs[k] - mx) * (series[k] - my)
    den = sum((xs[k] - mx) ** 2 for k in range(n))
    if den == 0 or my == 0:
        return None
    return (num / den) / my * 100.0


def _sma_series(vals, w):
    """计算 MA 序列（None 表示不足 w 日）。按窗口精确求和，避免长序列滚动累加漂移。"""
    out = [None] * len(vals)
    if w <= 0:
        return out
    for i in range(w - 1, len(vals)):
        out[i] = sum(vals[i - w + 1:i + 1]) / w
    return out


def _round(v, n=4):
    return None if v is None else round(v, n)


def compute(code, days=250):
    bars = load_daily(code)
    if len(bars) < days:
        # 数据不足则取全部
        days = len(bars)
    float_shares, total_shares = get_float_shares(code)
    try:
        from stock_names import code_to_name
        name = code_to_name(code)
    except Exception:
        name = ""
    pct_limit = _limit_pct(code, name)

    closes = [b.close for b in bars]
    vols = [b.volume for b in bars]          # 股
    highs = [b.high for b in bars]
    n = len(bars)

    # 预计算各周期均线（滚动求和, O(n)）
    MA = {w: _sma_series(closes, w) for w in (5, 10, 20, 60, 120)}

    # 预计算每日换手率%
    if float_shares and float_shares > 0:
        turnover = [v / float_shares * 100.0 for v in vols]
    else:
        turnover = [None] * n

    # 预计算涨停标记 + 前缀和（O(n) 后每行 O(1) 统计60日涨停数）
    up_flag = [0] * n
    for j in range(1, n):
        if _is_limit_up(closes[j - 1], closes[j], highs[j], pct_limit):
            up_flag[j] = 1
    up_pref = [0] * (n + 1)
    for j in range(n):
        up_pref[j + 1] = up_pref[j] + up_flag[j]

    # 量比分母：前5日均量（滚动）
    rows = []
    start = max(0, n - days)
    for i in range(start, n):
        c = closes[i]
        mas = {w: MA[w][i] for w in MA}

        # 均线斜率：用该均线自身序列在最近 w 个点做回归
        slopes = {}
        for w in (5, 10, 20, 60, 120):
            if i - w + 1 < 0:
                slopes[w] = None
                continue
            seg = [MA[w][j] for j in range(i - w + 1, i + 1)]
            seg = [x for x in seg if x is not None]
            slopes[w] = _linreg_slope_pct(seg)

        # 均线粘合度
        mlist = [x for x in mas.values() if x is not None]
        if len(mlist) >= 2 and sum(mlist) > 0:
            convergence = (max(mlist) - min(mlist)) / (sum(mlist) / len(mlist)) * 100.0
        else:
            convergence = None

        # 量比：当日量 / 前5日均量
        if i >= 5:
            vr = vols[i] / (sum(vols[i - 5:i]) / 5.0)
        elif i >= 1:
            vr = vols[i] / (sum(vols[:i]) / i)
        else:
            vr = None

        # 20日平均换手率
        if i >= 19 and all(x is not None for x in turnover[i - 19:i + 1]):
            t20 = sum(turnover[i - 19:i + 1]) / 20.0
        else:
            t20 = None

        # 60日涨停次数（含当日）—— 前缀和
        lo = max(0, i - 59)
        cnt = up_pref[i + 1] - up_pref[lo]

        # 60日新高突破：当日收盘 > 前60日最高收盘
        if i >= 1:
            prior = closes[max(0, i - 60):i]
            nh = 1 if prior and c > max(prior) else 0
        else:
            nh = 0

        rows.append({
            "date": date_str(bars[i].date),
            "close": _round(c, 2),
            "vol_hand": _round(vols[i] / 100.0, 0),          # 手
            "amount_wan": _round(bars[i].amount / 1e4, 1),   # 万元
            "turnover_pct": _round(turnover[i], 3),
            "MA5": _round(mas[5], 3),
            "MA10": _round(mas[10], 3),
            "MA20": _round(mas[20], 3),
            "MA60": _round(mas[60], 3),
            "MA120": _round(mas[120], 3),
            "slope_MA5": _round(slopes[5], 4),
            "slope_MA10": _round(slopes[10], 4),
            "slope_MA20": _round(slopes[20], 4),
            "slope_MA60": _round(slopes[60], 4),
            "slope_MA120": _round(slopes[120], 4),
            "ma_convergence_pct": _round(convergence, 3),
            "volume_ratio": _round(vr, 3),
            "turnover_20avg_pct": _round(t20, 3),
            "limitup_60_count": cnt,
            "newhigh_60_break": nh,
        })
    meta = {
        "code": code,
        "name": name,
        "float_shares": float_shares,
        "total_shares": total_shares,
        "pct_limit": pct_limit,
        "bars_total": n,
    }
    return rows, meta


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("code")
    ap.add_argument("--days", "-n", type=int, default=250)
    ap.add_argument("--out", default="reports/indicators.csv")
    args = ap.parse_args()

    rows, meta = compute(args.code, args.days)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    fields = ["date", "close", "vol_hand", "amount_wan", "turnover_pct",
              "MA5", "MA10", "MA20", "MA60", "MA120",
              "slope_MA5", "slope_MA10", "slope_MA20", "slope_MA60", "slope_MA120",
              "ma_convergence_pct", "volume_ratio", "turnover_20avg_pct",
              "limitup_60_count", "newhigh_60_break"]
    with open(args.out, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    fs = meta["float_shares"]
    ts = meta["total_shares"]
    print(f"已写出 {len(rows)} 行 -> {args.out}")
    print(f"{meta['code']}({meta.get('name') or '?'})  "
          f"流通股本={'—' if not fs else f'{fs/1e8:.4f}亿股'}  "
          f"总股本={'—' if not ts else f'{ts/1e8:.4f}亿股'}  "
          f"涨停幅度={meta['pct_limit']*100:.0f}%  本地日线总数={meta['bars_total']}")


if __name__ == "__main__":
    main()
