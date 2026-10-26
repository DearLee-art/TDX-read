# -*- coding: utf-8 -*-
"""
个股K线图生成器（楚云风判读用图）
- 蜡烛图(涨红跌绿, A股惯例) + MA10/MA30/MA60 + 成交量
- 叠加判读关键位(可选): 提示线(突破位) / 初始止损 / 起涨点 / 近期高点
  关键位依赖楚云风策略层 cyf_screen.evaluate；缺失时仅画纯 K 线 + MA
- 输出 PNG 到 当前工作目录/reports/（可用 --out DIR 覆盖）
用法: python chart_stock.py <6位代码> [显示天数] [--out DIR]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib import font_manager

from tdx_reader import load_daily, date_str

# 判读关键位（楚云风策略层 cyf_screen）为可选增强：缺失时仅画纯 K 线 + MA
try:
    from cyf_screen import evaluate
except Exception:
    evaluate = None

REPORTS = os.path.join(os.getcwd(), "reports")  # 默认输出到当前工作目录


def setup_font():
    cands = [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
    ]
    for f in cands:
        if os.path.exists(f):
            try:
                font_manager.fontManager.addfont(f)
                name = font_manager.FontProperties(fname=f).get_name()
                plt.rcParams["font.family"] = name
                return
            except Exception:
                pass
    plt.rcParams["font.family"] = "DejaVu Sans"


def sma(vals, n):
    out = []
    for i in range(len(vals)):
        if i + 1 < n:
            out.append(None)
        else:
            out.append(sum(vals[i + 1 - n:i + 1]) / n)
    return out


def candle(ax, bars):
    for i, b in enumerate(bars):
        up = b.close >= b.open
        col = "#d8392b" if up else "#1a9d4b"   # 涨红 / 跌绿
        # 影线
        ax.plot([i, i], [b.low, b.high], color=col, linewidth=0.7, zorder=1)
        # 实体
        body_low = min(b.open, b.close)
        body_h = abs(b.close - b.open)
        if body_h < 1e-9:
            body_h = 0.001
        ax.add_patch(Rectangle((i - 0.4, body_low), 0.8, body_h,
                               facecolor=col, edgecolor=col, zorder=2))


def main():
    argv = sys.argv[1:]
    out_dir = None
    if "--out" in argv:
        i = argv.index("--out")
        out_dir = argv[i + 1] if i + 1 < len(argv) else None
        del argv[i:i + 2]
    code = argv[0] if argv else "300759"
    ndays = int(argv[1]) if len(argv) > 1 else 160
    reports = out_dir or os.path.join(os.getcwd(), "reports")

    try:
        bars = load_daily(code)
    except Exception as e:
        print("读取失败:", e)
        return
    r = evaluate(code) if evaluate else None

    N = min(len(bars), ndays)
    view = bars[-N:]
    closes = [b.close for b in bars]
    ma10 = sma(closes, 10)[-N:]
    ma30 = sma(closes, 30)[-N:]
    ma60 = sma(closes, 60)[-N:]

    setup_font()
    plt.rcParams["axes.unicode_minus"] = False

    fig = plt.figure(figsize=(15, 8))
    axp = fig.add_axes([0.07, 0.30, 0.88, 0.58])
    axv = fig.add_axes([0.07, 0.06, 0.88, 0.18], sharex=axp)

    # 买入区间(半透明): 首笔试探仓区(7%约束内) + 次笔主力仓区(突破提示线附近)
    if r:
        probe_lo, probe_hi = r["init_stop"], r["init_stop"] / 0.93
        add_lo, add_hi = r["hint"], r["hint"] * 1.03
        axp.axhspan(probe_lo, probe_hi, color="#16a34a", alpha=0.13, zorder=0)
        axp.axhspan(add_lo, add_hi, color="#1d4ed8", alpha=0.13, zorder=0)
        axp.text(0.5, (probe_lo + probe_hi) / 2, "首笔试探仓区 (1/2)", color="#15803d",
                 fontsize=9, va="center", fontweight="bold")
        axp.text(0.5, (add_lo + add_hi) / 2, "次笔主力仓区 (1/2)", color="#1e40af",
                 fontsize=9, va="center", fontweight="bold")

    candle(axp, view)
    xs = list(range(N))
    axp.plot(xs, ma10, color="#f2a900", linewidth=1.1, label="MA10")
    axp.plot(xs, ma30, color="#2b6cd8", linewidth=1.1, label="MA30")
    axp.plot(xs, ma60, color="#7a4fd8", linewidth=1.1, label="MA60")

    # 成交量
    vmax = max((b.volume for b in view), default=1)
    for i, b in enumerate(view):
        col = "#d8392b" if b.close >= b.open else "#1a9d4b"
        axv.bar(i, b.volume / vmax * 100, color=col, width=0.8)
    axv.set_ylabel("量(归一%)", fontsize=9)
    axv.set_ylim(0, 105)

    # 关键位标注
    if r:
        hints = [
            (r["hint"], "#027a48", "提示线(反弹高点) {:.2f}".format(r["hint"])),
            (r["init_stop"], "#b42318", "初始止损 {:.2f}".format(r["init_stop"])),
            (r["launch_low"], "#b54708", "起涨点 {:.2f}".format(r["launch_low"])),
            (r["peak"], "#1a56db", "近期高点(第一波顶) {:.2f}".format(r["peak"])),
        ]
        for y, c, lab in hints:
            axp.axhline(y, color=c, linestyle="--", linewidth=1.0, alpha=0.9)
            axp.text(N - 1, y, " " + lab, color=c, fontsize=9,
                     va="center", ha="right")

        # 当前价位置 + 观望区/持仓区 提示箭头
        cx = N - 1
        probe_hi2 = r["init_stop"] / 0.93
        zone = ("试探仓区" if r["close"] <= probe_hi2
                else "主力仓区(突破)" if r["close"] >= r["hint"]
                else "观望区")
        axp.scatter([cx], [r["close"]], color="#374151", s=26, zorder=6, marker="D")
        axp.axhline(r["close"], color="#6b7280", linestyle=":", linewidth=0.9, alpha=0.7)
        xtext = max(2, cx - 44)
        yspan = axp.get_ylim()[1] - axp.get_ylim()[0]
        axp.annotate("当前 {:.2f} · {}".format(r["close"], zone),
                     xy=(cx, r["close"]),
                     xytext=(xtext, r["close"] + yspan * 0.03),
                     fontsize=9, color="#374151",
                     arrowprops=dict(arrowstyle="->", color="#374151", lw=0.9))

    # X 轴日期刻度
    step = max(1, N // 10)
    ticks, labels = [], []
    for i in range(0, N, step):
        ticks.append(i)
        labels.append(date_str(view[i].date))
    axp.set_xticks(ticks)
    axp.set_xticklabels(labels, rotation=0, fontsize=9)
    axp.set_ylim(min(b.low for b in view) * 0.97,
                 max(b.high for b in view) * 1.03)

    name = (r["name"] if r else None) or code
    title = "{} ({}) K线".format(name, code)
    if r:
        probe_hi = r["init_stop"] / 0.93
        sub = ("收盘 {:.2f} ｜ 起涨 +{:.0f}% ｜ 回撤 {:.1f}% ｜ 缩量比 {:.2f} ｜ 评分 {}\n"
               "买区: 首试探 {:.2f}–{:.2f} ｜ 次主力 >提示线 {:.2f}（初始止损 {:.2f}）").format(
            r["close"], r["rise_pct"] * 100, r["pullback"] * 100, r["vol_ratio"], r["score"],
            r["init_stop"], probe_hi, r["hint"], r["init_stop"])
        title += " · 强势股回调判读\n" + sub
    axp.set_title(title, fontsize=13, fontweight="bold")
    axp.legend(loc="upper left", fontsize=9)
    axp.grid(True, alpha=0.25)
    axv.grid(True, alpha=0.25)

    os.makedirs(reports, exist_ok=True)
    out = os.path.join(reports, "kline_{}.png".format(code))
    fig.savefig(out, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print("K线图已写出:", out)


if __name__ == "__main__":
    main()
