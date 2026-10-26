# -*- coding: utf-8 -*-
"""
纯 SVG 图表渲染（无第三方依赖，离线可用）。
约定：A股配色 红=涨 绿=跌。
"""
import math


def _mapx(i, n, padL, padR, W):
    if n <= 1:
        return padL
    return padL + i * (W - padL - padR) / (n - 1)


def _scale(v, lo, hi, padT, padB, H, log):
    if log:
        lv = math.log(v) if v > 0 else math.log(max(lo, 1e-9))
        llo = math.log(lo) if lo > 0 else math.log(1e-9)
        lhi = math.log(hi) if hi > 0 else math.log(1e-9)
        if lhi == llo:
            return padT + (H - padT - padB) / 2
        return padT + (1 - (lv - llo) / (lhi - llo)) * (H - padT - padB)
    if hi == lo:
        return padT + (H - padT - padB) / 2
    return padT + (1 - (v - lo) / (hi - lo)) * (H - padT - padB)


def _fmt_date(d):
    s = str(int(d))
    return f"{s[4:6]}-{s[6:8]}"


def _fmt_price(v):
    if v >= 1000:
        return f"{v:.0f}"
    if v >= 100:
        return f"{v:.0f}"
    return f"{v:.2f}"


def overview(dates, close, ma20, ma60, volumes, launches, title="", log_auto=True):
    """价格(上)+成交量(下)。volumes: list[float]。launches: list[dict with 'i','max_gain','fwd60']。"""
    n = len(close)
    W, H = 1000, 560
    padL, padR, padT, padB = 58, 14, 18, 30
    priceH = 384
    volTop = priceH + 44
    volH = H - volTop - padB

    lo, hi = min(close), max(close)
    log = (log_auto and hi / max(lo, 1e-9) > 8)
    # 价格 y 范围留白
    if log:
        ylo = lo * 0.92
        yhi = hi * 1.08
    else:
        ylo = lo - (hi - lo) * 0.06
        yhi = hi + (hi - lo) * 0.06

    vmax = max(volumes) if volumes else 1

    def yp(v):
        return _scale(v, ylo, yhi, padT, 0, priceH, log)  # padT relative within price area

    # 注意：_scale 用整体高度，这里价格区单独映射
    def yprice(v):
        if log:
            lv = math.log(v); llo = math.log(ylo); lhi = math.log(yhi)
            return padT + (1 - (lv - llo) / (lhi - llo)) * priceH
        return padT + (1 - (v - ylo) / (yhi - ylo)) * priceH

    def yvol(v):
        return volTop + (1 - v / vmax) * volH

    def xx(i):
        return _mapx(i, n, padL, padR, W)

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
             f'font-family="Segoe UI,Microsoft YaHei,sans-serif" font-size="11">']
    # 背景
    parts.append(f'<rect x="0" y="0" width="{W}" height="{H}" fill="#ffffff"/>')
    # 网格 + 价格刻度
    gridN = 5
    for g in range(gridN + 1):
        if log:
            frac = g / gridN
            val = math.exp(math.log(ylo) + frac * (math.log(yhi) - math.log(ylo)))
        else:
            val = ylo + g / gridN * (yhi - ylo)
        yy = yprice(val)
        parts.append(f'<line x1="{padL}" y1="{yy:.1f}" x2="{W-padR}" y2="{yy:.1f}" stroke="#eef0f3"/>')
        parts.append(f'<text x="{padL-6}" y="{yy+3:.1f}" text-anchor="end" fill="#8a93a6">{_fmt_price(val)}</text>')
    # 标题
    if title:
        parts.append(f'<text x="{padL}" y="13" fill="#1f2733" font-size="13" font-weight="600">{title}</text>')
    # MA20 / MA60
    def poly(arr, color, wdt):
        pts = []
        for i, v in enumerate(arr):
            if v is None:
                continue
            pts.append(f"{xx(i):.1f},{yprice(v):.1f}")
        if pts:
            parts.append(f'<polyline fill="none" stroke="{color}" stroke-width="{wdt}" points="{" ".join(pts)}"/>')
    poly(ma60, "#f0a020", 1.2)
    poly(ma20, "#2e7be0", 1.4)
    # 收盘线
    cpts = " ".join(f"{xx(i):.1f},{yprice(close[i]):.1f}" for i in range(n))
    parts.append(f'<polyline fill="none" stroke="#3a3f4b" stroke-width="1.1" points="{cpts}"/>')
    # 成交量柱
    bw = max(0.6, (W - padL - padR) / n * 0.7)
    launch_idx = {r["i"] for r in launches}
    for i in range(n):
        v = volumes[i]
        col = "#e7556b" if i in launch_idx else "#c9d2e0"
        yy = yvol(v)
        parts.append(f'<rect x="{xx(i)-bw/2:.1f}" y="{yy:.1f}" width="{bw:.1f}" height="{volTop+volH-yy:.1f}" fill="{col}" opacity="0.8"/>')
    parts.append(f'<text x="{padL}" y="{volTop-6}" fill="#8a93a6">成交量(手)</text>')
    # 启动点标记
    for r in launches:
        i = r["i"]
        x = xx(i); y = yprice(close[i])
        if r.get("fwd60", 0) >= 0.5:
            col = "#e23b3b"   # 主升浪
        elif r.get("fwd60", 0) >= 0.15:
            col = "#f0902a"   # 波段
        else:
            col = "#9aa3b2"   # 失败
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="{col}" stroke="#fff" stroke-width="1.2"/>')
        parts.append(f'<line x1="{x:.1f}" y1="{y-7:.1f}" x2="{x:.1f}" y2="{y-16:.1f}" stroke="{col}" stroke-width="1"/>')
    # x 轴日期
    ticks = 6
    for t in range(ticks + 1):
        i = int(t / ticks * (n - 1))
        x = xx(i)
        parts.append(f'<text x="{x:.1f}" y="{H-10}" text-anchor="middle" fill="#8a93a6">{_fmt_date(dates[i])}</text>')
    # 图例
    lx = W - 220
    parts.append(f'<text x="{lx}" y="13" fill="#2e7be0">— MA20</text>')
    parts.append(f'<text x="{lx+70}" y="13" fill="#f0a020">— MA60</text>')
    parts.append(f'<circle cx="{lx+150}" cy="9" r="4" fill="#e23b3b"/><text x="{lx+158}" y="13" fill="#e23b3b">主升</text>')
    parts.append(f'<circle cx="{lx+200}" cy="9" r="4" fill="#f0902a"/><text x="{lx+208}" y="13" fill="#f0902a">波段</text>')
    parts.append("</svg>")
    return "".join(parts)


