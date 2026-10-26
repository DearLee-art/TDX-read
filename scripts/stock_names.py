# -*- coding: utf-8 -*-
"""
股票名称 -> 代码 映射。
1) 内置一份「历史知名牛股/妖股」词典（覆盖常见提问场景）；
2) 扫描本机 T0002/recentbreed.dat 提取你近期接触过的股票名；
3) 支持精确 / 包含匹配。
"""
import os
import re
import sys

# 路径（与 tdx_reader 保持一致）
sys.path.insert(0, os.path.dirname(__file__))
from tdx_reader import TDX_ROOT  # noqa

# ---- 内置：历史知名牛股 / 妖股 / 各阶段龙头（名称: 代码）----
BUILTIN = {
    # 1990s~2007 老牌长牛
    "四川长虹": "sh600839", "深发展A": "sz000001", "万科A": "sz000002",
    "深科技": "sz000021", "中关村": "sz000931", "亿安科技": "sz000008",
    "银广夏": "sz000557", "东方电子": "sz000682", "哈医药": "sh600664",
    "上海石化": "sh600688", "青岛海尔": "sh600690", "广电电子": "sh600602",
    # 2005-2007 大牛市
    "中国船舶": "sh600150", "中信证券": "sh600030", "中国平安": "sh601318",
    "招商银行": "sh600036", "贵州茅台": "sh600519", "苏宁电器": "sz002024",
    "驰宏锌锗": "sh600497", "泸州老窖": "sz000568", "吉林敖东": "sz000623",
    "辽宁成大": "sh600739", "江西铜业": "sh600362", "山东黄金": "sh600547",
    "中金黄金": "sh600489", "保利地产": "sh600048", "泛海建设": "sz000046",
    "长江电力": "sh600900", "大秦铁路": "sh601006", "工商银行": "sh601398",
    # 2009-2010 反弹 + 题材
    "四环生物": "sz000518", "莱茵生物": "sz002166", "甲流": "sz000518",
    "包钢稀土": "sh600111", "广晟有色": "sh600259", "成飞集成": "sz002190",
    "太原刚玉": "sz000795", "壹桥苗业": "sz002447", "联环药业": "sh600513",
    # 2013-2015 创业板牛市 / 杠杆牛
    "乐视网": "sz300104", "暴风科技": "sz300431", "全通教育": "sz300359",
    "安硕信息": "sz300380", "银之杰": "sz300085", "同花顺": "sz300033",
    "东方财富": "sz300059", "万达信息": "sz300168", "朗玛信息": "sz300288",
    "上海钢联": "sz300226", "奋达科技": "sz002681", "中国中车": "sh601766",
    "中国神车": "sh601766", "特力A": "sz000025", "梅雁吉祥": "sh600868",
    "协鑫集成": "sz002506", "世纪游轮": "sz002558", "潜能恒信": "sz300191",
    "海欣食品": "sz002702", "光力科技": "sz300480", "鲍斯股份": "sz300441",
    "锦江投资": "sh600650", "锦江系": "sh600650", "际华集团": "sh601718",
    "洛阳玻璃": "sh600876", "巨人网络": "sz002558", "七喜控股": "sz002027",
    # 2016-2018 白马 / 价值
    "格力电器": "sz000651", "美的集团": "sz000333", "海康威视": "sz002415",
    "恒瑞医药": "sh600276", "中国平安": "sh601318", "招商银行": "sh600036",
    "五粮液": "sz000858", "伊利股份": "sh600887", "隆基绿能": "sh601012",
    "亨通光电": "sh600487", "方大炭素": "sh600516", "京东方A": "sz000725",
    "科大讯飞": "sz002230", "华友钴业": "sh603799", "天齐锂业": "sz002466",
    # 2018-2019 5G 妖王
    "东方通信": "sh600776", "东信和平": "sz002017", "南京熊猫": "sh600775",
    "风范股份": "sh601700", "通产丽星": "sz002243", "市北高新": "sh600604",
    "顺灏股份": "sz002565", "大智慧": "sh601519", "中信建投": "sh601066",
    "人民网": "sh603000", "工业富联": "sh601138", "沪电股份": "sz002463",
    "闻泰科技": "sh600745", "韦尔股份": "sh603501", "北京君正": "sz300223",
    # 2020 疫情 / 新能源
    "英科医疗": "sz300677", "九安医疗": "sz002432", "道恩股份": "sz002838",
    "未名医药": "sz002581", "振德医疗": "sh603301", "阳普医疗": "sz300030",
    "宁德时代": "sz300750", "比亚迪": "sz002594", "亿纬锂能": "sz300014",
    "阳光电源": "sz300274", "长城汽车": "sh601633", "赣锋锂业": "sz002460",
    "通威股份": "sh600438", "隆基股份": "sh601012", "酒鬼酒": "sz000799",
    "山西汾酒": "sh600809", "通策医疗": "sh600763", "片仔癀": "sh600436",
    # 2021 周期 / 题材
    "湖北宜化": "sz000422", "联创股份": "sz300343", "合盛硅业": "sh603260",
    "石大胜华": "sh603026", "江特电机": "sz002176", "西藏矿业": "sz000762",
    "中远海控": "sh601919", "包钢股份": "sh600010", "北方稀土": "sh600111",
    "广宇发展": "sz000537", "凤凰光学": "sh600071", "文山电力": "sh600995",
    "拓新药业": "sz301089", "小康股份": "sh601127", "鞍重股份": "sz002667",
    # 2021-2022 基建 / 妖股
    "浙江建投": "sz002761", "建艺集团": "sz002789", "天保基建": "sz000965",
    "中交地产": "sz000736", "湖南发展": "sz000722", "中通客车": "sz000957",
    "新华制药": "sz000756", "海汽集团": "sh603069", "赣能股份": "sz000899",
    "竞业达": "sz003005", "众生药业": "sz002317", "西安饮食": "sz000721",
    "安奈儿": "sz002875", "人人乐": "sz002336", "通润装备": "sz002150",
    # 2023-2024 AI / 算力 / 妖股
    "剑桥科技": "sh603083", "鸿博股份": "sz002229", "中际旭创": "sz300308",
    "昆仑万维": "sz300418", "万兴科技": "sz300624", "寒武纪": "sh688256",
    "佰维存储": "sh688525", "联特科技": "sz301205", "上海电影": "sh601595",
    "杭州热电": "sh605011", "捷荣技术": "sz002855", "圣龙股份": "sh603178",
    "天龙股份": "sh603266", "高新发展": "sz000628", "中文在线": "sz300364",
    "因赛集团": "sz300781", "克来机电": "sh603960", "维海德": "sz301318",
    "艾艾精工": "sh603580", "正丹股份": "sz300641", "大众交通": "sh600611",
    "金龙汽车": "sh600686", "深圳华强": "sz000062", "常山北明": "sz000158",
    # 沪深300/指数
    "上证指数": "sh000001", "深证成指": "sz399001", "创业板指": "sz399006",
    "沪深300": "sh000300", "上证50": "sh000016", "科创50": "sh000688",
}


