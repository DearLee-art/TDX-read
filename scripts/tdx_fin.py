# -*- coding: utf-8 -*-
"""
通达信专业财务数据 —— 通用读取工具
====================================
数据来源：通达信 gpcw 历史专业财务数据包（与软件同源），
          http://down.tdx.com.cn:8001/tdxfin/gpcw{YYYYMMDD}.zip
字段对照：tdx_fin_fields.json（通达信帮助中心 584 字段编号↔中文名）

特性：
- 输入股票代码 + 任意字段（中文名 / 编号 / col编号）即可取数，无需为每种数据重写。
- 自动区分「累计型科目」(利润表/现金流量表) 与「时点型科目」(资产负债表)：
    累计型 → 自动算【单季值】= 本期累计 − 同年前期累计
    时点型 → 直接取期末值
- 自动算【同比】(vs 去年同期同季) 与【环比】(vs 上一期)。
- 货币字段默认以「亿元」展示（÷1e8），可用 --unit 切换。

用法示例：
  python tdx_fin.py 300759 --fields 应收账款,营业收入,净利润 --recent 6
  python tdx_fin.py 300759 --fields 11,74,95 --periods 20251231,20260630 --html
  python tdx_fin.py 600519 --fields 营业收入 --recent 8 --html
"""
import os, sys, json, re, argparse, urllib.request, socket
from pytdx.reader import HistoryFinancialReader

HERE = os.path.dirname(os.path.abspath(__file__))
# 财务包缓存目录：默认脚本目录 cw_cache（字段 JSON 与下载的 gpcw*.zip 同处），
# 可用环境变量 TDX_FIN_CACHE 覆盖（如指向一个共享缓存盘）。
CACHE = os.environ.get("TDX_FIN_CACHE", os.path.join(HERE, "cw_cache"))
FIELDS_JSON = os.path.join(CACHE, "tdx_fin_fields.json")
_FALLBACK_LATEST = "20260630"   # 缓存目录为空时的兜底（本机曾验证有效）


def latest_cached_period():
    """自动探测：缓存目录里已下载的 gpcw{YYYYMMDD}.zip 中最新一期。
    避免硬编码过期（每季新报表发布后无需改代码）。"""
    if os.path.isdir(CACHE):
        ps = []
        for fn in os.listdir(CACHE):
            m = re.fullmatch(r"gpcw(\d{8})\.zip", fn)
            if m:
                ps.append(m.group(1))
        if ps:
            return max(ps)
    return _FALLBACK_LATEST


DEFAULT_LATEST = latest_cached_period()

# 科目大类：累计型（期间累计，可算单季） vs 时点型（期末值）
CUMULATIVE_CATS = {"利润表", "现金流量表"}
SINGLE_CATS = {"单季度财务指标"}   # 已是单季值

PREV_MD = {"0331": ("1231", True), "0630": ("0331", False),
           "0930": ("0630", False), "1231": ("0930", False)}


def load_fields():
    if not os.path.exists(FIELDS_JSON):
        return {}
    with open(FIELDS_JSON, encoding="utf-8") as f:
        lst = json.load(f)
    return {it["id"]: it for it in lst}


FIELDS = load_fields()

# 常用别名 → 字段编号（解决「净利润」等多处出现导致的歧义，优先命中主表科目）
ALIAS = {
    "营收": 74, "营业收入": 74, "收入": 74,
    "净利润": 95, "净利": 95, "利润": 95,
    "归母": 96, "归母净利润": 96, "归母净利": 96,
    "应收账款": 11, "应收": 11,
    "存货": 17,
    "货币资金": 8,
    "总资产": 40, "资产总计": 40, "资产": 40,
    "总负债": 63, "负债合计": 63, "负债": 63,
    "股东权益": 72, "净资产": 72, "权益": 72, "权益合计": 72,
    "经营现金流": 107, "经营现金流净额": 107, "经营活动现金流": 107, "经营活动现金流量净额": 107,
    "投资活动现金流": 119, "投资活动现金流量净额": 119,
    "筹资活动现金流": 128, "筹资活动现金流量净额": 128,
    "每股收益": 1, "基本每股收益": 1,
    "每股净资产": 4,
    "净资产收益率": 6, "roe": 6, "ROE": 6,
    "毛利率": 202, "销售毛利率": 202,
    "营收增长率": 183, "营业收入增长率": 183,
    "研发费用": 304,
    "单季营收": 230, "单季度营收": 230,
}


