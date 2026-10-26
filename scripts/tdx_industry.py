# -*- coding: utf-8 -*-
"""
通达信二级行业 映射 (只读, 解析本机 TDX 数据)。
链路: T0002/hq_cache/tdxhy.cfg  股票代码 -> X行业码
      T0002/hq_cache/tdxzs3.cfg X行业码 -> (二级行业名称, 881xxx行业指数代码)
join key = X码 (如 X1303 / X400401)。
"""
import os
import re

from tdx_reader import TDX_ROOT

HC = os.path.join(TDX_ROOT, "T0002", "hq_cache")
_MAP = None


def build_map():
    """返回 (code2x, x2ind)"""
    code2x = {}
    p = os.path.join(HC, "tdxhy.cfg")
    if os.path.exists(p):
        for line in open(p, "rb").read().decode("gbk", "ignore").splitlines():
            f = line.split("|")
            if len(f) >= 6 and re.fullmatch(r"\d{6}", f[1]):
                code2x[f[1]] = f[5].strip()
    x2ind = {}
    p2 = os.path.join(HC, "tdxzs3.cfg")
    if os.path.exists(p2):
        for line in open(p2, "rb").read().decode("gbk", "ignore").splitlines():
            f = line.split("|")
            if len(f) >= 6:
                x2ind[f[5].strip()] = (f[0].strip(), f[1].strip())
    return code2x, x2ind


def get_industry(code):
    """返回 二级行业名称 (如 'PCB'); 未知返回 '' """
    global _MAP
    if _MAP is None:
        _MAP = build_map()
    code2x, x2ind = _MAP
    x = code2x.get(code, "")
    if not x:
        return ""
    return x2ind.get(x, ("", ""))[0]


def get_industry_full(code):
    """返回 (二级行业名称, 881xxx行业指数代码)"""
    global _MAP
    if _MAP is None:
        _MAP = build_map()
    code2x, x2ind = _MAP
    x = code2x.get(code, "")
    if not x:
        return ("", "")
    return x2ind.get(x, ("", ""))


if __name__ == "__main__":
    for c in ["603995", "688002", "300759", "603228", "600256"]:
        print(c, get_industry_full(c))