def candle_svg(bars, launches_idx, title=""):
    """K线缩放图（±窗口）。bars: 子列表 Bar；launches_idx: set of index。"""
    n = len(bars)
    W, H = 1000, 460
    padL, padR, padT, padB = 56, 14, 18, 30
    priceH = 330
    volTop = priceH + 40
    volH = H - volTop - padB
    closes = [b.close for b in bars]
    hi = max(b.high for b in bars); lo = min(b.low for b in bars)
    ylo = lo - (hi - lo) * 0.08; yhi = hi + (hi - lo) * 0.08
    vmax = max(b.volume for b in bars) or 1

    def yprice(v):
        return padT + (1 - (v - ylo) / (yhi - ylo)) * priceH

    def yvol(v):
        return volTop + (1 - v / vmax) * volH

    def xx(i):
        return padL + (i + 0.5) * (W - padL - padR) / n

    bw = (W - padL - padR) / n * 0.66
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
             f'font-family="Segoe UI,Microsoft YaHei,sans-serif" font-size="11">']
    parts.append(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')
    for g in range(6):
        val = ylo + g / 5 * (yhi - ylo)
        yy = yprice(val)
        parts.append(f'<line x1="{padL}" y1="{yy:.1f}" x2="{W-padR}" y2="{yy:.1f}" stroke="#eef0f3"/>')
        parts.append(f'<text x="{padL-6}" y="{yy+3:.1f}" text-anchor="end" fill="#8a93a6">{_fmt_price(val)}</text>')
    if title:
        parts.append(f'<text x="{padL}" y="13" fill="#1f2733" font-size="13" font-weight="600">{title}</text>')
    for i, b in enumerate(bars):
        up = b.close >= b.open
        col = "#e23b3b" if up else "#1faa6a"
        x = xx(i)
        # 影线
        parts.append(f'<line x1="{x:.1f}" y1="{yprice(b.high):.1f}" x2="{x:.1f}" y2="{yprice(b.low):.1f}" stroke="{col}" stroke-width="1"/>')
        # 实体
        yo = yprice(b.open); yc = yprice(b.close)
        top = min(yo, yc); hgt = max(1.2, abs(yo - yc))
        parts.append(f'<rect x="{x-bw/2:.1f}" y="{top:.1f}" width="{bw:.1f}" height="{hgt:.1f}" fill="{col}"/>')
        # 量
        vcol = "#e7556b" if i in launches_idx else ("#e9b7c0" if up else "#a9d8c5")
        yy = yvol(b.volume)
        parts.append(f'<rect x="{x-bw/2:.1f}" y="{yy:.1f}" width="{bw:.1f}" height="{volTop+volH-yy:.1f}" fill="{vcol}" opacity="0.85"/>')
    # 启动点竖线
    for i in launches_idx:
        x = xx(i)
        parts.append(f'<line x1="{x:.1f}" y1="{padT}" x2="{x:.1f}" y2="{volTop+volH}" stroke="#e23b3b" stroke-width="1" stroke-dasharray="3 3"/>')
    parts.append("</svg>")
    return "".join(parts)
