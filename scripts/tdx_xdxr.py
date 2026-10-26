# -*- coding: utf-8 -*-
"""
通达信本地「除权除息(xdxr)」事件读取器 —— 复权计算的数据基础。
================================================================
数据源: {TDX_ROOT}/T0002/hq_cache/gbbq  （通达信「股本变迁」文件，加密）
  - 与通达信软件同源，是本机复权(前复权/后复权)的权威依据，无需联网。
  - gbbq 为加密二进制，解密算法移植自 pytdx（已逐条校验）。
  - 首次解析较慢（约 50~60s，19 万条）。解析结果会抽取为「category==1 除权除息」
    事件并缓存到 cw_cache/gbbq_xdxr.json；之后读取 < 0.1s。
  - 缓存按 gbbq 文件的 (mtime, size) 自动失效重建。

事件字段（category==1 除权除息）：
  date    除权除息日 (int YYYYMMDD)
  div     每股现金分红(税前, 元)      = 原始值 / 10
  bonus   每股送转股(股)             = 原始值 / 10
  rights  每股配股(股)               = 原始值 / 10
  rprice  配股价(元)

库用法：
  from tdx_xdxr import get_events
  ev = get_events("600519")   # -> [dict(date, div, bonus, rights, rprice), ...]

命令行：
  python tdx_xdxr.py 600519          # 打印该股全部除权除息事件
  python tdx_xdxr.py --rebuild       # 强制重建缓存
"""
import os
import sys
import json

HERE = os.path.dirname(os.path.abspath(__file__))
TDX_ROOT = os.environ.get("TDX_ROOT", r"C:\new_tdx64\new_tdx64")
GBBQ = os.path.join(TDX_ROOT, "T0002", "hq_cache", "gbbq")
CACHE_DIR = os.environ.get("TDX_FIN_CACHE", os.path.join(HERE, "cw_cache"))
CACHE = os.path.join(CACHE_DIR, "gbbq_xdxr.json")

# gbbq 内部 market 字节 -> 市场前缀
_MKT = {0: "sz", 1: "sh", 2: "bj"}

_EVENTS = None          # 进程内缓存: {full_code: [event, ...]}
_CACHE_META = None      # 记录缓存对应的 gbbq (mtime, size)


def _gbbq_stat(path):
    st = os.stat(path)
    return [round(st.st_mtime, 3), st.st_size]


def _full_code(code: str) -> str:
    """补全市场前缀（用 tdx_reader 的市场推断，带兜底）。"""
    c = code.strip().lower()
    if c.startswith(("sh", "sz", "bj")):
        return c
    try:
        sys.path.insert(0, HERE)
        from tdx_reader import _market_of
        return _market_of(c) + c
    except Exception:
        return "sh" + c


def _parse_gbbq(path):
    """解析加密 gbbq，返回 {full_code: [event,...]}（仅 category==1 除权除息）。"""
    from pytdx.reader.gbbq_reader import GbbqReader  # 延迟导入(重)
    df = GbbqReader().get_df(path)
    out = {}
    # 只取除权除息事件（category==1）
    sub = df[df["category"] == 1]
    for mkt, code, dt, div, rp, bon, rig in zip(
            sub["market"], sub["code"], sub["datetime"],
            sub["hongli_panqianliutong"], sub["peigujia_qianzongguben"],
            sub["songgu_qianzongguben"], sub["peigu_houzongguben"]):
        full = _MKT.get(int(mkt), "sh") + str(code)
        out.setdefault(full, []).append({
            "date": int(dt),
            "div": round(float(div) / 10.0, 6),
            "bonus": round(float(bon) / 10.0, 6),
            "rights": round(float(rig) / 10.0, 6),
            "rprice": round(float(rp), 6),
        })
    for k in out:
        out[k].sort(key=lambda e: e["date"])
    return out


def _load_cache_file():
    if not os.path.exists(CACHE):
        return None, None
    try:
        with open(CACHE, encoding="utf-8") as fh:
            obj = json.load(fh)
        return obj.get("events", {}), obj.get("meta")
    except Exception:
        return None, None


def ensure_cache(force=False, verbose=False):
    """确保事件缓存可用；gbbq 有更新或 force 时重建。返回 {full_code:[event]}。"""
    global _EVENTS, _CACHE_META
    if _EVENTS is not None and not force:
        return _EVENTS
    if not os.path.exists(GBBQ):
        raise FileNotFoundError(f"未找到 gbbq 文件: {GBBQ}（请确认 TDX_ROOT 是否正确）")
    meta = _gbbq_stat(GBBQ)
    events, cmeta = _load_cache_file()
    if (not force) and events is not None and cmeta == meta:
        _EVENTS, _CACHE_META = events, cmeta
        return _EVENTS
    if verbose:
        print(f"[xdxr] 重建缓存（解析 gbbq，约 1 分钟）…", file=sys.stderr)
    events = _parse_gbbq(GBBQ)
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(CACHE, "w", encoding="utf-8") as fh:
        json.dump({"meta": meta, "events": events}, fh, ensure_ascii=False)
    _EVENTS, _CACHE_META = events, meta
    return _EVENTS


def get_events(code: str, rebuild=False):
    """返回某只股票的除权除息事件列表（按日期升序）。code 可带/不带市场前缀。"""
    ev = ensure_cache(force=rebuild)
    return list(ev.get(_full_code(code), []))


def list_codes():
    """返回缓存中所有含除权除息事件的代码。"""
    return sorted(ensure_cache().keys())


def main():
    import argparse
    ap = argparse.ArgumentParser(description="通达信本地除权除息(xdxr)读取器")
    ap.add_argument("code", nargs="?", help="股票代码，如 600519")
    ap.add_argument("--rebuild", action="store_true", help="强制重建缓存")
    args = ap.parse_args()

    ev = ensure_cache(force=args.rebuild, verbose=True)
    if args.code:
        code = _full_code(args.code)
        items = ev.get(code, [])
        print(f"{code} 除权除息事件 {len(items)} 条：")
        for e in items:
            print(f"  {e['date']}  派现/股={e['div']:.4f}  送转/股={e['bonus']:.4f} "
                  f"配股/股={e['rights']:.4f}  配股价={e['rprice']:.4f}")
    else:
        print(f"缓存代码数={len(ev)}  事件总数={sum(len(v) for v in ev.values())}  -> {CACHE}")


if __name__ == "__main__":
    main()