def _scan_infoharbor():
    """扫描 T0002/hq_cache/infoharbor_ex.code (GBK): 全市场代码->名称对照。
    格式: 代码|名称|拼音|...  （5579 条，覆盖全部 A/京/基/指）"""
    out = {}
    p = os.path.join(TDX_ROOT, "T0002", "hq_cache", "infoharbor_ex.code")
    if not os.path.exists(p):
        return out
    try:
        data = open(p, "rb").read().decode("gbk", "ignore")
    except Exception:
        return out
    for line in data.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("|")
        if len(parts) < 2:
            continue
        code = parts[0].strip()
        name = parts[1].strip()
        if re.fullmatch(r"\d{6}", code) and name:
            out.setdefault(code, name)
    return out


def _scan_recentbreed():
    """扫描 T0002/recentbreed.dat 提取 (代码, 名称) 候选对（尽力而为）"""
    out = {}
    p = os.path.join(TDX_ROOT, "T0002", "recentbreed.dat")
    if not os.path.exists(p):
        return out
    try:
        data = open(p, "rb").read()
    except Exception:
        return out
    # 在原始字节里找: 6位ASCII数字 之后(可能带填充) 出现>=2个汉字(GBK)
    # 逐位置扫描
    for m in re.finditer(rb"(\d{6})", data):
        code = m.group(1).decode()
        start = m.end()
        # 向后最多 60 字节寻找 GBK 中文串
        seg = data[start:start + 60]
        # 解码 GBK，截取到首个不可读处
        name = ""
        try:
            txt = seg.decode("gbk", "ignore")
            # 取开头连续中文字符
            for ch in txt:
                if "\u4e00" <= ch <= "\u9fff":
                    name += ch
                else:
                    if name:
                        break
        except Exception:
            name = ""
        if len(name) >= 2:
            out.setdefault(code, name)
    return out


