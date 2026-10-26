# -*- coding: utf-8 -*-
"""
通达信 复权行情数据生成器（前复权 qfq / 后复权 hfq）
================================================================
本机 vipdoc/{mkt}/lday/*.day 只存【不复权原始价】；复权缓存 fzline/ 通常为空。
本工具据本机通达信数据本地计算前复权与后复权，接口统一、离线可用。

复权口径（通达信标准「除权除息」公式，与 TDX 软件一致）：
  对每个除权除息事件 e（除权日 D，每股派现 div、送转 bonus、配股 rights、配股价 rprice），
  以 D 前一交易日收盘价 P0 计：
      理论除权价 P_ex = (P0 - div + rights*rprice) / (1 + bonus + rights)
      事件因子   k_e  = P0 / P_ex                       （≥1，反映“缺口”大小）
  累计因子 cf(t)   = ∏ { k_e : 除权日 ≤ t }
  后复权  hfq(t)   = 原始价(t) × cf(t)                 （以“上市首日”为基准，早期价=原始价）
  前复权  qfq(t)   = 原始价(t) × cf(t) / K,  K=∏ 全部 k_e（以“最新日”为基准，最新价=原始价）
  二者关系：hfq(t) = qfq(t) × K   —— 同一套因子，严格自洽。

精度与来源说明：
  - 事件来源 = 本机 T0002/hq_cache/gbbq（通达信权威除权除息数据），完全离线。
  - 前复权在最近区间与券商/腾讯 qfq 逐日吻合（实测 0.000%）；越早的历史，各数据商
    对「现金分红是否复投」处理不同会有差异，本工具遵循通达信标准公式，且前后复权自洽。
  - 本地价、量、额均来自你自己的 TDX；复权仅作用于价格，成交量/成交额保持原始值。

库用法（推荐）：
  from tdx_adjust import load_adjusted
  q = load_adjusted("600519", mode="qfq", days=250)   # list[dict]
  h = load_adjusted("600519", mode="hfq", days=250)

命令行：
  python tdx_adjust.py 600519 --mode qfq --days 300 --csv --html
  python tdx_adjust.py 300750 --mode hfq --days 300 --html
  python tdx_adjust.py 600519 --mode qfq --source tencent --days 300   # 与券商口径核对
"""
import os
import sys
import json
import argparse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import tdx_reader as T          # noqa: E402
import tdx_xdxr as X            # noqa: E402

TENCENT_FQKLINE = ("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
                   "?param={full},day,,,{n},{kind}")
DEFAULT_OUT = os.path.join(os.getcwd(), "reports")


# ----------------------------------------------------------------------------
# 核心：由本地原始价 + 事件 计算复权因子与复权价
# ----------------------------------------------------------------------------
def event_ratio(prev_close, ev):
    """单个除权除息事件的复权因子 k = P0 / P_ex（通达信标准公式）。"""
    denom = 1.0 + ev["bonus"] + ev["rights"]
    theo = (prev_close - ev["div"] + ev["rights"] * ev["rprice"]) / denom
    if theo <= 0 or prev_close <= 0:
        return 1.0
    return prev_close / theo


def build_event_ratios(bars, events):
    """为每个事件匹配「除权日前一交易日收盘价」并算 k。返回 [(date, k, ev), ...]。"""
    dates = [b.date for b in bars]
    closes = [b.close for b in bars]
    out = []
    for ev in events:
        d = ev["date"]
        # 二分找最后一个 date < d 的交易日
        lo, hi, pos = 0, len(dates), -1
        while lo < hi:
            mid = (lo + hi) // 2
            if dates[mid] < d:
                pos = mid
                lo = mid + 1
            else:
                hi = mid
        if pos < 0:                       # 事件早于本地可见历史，无法定基，跳过
            continue
        out.append((d, event_ratio(closes[pos], ev), ev))
    return out


def build_adjust_factors(bars, events, mode="qfq"):
    """返回 (factors, K)：factors 与 bars 等长（对应每日复权因子）。
    mode=qfq: 因子 = cf(t)/K ；mode=hfq: 因子 = cf(t)。"""
    ratios = build_event_ratios(bars, events)
    K = 1.0
    for _, k, _ in ratios:
        K *= k
    # 事件按日期升序，逐日推进
    ratios.sort(key=lambda x: x[0])
    factors = []
    cf = 1.0
    j = 0
    n = len(ratios)
    for b in bars:
        while j < n and ratios[j][0] <= b.date:
            cf *= ratios[j][1]
            j += 1
        factors.append(cf / K if mode == "qfq" else cf)
    return factors, K


