# -*- coding: utf-8 -*-
"""
通达信本地数据读取器 (纯 Python，无第三方依赖，适配本机 C:\\new_tdx64\\new_tdx64)

数据格式要点（已实测验证）：
  - 日线文件: {vipdoc}/{sh|sz}/lday/{code}.day
  - 每条约 32 字节，字段依次为(小端)，对应 struct "<IIIIIfII":
        date   : int32  YYYYMMDD
        open   : int32  开盘价 *100
        high   : int32  最高价 *100
        low    : int32  最低价 *100
        close  : int32  收盘价 *100
        amount : float32 成交额，单位 元（注意是 float，不是 int！）
        volume : int32  成交量，单位 股（手 = volume/100）
        reserved: int32  保留
    * 开高低收读出来 /100 得元
    * amount 是 float32 原值(元)，不要 /100
    * volume 单位: 股（手 = volume/100）
  注意：早期版本误用 "<8i"(全 int32) 解析 amount，会得到错误成交额；本环境已实测修正为 "<IIIIIfII"。
"""
import os
import struct

# 通达信安装根目录（可改环境变量 TDX_ROOT 覆盖）
TDX_ROOT = os.environ.get("TDX_ROOT", r"C:\new_tdx64\new_tdx64")
VIPDOC = os.path.join(TDX_ROOT, "vipdoc")


class Bar:
    __slots__ = ("date", "open", "high", "low", "close", "amount", "volume")

    def __init__(self, date, o, h, l, c, amount, volume):
        self.date = date          # int YYYYMMDD
        self.open = o / 100.0
        self.high = h / 100.0
        self.low = l / 100.0
        self.close = c / 100.0
        self.amount = float(amount)   # 元
        self.volume = float(volume)   # 股

    @property
    def vol_hand(self):
        return self.volume / 100.0    # 手

    def __repr__(self):
        return f"<Bar {self.date} C={self.close:.2f} V={self.vol_hand:.0f}手>"


# 各市场代码前缀（尽量覆盖：股票/ETF/LOF/指数/可转债/B股/北交所）
_SZ_PREFIX = ("00", "30", "20", "12", "15", "16", "18", "39")   # 深市：主板/创业板/B股/转债/ETF/LOF/基金/指数
_SH_PREFIX = ("60", "68", "90", "11", "13", "10", "19",
              "50", "51", "52", "56", "58")                     # 沪市：主板/科创/B股/转债/债券/ETF/基金
_BJ_PREFIX = ("43", "83", "87", "88", "92")                     # 北交所


def _market_of(code: str) -> str:
    """根据代码推断市场前缀 sh/sz/bj（尽力而为；resolve_path 会跨市场兜底）。"""
    c = code.lower()
    if c.startswith(("sh", "sz", "bj")):
        return c[:2]
    # 北交所：4/8 开头 或 43/83/87/88/92 段
    if code[:2] in _BJ_PREFIX or code[:1] in ("4", "8"):
        return "bj"
    if code[:2] in _SZ_PREFIX:
        return "sz"
    if code[:2] in _SH_PREFIX:
        return "sh"
    return "sh"


def resolve_path(code: str):
    """返回 (完整代码, 日线文件路径)；找不到返回 (full, None)。
    文件命名规则为 {市场}{6位代码}.day，本函数会按“先推断市场、再跨市场兜底”解析，
    因此深市 ETF/LOF/指数(15/16/39 开头) 等也能正确读取。"""
    c = code.strip().lower()
    full = c if c.startswith(("sh", "sz", "bj")) else _market_of(c) + c
    mkt, num = full[:2], full[2:]
    order = [mkt] + [m for m in ("sh", "sz", "bj") if m != mkt]
    for m in order:
        p = os.path.join(VIPDOC, m, "lday", m + num + ".day")
        if os.path.exists(p):
            return m + num, p
    return full, None


def list_codes():
    """列出 vipdoc 下所有可读取的日线代码"""
    codes = []
    for mkt in ("sh", "sz", "bj"):
        d = os.path.join(VIPDOC, mkt, "lday")
        if os.path.isdir(d):
            for fn in os.listdir(d):
                if fn.endswith(".day"):
                    codes.append(fn[:-4])
    return sorted(codes)


def load_daily(code: str):
    """读取某只股票全部日线，返回 Bar 列表（按日期升序）"""
    full, path = resolve_path(code)
    if path is None:
        raise FileNotFoundError(f"未找到 {code} 的日线文件（已搜索 sh/sz/bj）")
    with open(path, "rb") as fh:
        data = fh.read()
    if len(data) % 32 != 0:
        # 文件被截断/损坏时给出明确提示，而不是静默错读
        raise ValueError(f"{path} 长度 {len(data)} 不是 32 的整数倍，日线文件可能损坏")
    n = len(data) // 32
    bars = []
    for i in range(n):
        d, o, h, l, c, amt, vol, _ = struct.unpack("<IIIIIfII", data[i * 32:(i + 1) * 32])
        bars.append(Bar(d, o, h, l, c, amt, vol))
    return bars


def date_str(d: int) -> str:
    s = str(d)
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}"


if __name__ == "__main__":
    b = load_daily("sh600519")
    print("茅台日线条数:", len(b))
    print("首:", b[0], "末:", b[-1])