_local = _scan_recentbreed()  # 模块加载时扫描一次
_infoharbor = _scan_infoharbor()  # 全市场 代码->名称


def _code_to_name():
    """反向: 代码 -> 名称（优先级: 内置 > 全市场infoharbor > 本地recentbreed）"""
    m = {}
    for code, nm in _local.items():          # 本地接触过的最次
        m.setdefault(code, nm)
    for code, nm in _infoharbor.items():     # 全市场名称表
        m.setdefault(code, nm)
    for nm, code in BUILTIN.items():         # 内置牛股词典最高优先
        m.setdefault(code, nm)
    return m


CODE2NAME = _code_to_name()


def code_to_name(code: str):
    """代码 -> 名称。接受 6 位或带市场前缀(如 sh600519)。未知返回原代码。"""
    if code is None:
        return None
    q = str(code).strip()
    if not q:
        return q
    low = q.lower()
    if not low.startswith(("sh", "sz", "bj")):
        try:
            from tdx_reader import resolve_path
            full, _ = resolve_path(low)
        except Exception:
            full = low
    else:
        full = low
    return CODE2NAME.get(full) or CODE2NAME.get(low) or q


def name_to_code(name: str):
    """名称 -> 代码（含市场前缀，优先内置牛股词典）。未命中/歧义返回 None。
    歧义时可通过 search() 获取 'MULTI:...' 明细。"""
    if name is None:
        return None
    code, resolved = search(str(name))
    if code:
        return code
    return None


def search(query: str):
    """
    将用户输入解析为通达信代码。
    返回 (code, name) 或 (None, None)。
    """
    q = query.strip()
    if not q:
        return None, None
    # 1) 直接是代码
    low = q.lower()
    if re.fullmatch(r"(sh|sz|bj)?\d{6}", low):
        from tdx_reader import resolve_path
        full, _ = resolve_path(low)
        return full, CODE2NAME.get(full, full)
    # 2) 精确名称
    if q in BUILTIN:
        return BUILTIN[q], q
    # 3) 本地扫描命中名称
    rev = {v: k for k, v in _local.items()}
    if q in rev:
        return rev[q], q
    # 4) 包含匹配（内置）
    hits = [nm for nm in BUILTIN if q in nm]
    if len(hits) == 1:
        return BUILTIN[hits[0]], hits[0]
    if len(hits) > 1:
        return None, "MULTI:" + ",".join(hits)
    # 5) 包含匹配（本地）
    hits2 = [nm for nm in set(_local.values()) if q in nm]
    if len(hits2) == 1:
        code = [c for c, n in _local.items() if n == hits2[0]][0]
        return code, hits2[0]
    if len(hits2) > 1:
        return None, "MULTI:" + ",".join(hits2)
    return None, None


if __name__ == "__main__":
    for q in ["东方通信", "600776", "sh600776", "九安医疗", "茅台", "特力A"]:
        print(q, "->", search(q))
    print("本地扫描到名称数:", len(_local))
