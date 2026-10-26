# TDX-read

读取通达信（TDX）本地数据的工具集，封装成一个可直接被 AI Agent 调用的 skill。

数据全部来自**本机安装的通达信**（`vipdoc`、`T0002/hq_cache`），不抓网页、不依赖第三方行情 API，离线可用。输出为控制台表格、CSV、HTML 报告或 K 线 PNG。

## 能力

| 脚本 | 能力 | 说明 |
|---|---|---|
| `tdx_reader.py` | 日线 K 线价量 | 解析 `vipdoc/{sh,sz}/lday/*.day`，价格已换算为元 |
| `tdx_adjust.py` | 前复权 / 后复权 | 用本机 `gbbq` 除权事件本地计算，前后严格自洽 |
| `tdx_xdxr.py` | 除权除息事件 | 解析加密的 `gbbq`，抽取派现/送转/配股 |
| `tdx_fin.py` | 财务数据（584 字段） | 营收、净利润、应收账款等，累计/单季/同比/环比 |
| `tdx_industry.py` | 所属行业 | 二级行业名称 + 行业指数代码 |
| `tdx_blocks.py` | 自定义板块 | 只读解析 `T0002/blocknew/` |
| `tdx_float.py` | 流通股本 | 解析 `base.dbf`，换手率分母 |
| `tdx_indicators.py` | 技术指标 | MA 斜率、均线粘合度、量比、换手率、涨停次数、60 日新高 |
| `stock_names.py` | 代码 ↔ 名称 | 含 ST 判定 |
| `chart_stock.py` | K 线图 | PNG，涨红跌绿 + MA10/30/60 + 成交量 |
| `chart.py` | 纯 SVG 图 | 无第三方依赖 |
| `tdx_qfq.py` | 兼容壳 | 转发到 `tdx_adjust.py --mode qfq` |

## 前置条件

1. **Windows 本机已安装通达信**，且至少下载过一次盘后数据（`vipdoc` 目录非空）。
2. **Python 3.8+**。
3. 可选依赖：`pytdx`（`tdx_fin.py` 与 `tdx_xdxr.py` 首次建缓存时用）、`matplotlib`（`chart_stock.py` 画图用）。

```bash
pip install pytdx matplotlib
```

通达信默认装在 `C:\new_tdx64\new_tdx64`。装在别处就用环境变量指定：

```bash
export TDX_ROOT="D:/tdx"
```

## 安装为 skill

```bash
git clone https://github.com/DearLee-art/TDX-read.git ~/.workbuddy/skills/tdx-data-reader
```

**目录名必须是 `tdx-data-reader`**（与 `SKILL.md` 里 front matter 的 `name` 一致）。装好后新开一个会话即可调用。

`SKILL.md` 里示例路径含 `<用户名>` 占位符，指当前 Windows 账户名，使用前替换成实际值。

## 快速开始

```bash
# 财务：近 6 个季度营收/净利润/应收账款，生成 HTML 报告
python scripts/tdx_fin.py 300759 --fields 应收账款,营业收入,净利润 --recent 6 --html

# 前复权行情：最近 300 天，输出 CSV + HTML
python scripts/tdx_adjust.py 600519 --mode qfq --days 300 --csv --html

# 技术指标：最近 250 个交易日，输出 CSV
python scripts/tdx_indicators.py 600513 --days 250 --out reports/600513_indicators.csv

# K 线图
python scripts/chart_stock.py 300759 160 --out reports
```

作为库调用：

```python
from tdx_reader import load_daily
from tdx_adjust import load_adjusted
from tdx_industry import get_industry

bars = load_daily("300759")                          # open/high/low/close 单位元
full, rows, K = load_adjusted("600519", mode="qfq")  # 前复权序列
get_industry("300759")                               # '医疗研发外包'
```

输出默认落在**当前工作目录**的 `reports/`，可用 `--out` 覆盖。

## 复权口径

通达信 `lday/*.day` 只存**不复权原始价**，`fzline/` 复权线通常为空，所以复权由本工具本地计算：

```
k   = P0 / ((P0 − 每股派现 + 配股×配股价) / (1 + 送转 + 配股))
cf(t) = ∏_{除权日 ≤ t} k
后复权 = 原始价 × cf        前复权 = 原始价 × cf / K      (K = ∏ 全部 k)
```

满足 `后复权 = 前复权 × K`，首日前后严格对齐。近端已与腾讯 qfq 逐日核对（600519 偏差 0.000%）；越早的历史，各数据商对“现金分红是否复投”的口径不同，本工具遵循通达信标准公式。成交量与成交额不做复权，另给 `factor` 列自行换算。

## 缓存（不入库）

| 路径 | 大小 | 来源 | 是否提交 |
|---|---|---|---|
| `scripts/cw_cache/tdx_fin_fields.json` | 35 KB | 字段名↔编号对照表 | ✅ 已提交，必需 |
| `scripts/cw_cache/gbbq_xdxr.json` | ~5 MB | 首次解析 `gbbq` 生成，约 1 分钟 | ❌ 自动重建 |
| `scripts/cw_cache/gpcw*.zip` | ~250 MB | 从通达信服务器下载的财务数据包 | ❌ 自动下载 |

缓存目录可用 `TDX_FIN_CACHE` 覆盖。仓库不携带这些缓存，第一次跑财务/复权会慢一点，之后秒读。

## 目录结构

```
TDX-read/
├── SKILL.md                    # skill 定义（front matter + 使用手册）
└── scripts/
    ├── *.py                    # 12 个工具脚本
    └── cw_cache/
        └── tdx_fin_fields.json # 财务字段对照表
```

## 免责声明

- 仅读取本机已有数据，不做任何写入；`tdx_blocks.py` 对板块文件为只读。
- 数据准确性取决于通达信官方数据源与本地数据完整度，本工具不保证行情可用于实盘决策。
- 仅供研究与技术学习，**不构成投资建议**。

## License

MIT