def resolve_field(token):
    """中文名 / 别名 / 编号 / col编号 → 字段编号 int"""
    t = str(token).strip()
    if t in ALIAS:
        return ALIAS[t]
    if t.lower().startswith("col"):
        t = t[3:]
    try:
        return int(t)
    except ValueError:
        pass
    for idx, it in FIELDS.items():
        if it["name"] == t:
            return idx
    hits = [idx for idx, it in FIELDS.items() if t in it["name"]]
    if len(hits) == 1:
        return hits[0]
    if hits:
        raise KeyError(f"字段名 '{t}' 命中多个：{[(h, FIELDS[h]['name']) for h in hits]}，请更精确或用编号")
    raise KeyError(f"无法解析字段：{token}（可试用编号，如 74=营业收入）")


def fetch_df(period, force=False):
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, f"gpcw{period}.zip")
    if force or not os.path.exists(p) or os.path.getsize(p) < 1000:
        socket.setdefaulttimeout(120)
        urllib.request.urlretrieve(
            f"http://down.tdx.com.cn:8001/tdxfin/gpcw{period}.zip", p)
    return HistoryFinancialReader().get_df(p)


def get_value(df, code, idx):
    return float(df.loc[str(code), f"col{idx}"])


def prev_quarter(period):
    y = int(period[:4]); md = period[4:]
    pm, back = PREV_MD[md]
    return f"{y-1 if back else y}{pm}"


def same_year_prior(period):
    y = int(period[:4]); md = period[4:]
    if md == "0331":
        return None
    return f"{y}{PREV_MD[md][0]}"


def prev_year_same(period):
    return f"{int(period[:4])-1}{period[4:]}"


def recent_periods(n, latest=DEFAULT_LATEST):
    seq, cur = [], latest
    for _ in range(n):
        seq.append(cur); cur = prev_quarter(cur)
    return list(reversed(seq))


def scale_for(idx, unit):
    """推断字段量纲：返回 (除数, 是否百分比, 小数位)。"""
    it = FIELDS.get(idx, {})
    name = it.get("name", "")
    cat = it.get("cat", "")
    if "(%)" in name:                      # 比率/百分比类
        return 1.0, True, 2
    if cat == "每股指标":                   # 元/股
        return 1.0, False, 4
    if "(万元)" in name:                    # 以万元计
        return 1e4, False, 2
    if unit == "yi":                        # 货币（元）→ 亿元
        return 1e8, False, 4
    if unit == "wan":                       # 货币 → 万元
        return 1e4, False, 2
    return 1.0, False, 2


