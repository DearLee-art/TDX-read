# -*- coding: utf-8 -*-
"""
通达信本地「股本结构」读取器 —— 取流通股本(流通A股)，用于换手率计算。

数据源： {TDX_ROOT}/T0002/hq_cache/base.dbf
  - 纯 Python 解析 dBase III 头部 + 字段描述符，无第三方依赖。
  - 关键字段： GPDM(代码) / ZGB(总股本,万股) / LTAG(流通A股,万股)
  - 单位： 万股 (1 字段值 = 10000 股)。已用 600519(茅台)/000001(平安) 反查验证。

换手率口径（已验证）：
  换手率% = 成交量(股) / 流通股本(股) * 100
          = volume_shares / (LTAG_万股 * 10000) * 100
"""
import os
import struct

TDX_ROOT = os.environ.get("TDX_ROOT", r"C:\new_tdx64\new_tdx64")
BASE_DBF = os.path.join(TDX_ROOT, "T0002", "hq_cache", "base.dbf")

# base.dbf 字段（顺序/长度已实测；与文件内描述符一致）
_FIELDS = [
    ("SC", "C", 1), ("GPDM", "C", 6), ("GXRQ", "N", 8), ("ZGB", "N", 14),
    ("GJG", "N", 14), ("FQRFRG", "N", 14), ("FRG", "N", 14), ("BG", "N", 14),
    ("HG", "N", 14), ("LTAG", "N", 14), ("ZGG", "N", 14), ("ZPG", "N", 14),
    ("ZZC", "N", 14), ("LDZC", "N", 14), ("GDZC", "N", 14), ("WXZC", "N", 14),
    ("CQTZ", "N", 14), ("LDFZ", "N", 14), ("CQFZ", "N", 14), ("ZBGJJ", "N", 14),
    ("JZC", "N", 14), ("ZYSY", "N", 14), ("ZYLY", "N", 14), ("QTLY", "N", 14),
    ("YYLY", "N", 14), ("TZSY", "N", 14), ("BTSY", "N", 14), ("YYWSZ", "N", 14),
    ("SNSYTZ", "N", 14), ("LYZE", "N", 14), ("SHLY", "N", 14), ("JLY", "N", 14),
    ("WFPLY", "N", 14), ("TZMGJZ", "N", 14), ("DY", "C", 3), ("HY", "C", 4),
    ("ZBNB", "N", 2), ("SSDATE", "C", 8), ("MODIDATE", "C", 6), ("GDRS", "N", 8),
]


def _load():
    with open(BASE_DBF, "rb") as fh:
        data = fh.read()
    # 解析字段描述符，得到真实头部长度
    off = 32
    nfields = 0
    while True:
        d = data[off:off + 32]
        if d[0] == 0x0D:
            break
        nfields += 1
        off += 32
    hlen = off + 1                      # 跳过 0x0D 终止符
    datalen = sum(f[2] for f in _FIELDS)
    rlen = datalen + 1                  # +1 删除标志字节
    # 与 DBF 头部声明的记录长度(bytes 10-11)交叉校验；不一致则以头部为准(仅当更大=尾部填充)
    declared_rlen = struct.unpack("<H", data[10:12])[0]
    if declared_rlen > rlen:
        rlen = declared_rlen
    # 建立字段偏移
    pos = 1
    omap = {}
    for name, typ, length in _FIELDS:
        omap[name] = (pos, typ, length)
        pos += length
    return data, hlen, rlen, omap


def _decode(rec, omap, name):
    p, typ, length = omap[name]
    v = rec[p:p + length]
    if typ == "N":
        s = v.decode("gbk", "ignore").strip()
        try:
            return float(s) if s not in ("", ".", "-") else None
        except ValueError:
            return None
    return v.decode("gbk", "ignore").strip()


_SHARES = None   # 进程内缓存: {6位代码: (流通股本_股, 总股本_股)}


def _build_all():
    """一次性解析整个 base.dbf，返回 {代码: (流通股本, 总股本)}（单位: 股）。"""
    global _SHARES
    if _SHARES is not None:
        return _SHARES
    data, hlen, rlen, omap = _load()
    nrec = (len(data) - hlen) // rlen
    m = {}
    for i in range(nrec):
        base = hlen + i * rlen
        rec = data[base:base + rlen]
        if rec[0] == 0x2A:           # 删除标记 '*'
            continue
        gpdm = _decode(rec, omap, "GPDM")
        if not gpdm:
            continue
        ltag = _decode(rec, omap, "LTAG")   # 流通A股，万股
        zgb = _decode(rec, omap, "ZGB")     # 总股本，万股
        m[gpdm] = ((ltag * 10000.0) if ltag is not None else None,
                   (zgb * 10000.0) if zgb is not None else None)
    _SHARES = m
    return m


def get_shares_map():
    """返回 {6位代码: (流通股本_股, 总股本_股)} 全表（批量选股时可直接查表，避免重复 I/O）。"""
    return _build_all()


def get_float_shares(code: str):
    """返回 (流通股本_股, 总股本_股)；单位已换算为「股」。找不到返回 (None, None)。
    内部对 base.dbf 只解析一次（进程级缓存），批量调用不再重复读盘。"""
    c = code.strip().lower()
    if c.startswith(("sh", "sz", "bj")):
        c = c[2:]
    return _build_all().get(c, (None, None))


if __name__ == "__main__":
    import sys
    c = sys.argv[1] if len(sys.argv) > 1 else "600513"
    f, t = get_float_shares(c)
    print(f"{c}: 流通股本={f/1e8:.4f}亿股  总股本={t/1e8:.4f}亿股" if f else f"{c}: 未找到")