def adjust_bars(bars, events, mode="qfq"):
    """返回 list[dict]：date,o,h,l,c(复权),v(原始股),amt(原始元),raio(原始收盘),factor,src。"""
    if mode not in ("qfq", "hfq", "none"):
        raise ValueError("mode 只能是 qfq / hfq / none")
    if mode == "none":
        factors = [1.0] * len(bars)
        K = 1.0
    else:
        factors, K = build_adjust_factors(bars, events, mode)
    rows = []
    for b, f in zip(bars, factors):
        rows.append({
            "date": b.date,
            "o": round(b.open * f, 4), "h": round(b.high * f, 4),
            "l": round(b.low * f, 4), "c": round(b.close * f, 4),
            "v": b.volume,                       # 原始成交量（股）
            "amt": b.amount,                     # 原始成交额（元）
            "raw_c": b.close,                    # 原始收盘（对照）
            "factor": round(f, 8),
            "src": "local",
        })
    return rows, K


# ----------------------------------------------------------------------------
# 可选：腾讯前复权（与券商口径核对用；仅支持 qfq）
# ----------------------------------------------------------------------------
def fetch_tencent_qfq(code, ndays):
    """返回 {YYYYMMDD:int: close} 腾讯前复权收盘（权威 qfq 源，仅 qfq）。"""
    full = code if code.lower().startswith(("sh", "sz", "bj")) else _market(code) + code
    url = TENCENT_FQKLINE.format(full=full, n=ndays + 5, kind="qfq")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    txt = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
    j = json.loads(txt)
    rows = j["data"][full]["qfqday"]
    return {int(r[0].replace("-", "")): float(r[2]) for r in rows}


def _market(code):
    c = code.lower()
    return c[:2] if c.startswith(("sh", "sz", "bj")) else T._market_of(c)


# ----------------------------------------------------------------------------
# 主入口
# ----------------------------------------------------------------------------
def load_adjusted(code, mode="qfq", days=None, source="local"):
    """读取并复权。返回 (full_code, rows, K)。
    mode   : 'qfq' 前复权 / 'hfq' 后复权 / 'none' 不复权
    days   : 仅返回最近 N 个交易日（None=全部）
    source : 'local'（本机 gbbq，默认） / 'tencent'（仅 mode='qfq'，与券商口径核对）
    """
    full, path = T.resolve_path(code)
    if path is None:
        raise FileNotFoundError(f"未找到 {code} 的日线文件（已搜索 sh/sz/bj）")
    bars = T.load_daily(code)

    if source == "tencent" and mode == "qfq":
        rows, _ = adjust_bars(bars, [], "none")
        try:
            tc = fetch_tencent_qfq(full, days or len(bars))
        except Exception as e:                       # 联网失败回退本地，不静默
            print(f"[warn] 腾讯 qfq 获取失败，已回退本地计算: {e}", file=sys.stderr)
            events = X.get_events(full)
            rows, K = adjust_bars(bars, events, "qfq")
        else:
            rows, K = _apply_tencent(bars, tc, mode)
    else:
        events = X.get_events(full)
        rows, K = adjust_bars(bars, events, mode)

    if days and days > 0:
        rows = rows[-days:]
    return full, rows, K


def _apply_tencent(bars, tc_close, mode):
    """用腾讯 qfq 收盘重算复权 OHLC（保持序列内部连续）。"""
    out = []
    K = None
    for b in bars:
        c = tc_close.get(b.date)
        if c is None:
            continue
        f = (c / b.close) if b.close else 1.0
        if b.date == max(tc_close) and K is None:
            K = 1.0
        out.append({
            "date": b.date,
            "o": round(b.open * f, 4), "h": round(b.high * f, 4),
            "l": round(b.low * f, 4), "c": round(c, 4),
            "v": b.volume, "amt": b.amount, "raw_c": b.close,
            "factor": round(f, 8), "src": "tencent",
        })
    return out, (K or 1.0)