def build_table(code, fields, periods, unit="yi"):
    """返回 list[dict]，每个 period 一行，含累计/单季/同比/环比。"""
    fidx = [resolve_field(f) for f in fields]
    _cache = {}
    def df_of(p):
        if p not in _cache:
            _cache[p] = fetch_df(p)
        return _cache[p]
    def val(p, idx):
        try:
            return get_value(df_of(p), code, idx)
        except Exception:
            return None

    rows = []
    prev_in_seq = None
    for p in periods:
        row = {"period": p}
        for idx in fidx:
            it = FIELDS.get(idx, {"cat": "?", "name": f"col{idx}"})
            cat, name = it["cat"], it["name"]
            div, is_pct, dec = scale_for(idx, unit)
            raw = val(p, idx)
            def sc(v):
                return None if v is None else v / div
            # 单季值 / 期末值
            if cat in CUMULATIVE_CATS:
                sp = same_year_prior(p)
                single = raw if (sp is None or raw is None) else (raw - val(sp, idx))
                row[f"{name}__cum"] = sc(raw)
                row[f"{name}__single"] = sc(single)
                disp = sc(single)
            elif cat in SINGLE_CATS:
                row[f"{name}__single"] = sc(raw)
                disp = sc(raw)
            else:  # 时点型
                row[f"{name}__point"] = sc(raw)
                disp = sc(raw)
            row[f"{name}__is_pct"] = is_pct
            row[f"{name}__dec"] = dec
            # 同比（vs 去年同期同季）
            py = prev_year_same(p)
            raw_py = val(py, idx)
            if raw_py is not None and disp is not None:
                if cat in CUMULATIVE_CATS:
                    sp_py = same_year_prior(py)
                    single_py = raw_py if sp_py is None else (raw_py - val(sp_py, idx))
                else:
                    single_py = raw_py
                row[f"{name}__yoy"] = _pct(disp, sc(single_py))
            else:
                row[f"{name}__yoy"] = None
            # 环比（vs 上一期）
            if prev_in_seq is not None:
                raw_pq = val(prev_in_seq, idx)
                if raw_pq is not None and disp is not None:
                    if cat in CUMULATIVE_CATS:
                        sp_pq = same_year_prior(prev_in_seq)
                        single_pq = raw_pq if sp_pq is None else (raw_pq - val(sp_pq, idx))
                    else:
                        single_pq = raw_pq
                    row[f"{name}__qoq"] = _pct(disp, sc(single_pq))
                else:
                    row[f"{name}__qoq"] = None
            else:
                row[f"{name}__qoq"] = None
            row[f"{name}__cat"] = cat
        prev_in_seq = p
        rows.append(row)
    return rows, fidx


def _pct(cur, base):
    if base is None or base == 0:
        return None
    return (cur - base) / abs(base) * 100.0


def fmt(v, is_pct=False, dec=4):
    if v is None:
        return "—"
    if is_pct:
        return f"{v:.{dec}f}%"
    return f"{v:,.{dec}f}"


def pctfmt(v):
    return "—" if v is None else f"{v:+.2f}%"


def make_html(code, fields, periods, rows, fidx, unit):
    names = [FIELDS.get(i, {"name": f"col{i}"})["name"] for i in fidx]
    # 判断每个字段展示类型
    def show_type(idx):
        cat = FIELDS.get(idx, {"cat": "?"})["cat"]
        if cat in CUMULATIVE_CATS:
            return "cum_single"
        if cat in SINGLE_CATS:
            return "single"
        return "point"
    html = ["<html><head><meta charset='utf-8'><style>",
            "body{font-family:system-ui,'Microsoft YaHei',sans-serif;margin:24px;color:#222}",
            "h2{color:#b00}h3{color:#333}table{border-collapse:collapse;font-size:13px;margin:8px 0 20px}",
            "th,td{border:1px solid #ccc;padding:4px 8px;text-align:right}",
            "th{background:#f0f0f0}td.lbl{text-align:left;font-weight:600}",
            ".pos{color:#c00}.neg{color:#0a0}.note{color:#666;font-size:12px}",
            "</style></head><body>"]
    html.append(f"<h2>通达信财务数据 · {code}</h2>")
    html.append(f"<div class='note'>数据：gpcw 历史专业财务数据包（与通达信同源）｜量纲自动识别：货币→亿元、每股指标→元/股、比率→%。｜"
                f"累计型科目(利润表/现金流量表)自动列【单季值】=本期累计−同年前期累计；时点型(资产负债表)列期末值。</div>")
    # 一表一字段
    for idx, name in zip(fidx, names):
        st = show_type(idx)
        html.append(f"<h3>{name}（{FIELDS.get(idx,{'cat':'?'})['cat']}）</h3>")
        html.append("<table><tr><th>报告期</th>")
        if st == "cum_single":
            html.append("<th>累计值</th><th>单季值</th><th>同比</th><th>环比</th>")
        elif st == "single":
            html.append("<th>单季值</th><th>同比</th><th>环比</th>")
        else:
            html.append("<th>期末值</th><th>同比</th><th>环比</th>")
        html.append("</tr>")
        for r in rows:
            ip = r.get(name + "__is_pct", False)
            dc = r.get(name + "__dec", 4)
            html.append(f"<tr><td class='lbl'>{r['period']}</td>")
            if st == "cum_single":
                html.append(f"<td>{fmt(r.get(name+'__cum'),ip,dc)}</td>")
                html.append(f"<td>{fmt(r.get(name+'__single'),ip,dc)}</td>")
            elif st == "single":
                html.append(f"<td>{fmt(r.get(name+'__single'),ip,dc)}</td>")
            else:
                html.append(f"<td>{fmt(r.get(name+'__point'),ip,dc)}</td>")
            yoy = r.get(name+"__yoy"); qoq = r.get(name+"__qoq")
            html.append(_cell(yoy)); html.append(_cell(qoq))
            html.append("</tr>")
        html.append("</table>")
    html.append("<div class='note'>同比 = 本期单季/期末值 ÷ 去年同期 − 1；环比 = 本期 ÷ 上一期 − 1。</div>")
    html.append("</body></html>")
    return "".join(html)


