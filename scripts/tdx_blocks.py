# -*- coding: utf-8 -*-
"""
通达信自定义板块解读（只读，绝不写入 C:\\new_tdx64）。
数据位置: T0002/blocknew/
  - blocknew.cfg : 120字节/条, 存 (中文名 + 板块ID) 的自定义板块索引
  - <ID>.blk    : 文本, CRLF 分隔, 每行 = [市场位][6位代码]
  - <ID>.dat    : 二进制, 80字节/条, 每条含 6位代码(ASCII), 与 .blk 同内容(顺序可能不同)
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from tdx_reader import TDX_ROOT  # noqa

BLOCK_DIR = os.path.join(TDX_ROOT, "T0002", "blocknew")
CFG = os.path.join(BLOCK_DIR, "blocknew.cfg")


def parse_cfg(path=CFG):
    """返回 {板块ID: 中文名}"""
    out = {}
    if not os.path.exists(path):
        return out
    data = open(path, "rb").read()
    rec = 120
    n = len(data) // rec
    if n == 0:
        return out
    for i in range(0, n * rec, rec):
        chunk = data[i:i + rec]
        end = chunk.find(b"\x00")
        name = chunk[:end].decode("gbk", "ignore").strip() if end > 0 else ""
        m = re.search(rb"[A-Z0-9]{2,}", chunk)
        bid = m.group().decode() if m else ""
        if bid:
            out[bid] = name or bid
    return out


def _code_from_text_block(raw: bytes):
    """文本 .blk: 提取 6 位代码(取每行尾部6位数字)"""
    codes = []
    for line in raw.decode("gbk", "ignore").split():
        digits = re.sub(r"\D", "", line)
        if len(digits) >= 6:
            codes.append(digits[-6:])
    return codes


def _code_from_dat(raw: bytes):
    """二进制 .dat: 80字节/条, 每条找 6 位连续数字"""
    codes = []
    rec = 80
    if len(raw) % rec not in (0,):
        # 容错: 不确定记录长就全局扫描
        for m in re.finditer(rb"(\d{6})", raw):
            codes.append(m.group().decode())
        return codes
    for i in range(0, len(raw), rec):
        recb = raw[i:i + rec]
        m = re.search(rb"(\d{6})", recb)
        if m:
            codes.append(m.group().decode())
    return codes


def market_of(code):
    """市场推断：统一委托 tdx_reader._market_of（覆盖北交所/深市ETF等）。"""
    c = code.strip().lower()
    if c.startswith(("sh", "sz", "bj")):
        return c[:2]
    from tdx_reader import _market_of as _m
    return _m(c)


def full_code(code):
    return market_of(code) + code


def read_block_members(stem):
    """读取某板块的全部成员代码(去重, 优先 .blk)。返回 code 列表。"""
    blk = os.path.join(BLOCK_DIR, stem + ".blk")
    dat = os.path.join(BLOCK_DIR, stem + ".dat")
    codes = []
    if os.path.exists(blk) and os.path.getsize(blk) > 0:
        codes = _code_from_text_block(open(blk, "rb").read())
    if not codes and os.path.exists(dat) and os.path.getsize(dat) > 0:
        codes = _code_from_dat(open(dat, "rb").read())
    # 去重保序
    seen = set(); out = []
    for c in codes:
        if c in seen:
            continue
        seen.add(c); out.append(c)
    return out


# 常见指数/ETF 名称（板块里常混入指数代码）
INDEX_NAMES = {
    "000001": "上证指数", "999999": "上证指数", "000300": "沪深300",
    "000016": "上证50", "000688": "科创50", "000905": "中证500",
    "399001": "深证成指", "399006": "创业板指", "399005": "中小板指",
    "399106": "深证综指", "399673": "创业板50", "399300": "沪深300",
    "399330": "深证100", "000010": "上证180", "880001": "总市值",
}


def resolve_name(code):
    """反查股票名(尽力而为)"""
    if code in INDEX_NAMES:
        return INDEX_NAMES[code]
    from stock_names import CODE2NAME
    if code in CODE2NAME:
        return CODE2NAME[code]
    # 尝试 recentbreed 扫描结果已在 CODE2NAME 中, 兜底返回代码
    return ""


def load_all_blocks():
    """返回 list of dict: {id, name, custom, members:[code], named}"""
    cfg = parse_cfg()
    # 收集非空的 .blk / .dat stem
    stems = set()
    for f in os.listdir(BLOCK_DIR):
        if f.endswith(".blk") or f.endswith(".dat"):
            if os.path.getsize(os.path.join(BLOCK_DIR, f)) > 0:
                stems.add(f[:-4])
    blocks = []
    for stem in sorted(stems):
        members = read_block_members(stem)
        if not members:
            continue
        custom = stem in cfg
        blocks.append({
            "id": stem,
            "name": cfg.get(stem, stem),
            "custom": custom,
            "members": members,
        })
    return blocks, cfg


def parse_all():
    """解析全部自定义板块（只读）。返回 list of dict：{id,name,custom,members}。
    兼容 SKILL.md 中约定的 parse_all() 名称。"""
    blocks, _cfg = load_all_blocks()
    return blocks


if __name__ == "__main__":
    blocks, cfg = load_all_blocks()
    print(f"自定义板块索引(blocknew.cfg) 共 {len(cfg)} 个:")
    for k, v in cfg.items():
        print(f"  {v}  <{k}>")
    print(f"\n含成员的非空板块文件共 {len(blocks)} 个:\n")
    for b in blocks:
        tag = "自定义" if b["custom"] else "其他/系统"
        names = [f"{c}({resolve_name(c)})" for c in b["members"][:8]]
        print(f"● [{tag}] {b['name']} <{b['id']}>  成员 {len(b['members'])} 只")
        print("   ", ", ".join(names) + (" ..." if len(b["members"]) > 8 else ""))