# ----------------------------------------------------------------------------
# 图表（自包含 SVG）
# ----------------------------------------------------------------------------
def candle_svg(adj, exdates, title, n=None):
    N = len(adj)
    W = 1000; L = 58; R = 18; PW = W - L - R
    PH = 370; PADT = 15; PADB = 10; VH = 120; VTOP = PH + PADB + 30
    lo = min(a["l"] for a in adj); hi = max(a["h"] for a in adj)
    if hi <= lo:
        hi = lo + 1
    lo -= (hi - lo) * 0.03; hi += (hi - lo) * 0.03

    def y(p):
        return PADT + (hi - p) / (hi - lo) * (PH - PADT - PADB)

    vmax = max(a["v"] for a in adj) or 1

    def vx(i):
        return L + (i + 0.5) / N * PW

    bw = max(1.0, PW / N * 0.62)
    H = VTOP + VH + 20
    s = [f"<svg xmlns='http://www.w3.org/2000/svg' width='{W}' height='{H}' "
         f"viewBox='0 0 {W} {H}' font-family='system-ui' font-size='11'>"
         f"<rect width='{W}' height='{H}' fill='#fff'/>"]
    if title:
        s.append(f"<text x='{L}' y='12' fill='#b00' font-size='13' font-weight='600'>{title}</text>")
    for k in range(6):
        p = hi - (hi - lo) * k / 5; yy = y(p)
        s.append(f"<line x1='{L}' y1='{yy:.1f}' x2='{L+PW}' y2='{yy:.1f}' stroke='#eee'/>")
        s.append(f"<text x='{L-6}' y='{yy+3:.1f}' text-anchor='end' fill='#666'>{p:.2f}</text>")
    for i in range(0, N, max(1, N // 12)):
        d = adj[i]["date"]
        s.append(f"<text x='{vx(i):.1f}' y='{PH+12}' text-anchor='middle' fill='#666'>"
                 f"{d%10000//100:02d}-{d%100:02d}</text>")
    exset = set(exdates or [])
    for i, a in enumerate(adj):
        if a["date"] in exset:
            s.append(f"<line x1='{vx(i):.1f}' y1='{PADT}' x2='{vx(i):.1f}' y2='{PH}' "
                     f"stroke='#f1c40f' stroke-dasharray='4 3'/>")
    for i, a in enumerate(adj):
        xx = vx(i); up = a["c"] >= a["o"]; col = "#c00" if up else "#0a0"
        yo = y(a["o"]); yc = y(a["c"])
        s.append(f"<line x1='{xx:.1f}' y1='{y(a['h']):.1f}' x2='{xx:.1f}' y2='{y(a['l']):.1f}' stroke='{col}'/>")
        top = min(yo, yc)
        s.append(f"<rect x='{xx-bw/2:.1f}' y='{top:.1f}' width='{bw:.1f}' "
                 f"height='{max(1,abs(yc-yo)):.1f}' fill='{col}'/>")
    s.append(f"<text x='{L}' y='{VTOP-12}' fill='#666'>成交量(股, 本地不复权原始值)</text>")
    for i, a in enumerate(adj):
        xx = vx(i); up = a["c"] >= a["o"]; col = "#c00" if up else "#0a0"
        vh = a["v"] / vmax * VH
        s.append(f"<rect x='{xx-bw/2:.1f}' y='{VTOP+VH-vh:.1f}' width='{bw:.1f}' "
                 f"height='{vh:.1f}' fill='{col}' opacity='0.75'/>")
    s.append("</svg>")
    return "".join(s)


def compare_svg(adj, exdates):
    N = len(adj)
    W = 1000; L = 58; R = 18; PW = W - L - R
    lo = min(min(a["l"] for a in adj), min(a["raw_c"] for a in adj))
    hi = max(max(a["h"] for a in adj), max(a["raw_c"] for a in adj))
    if hi <= lo:
        hi = lo + 1
    lo -= (hi - lo) * 0.04; hi += (hi - lo) * 0.04

    def y(p):
        return 20 + (hi - p) / (hi - lo) * 270

    def vx(i):
        return L + (i + 0.5) / N * PW

    s = [f"<svg xmlns='http://www.w3.org/2000/svg' width='{W}' height='340' "
         f"viewBox='0 0 {W} 340' font-family='system-ui' font-size='11'>"
         f"<rect width='{W}' height='340' fill='#fff'/>"]
    for k in range(6):
        p = hi - (hi - lo) * k / 5; yy = y(p)
        s.append(f"<line x1='{L}' y1='{yy:.1f}' x2='{L+PW}' y2='{yy:.1f}' stroke='#eee'/>")
        s.append(f"<text x='{L-6}' y='{yy+3:.1f}' text-anchor='end' fill='#666'>{p:.2f}</text>")
    for i in range(0, N, max(1, N // 12)):
        d = adj[i]["date"]
        s.append(f"<text x='{vx(i):.1f}' y='322' text-anchor='middle' fill='#666'>"
                 f"{d%10000//100:02d}-{d%100:02d}</text>")

    def path(key):
        return "M" + " L".join(f"{vx(i):.1f},{y(a[key]):.1f}" for i, a in enumerate(adj))

    s.append(f"<path d='{path('raw_c')}' fill='none' stroke='#999' stroke-dasharray='5 3' stroke-width='1.2'/>")
    s.append(f"<path d='{path('c')}' fill='none' stroke='#c00' stroke-width='1.6'/>")
    exset = set(exdates or [])
    for i, a in enumerate(adj):
        if a["date"] in exset:
            s.append(f"<line x1='{vx(i):.1f}' y1='20' x2='{vx(i):.1f}' y2='310' stroke='#f1c40f' stroke-dasharray='4 3'/>")
    s.append(f"<text x='{L+4}' y='16' fill='#c00'>■ 复权收盘</text>")
    s.append(f"<text x='{L+110}' y='16' fill='#999'>┄ 不复权收盘</text>")
    s.append("</svg>")
    return "".join(s)


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="通达信 前复权/后复权 数据生成器（本地 gbbq 计算）")
    ap.add_argument("code", help="股票代码，如 600519 / sh600519")
    ap.add_argument("--mode", "-m", default="qfq", choices=["qfq", "hfq", "none"],
                    help="qfq=前复权(默认) / hfq=后复权 / none=不复权")
    ap.add_argument("--days", "-n", type=int, default=300, help="最近 N 个交易日")
    ap.add_argument("--source", default="local", choices=["local", "tencent"],
                    help="local=本机gbbq(默认) / tencent=腾讯qfq(仅 mode=qfq)")
    ap.add_argument("--csv", action="store_true", help="导出 CSV")
    ap.add_argument("--html", action="store_true", help="生成 HTML(含K线图)")
    ap.add_argument("--out", default="", help="输出目录(默认 当前目录/reports)")
    args = ap.parse_args()

    try:
        full, rows, K = load_adjusted(args.code, mode=args.mode,
                                      days=args.days, source=args.source)
    except Exception as e:
        print(f"[error] {e}", file=sys.stderr)
        sys.exit(1)

    label = {"qfq": "前复权", "hfq": "后复权", "none": "不复权"}[args.mode]
    print(f"股票 {full}  {label}(最近{args.days}日)  区间 {rows[0]['date']}→{rows[-1]['date']}"
          f"  来源={args.source}")
    if args.mode == "qfq":
        print(f"锚定校验: 最新日因子 = {rows[-1]['factor']:.6f} (应≈1.0，前复权末值=本地原始末值)")
    elif args.mode == "hfq":
        print(f"后复权累计因子 K = {K:.6f}（最新日 = 原始价 × K；首日 = 原始价 × 当日因子）")
    print(f"\n{label} 最上5行:")
    for a in rows[:5]:
        print(f"  {a['date']} O={a['o']:.2f} H={a['h']:.2f} L={a['l']:.2f} C={a['c']:.2f} "
              f"量={a['v']:.0f}股 因子={a['factor']:.4f}")
    print(f"{label} 最下5行:")
    for a in rows[-5:]:
        print(f"  {a['date']} O={a['o']:.2f} H={a['h']:.2f} L={a['l']:.2f} C={a['c']:.2f} "
              f"量={a['v']:.0f}股 因子={a['factor']:.4f}")

    out_dir = args.out or DEFAULT_OUT
    os.makedirs(out_dir, exist_ok=True)
    tag = f"{full}_{args.mode}_last{args.days}"

    if args.csv:
        import csv as _csv
        p = os.path.join(out_dir, tag + ".csv")
        with open(p, "w", newline="", encoding="utf-8-sig") as fp:
            w = _csv.writer(fp)
            w.writerow(["日期", "复权开盘", "复权最高", "复权最低", "复权收盘",
                        "原始成交量(股)", "原始成交额(元)", "原始收盘", "复权因子"])
            for a in rows:
                w.writerow([a["date"], f"{a['o']:.2f}", f"{a['h']:.2f}", f"{a['l']:.2f}",
                            f"{a['c']:.2f}", f"{a['v']:.0f}", f"{a['amt']:.0f}",
                            f"{a['raw_c']:.2f}", f"{a['factor']:.6f}"])
        print("CSV ->", os.path.abspath(p))

    if args.html:
        events = X.get_events(full) if args.source == "local" else []
        exdates = [e["date"] for e in events if rows[0]["date"] <= e["date"] <= rows[-1]["date"]]
        html = [
            "<html><head><meta charset='utf-8'><style>",
            "body{font-family:system-ui,'Microsoft YaHei',sans-serif;margin:28px;color:#222;max-width:1080px}",
            "h1{color:#b00}h2{color:#c0392b}",
            "table{border-collapse:collapse;font-size:13px}",
            "th,td{border:1px solid #ccc;padding:4px 8px;text-align:right}",
            "th{background:#f4f4f4}td:first-child,th:first-child{text-align:left}",
            ".note{background:#fff8e1;border-left:4px solid #f1c40f;padding:8px 12px;font-size:13px}",
            "svg{width:100%;max-width:1000px;height:auto;border:1px solid #eee}",
            "</style></head><body>",
        ]
        html.append(f"<h1>{full} · {label}（最近{args.days}日）</h1>")
        html.append("<div class='note'>原始价/量来自本机通达信 <code>vipdoc/.../lday/{}.day</code>；"
                    "{label}由本机 <code>T0002/hq_cache/gbbq</code> 除权除息事件按通达信标准公式本地计算。"
                    "复权仅作用于价格，成交量/成交额为原始值。{anchor}</div>".format(
                        full, label=label,
                        anchor=("最新日因子≈1（前复权末值=原始末值）" if args.mode == "qfq"
                                else f"后复权累计因子 K={K:.4f}")))
        html.append(f"<h2>{label} K线（黄线=除权除息日）</h2>" + candle_svg(rows, exdates, f"{full} {label}"))
        html.append("<h2>不复权 vs 复权 收盘对比</h2>" + compare_svg(rows, exdates))
        html.append(f"<h2>{label} 最上5行</h2><table><tr><th>日期</th><th>开</th><th>高</th><th>低</th>"
                    "<th>收</th><th>量(股)</th><th>原始收盘</th><th>因子</th></tr>")
        for a in rows[:5]:
            html.append(f"<tr><td>{a['date']}</td><td>{a['o']:.2f}</td><td>{a['h']:.2f}</td>"
                        f"<td>{a['l']:.2f}</td><td>{a['c']:.2f}</td><td>{a['v']:.0f}</td>"
                        f"<td>{a['raw_c']:.2f}</td><td>{a['factor']:.4f}</td></tr>")
        html.append("</table>")
        html.append(f"<h2>{label} 最下5行</h2><table><tr><th>日期</th><th>开</th><th>高</th><th>低</th>"
                    "<th>收</th><th>量(股)</th><th>原始收盘</th><th>因子</th></tr>")
        for a in rows[-5:]:
            html.append(f"<tr><td>{a['date']}</td><td>{a['o']:.2f}</td><td>{a['h']:.2f}</td>"
                        f"<td>{a['l']:.2f}</td><td>{a['c']:.2f}</td><td>{a['v']:.0f}</td>"
                        f"<td>{a['raw_c']:.2f}</td><td>{a['factor']:.4f}</td></tr>")
        html.append("</table></body></html>")
        hp = os.path.join(out_dir, tag + ".html")
        with open(hp, "w", encoding="utf-8") as fp:
            fp.write("".join(html))
        print("HTML ->", os.path.abspath(hp))


if __name__ == "__main__":
    main()