def _cell(v):
    s = pctfmt(v)
    cls = "pos" if (v is not None and v > 0) else ("neg" if (v is not None and v < 0) else "")
    return f"<td class='{cls}'>{s}</td>"


def main():
    ap = argparse.ArgumentParser(description="通达信通用财务读取工具")
    ap.add_argument("code", help="股票代码，如 300759")
    ap.add_argument("--fields", "-f", required=True,
                    help="字段，逗号分隔：中文名/编号/col编号，如 '应收账款,营业收入,净利润' 或 '11,74,95'")
    ap.add_argument("--recent", "-r", type=int, default=0, help="取最近 N 个季度末（含最新）")
    ap.add_argument("--periods", "-p", default="", help="显式报告期，逗号分隔，如 20251231,20260630")
    ap.add_argument("--unit", "-u", default="yi", choices=["yi", "wan", "yuan"], help="货币单位")
    ap.add_argument("--html", action="store_true", help="生成 HTML 报告到当前工作目录/reports/")
    ap.add_argument("--out", default="", help="输出目录（默认 当前工作目录/reports/）")
    args = ap.parse_args()

    fields = [x.strip() for x in args.fields.split(",") if x.strip()]
    if args.periods:
        periods = [x.strip() for x in args.periods.split(",") if x.strip()]
    else:
        periods = recent_periods(args.recent or 6)

    rows, fidx = build_table(args.code, fields, periods, args.unit)

    # 控制台
    hdr = ["报告期"] + [FIELDS.get(i, {"name": f"col{i}"})["name"] for i in fidx]
    print("  ".join(h.ljust(20) for h in hdr))
    for r in rows:
        cells = []
        for idx in fidx:
            nm = FIELDS.get(idx, {"name": f"col{idx}"})["name"]
            cat = FIELDS.get(idx, {"cat": "?"})["cat"]
            ip = r.get(nm + "__is_pct", False)
            dc = r.get(nm + "__dec", 4)
            if cat in CUMULATIVE_CATS:
                cells.append(f"{fmt(r[nm+'__single'],ip,dc)}(单)/{pctfmt(r[nm+'__yoy'])}")
            elif cat in SINGLE_CATS:
                cells.append(f"{fmt(r[nm+'__single'],ip,dc)}/{pctfmt(r[nm+'__yoy'])}")
            else:
                cells.append(f"{fmt(r[nm+'__point'],ip,dc)}/{pctfmt(r[nm+'__yoy'])}")
        print(str(r["period"]).ljust(10), "  ".join(c.ljust(20) for c in cells))

    if args.html:
        out_dir = args.out or os.path.join(os.getcwd(), "reports")
        os.makedirs(out_dir, exist_ok=True)
        out = os.path.join(out_dir, f"tdx_fin_{args.code}.html")
        with open(out, "w", encoding="utf-8") as f:
            f.write(make_html(args.code, fields, periods, rows, fidx, args.unit))
        print("HTML ->", os.path.abspath(out))


if __name__ == "__main__":
    main()
