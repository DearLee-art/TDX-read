---
name: tdx-data-reader
description: 读取本机通达信（TDX）本地数据的通用工具集。当用户需要从通达信读取「K线价量、前复权/后复权行情、股票所属行业、财务数据（营收/净利润/应收账款/增幅等任意584字段）、自定义板块、流通股本、技术指标、代码↔名称、生成K线图」时使用。覆盖场景关键词：通达信、TDX、K线、日线、股价、成交量、前复权、后复权、复权、除权除息、回测、所属行业、财务数据、营业收入、净利润、应收账款、每股收益、毛利率、营收增长率、板块、股票名称、画K线图。该 skill 为纯数据读取层，不依赖任何具体分析策略，可在任意 workspace（空间）直接加载即用。
---

# 通达信本地数据读取器（tdx-data-reader）

从本机安装的通达信读取行情、行业、财务、板块等数据。**与具体选股/判读策略无关**，可在任意 workspace 复用。所有数据均来自固定目录 `TDX_ROOT`（默认 `C:\new_tdx64\new_tdx64`），脚本本身不依赖调用方项目。

## 一、环境约定（重要，务必遵守）

- **路径占位符**：下文示例中的 `<用户名>` 指当前 Windows 账户名（Git Bash 可用 `echo $USERNAME` 查看），使用前替换为实际值；路径一律用 Windows 盘符格式 `C:/Users/...`，不要用 `/c/...`。
- **TDX 根目录**：默认 `C:\new_tdx64\new_tdx64`，可用环境变量 `TDX_ROOT` 覆盖（如其他盘符安装）。
- **Python 运行环境**：使用托管 venv  
  `C:/Users/<用户名>/.workbuddy/binaries/python/envs/default/Scripts/python.exe`  
  该 venv 需安装 `pytdx`（财务工具 `tdx_fin.py` 与除权除息解析 `tdx_xdxr.py` 首建缓存时依赖）：  
  `C:/Users/<用户名>/.workbuddy/binaries/python/envs/default/Scripts/pip install pytdx`
- **路径格式**：传给 python 的路径用 **Windows 盘符路径**（`C:/...` 或 `C:\...`），**不要用** Git Bash 的 `/c/...`（原生 Windows python 不识别）。
- **网络**：仅 `tdx_fin.py`（财务数据，下载 `gpcw{YYYYMMDD}.zip`）与复权核对源（`--source tencent`，可选）  
  需要联网，运行 Bash 时加 `dangerouslyDisableSandbox=true`。**复权计算（默认 local）完全离线。**
- **除权除息缓存**：复权事件来自本机 `T0002/hq_cache/gbbq`，首次解析较慢（约 1 分钟）并缓存到  
  `scripts/cw_cache/gbbq_xdxr.json`，之后秒读；gbbq 更新时按 (mtime,size) 自动重建。
- **输出目录**：脚本默认把 HTML/PNG 输出到**当前工作目录**下的 `reports/`（即调用时所在的 workspace），可用 `--out DIR` 覆盖。

## 二、能力清单与调用示例

脚本位于本 skill 的 `scripts/` 目录。推荐调用方式：用 venv 的 `python.exe` 直接运行脚本的**绝对路径**，并把工作目录（cwd）设在目标 workspace，输出即落到该 workspace 的 `reports/`。

### 1) 财务数据（最常用）—— `tdx_fin.py`

通用工具：输入「股票代码 + 任意字段（中文名/编号）」即可出 **累计 / 单季 / 同比 / 环比**，无需为每种数据重写。

```bash
PY="C:/Users/<用户名>/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
SCR="C:/Users/<用户名>/.workbuddy/skills/tdx-data-reader/scripts/tdx_fin.py"

# 近 6 个季度：应收账款 + 营业收入 + 净利润（控制台）
"$PY" "$SCR" 300759 --fields 应收账款,营业收入,净利润 --recent 6

# 生成 HTML 报告（落到当前 workspace 的 reports/）
"$PY" "$SCR" 300759 --fields 应收账款,营业收入,净利润,经营现金流 --recent 6 --html

# 显式指定报告期 + 换股票（如贵州茅台）
"$PY" "$SCR" 600519 --fields 毛利率,ROE,经营现金流 --recent 8 --html

# 直接用字段编号（11=应收账款, 74=营收, 95=净利, 96=归母, 230=单季营收）
"$PY" "$SCR" 300759 --fields 11,74,95 --periods 20251231,20260630 --html
```

### 2) K线价量（库）—— `tdx_reader.py`

```python
from tdx_reader import load_daily, date_str
bars = load_daily("300759")          # 返回 Bar 列表（open/high/low/close 已 /100 为元, volume 单位为股）
print(len(bars), date_str(bars[-1].date), bars[-1].close)
# 涨红跌绿取数约定；手 = volume/100
```

### 3) 股票所属行业 —— `tdx_industry.py`

```python
from tdx_industry import get_industry, get_industry_full
print(get_industry("300759"))        # -> '医疗研发外包'（二级行业名称；未知返回 ''）
print(get_industry_full("300759"))   # -> ('医疗研发外包', '881249')  (名称, 行业指数代码)
```

### 4) 自定义板块（只读）—— `tdx_blocks.py`

```python
import tdx_blocks as tb
blocks = tb.parse_all()              # 解析 T0002/blocknew/ 下全部板块与成员
for b in blocks:
    print(b["name"], b["id"], len(b["members"]))
```

### 5) 代码 ↔ 名称 —— `stock_names.py`

```python
from stock_names import name_to_code, code_to_name
code = name_to_code("康龙化成")       # -> '300759'
name = code_to_name("300759")        # -> '康龙化成'
```

### 6) K线图（PNG）—— `chart_stock.py`

涨红跌绿 + MA10/30/60 + 成交量；若同目录存在 `cyf_screen.evaluate` 会叠加判读关键位，缺失则只画纯 K 线。

```bash
"$PY" "$SCR" 300759 160 --out "C:/path/to/workspace/reports"
# 输出 kline_300759.png
```

### 7) 复权行情（前复权 / 后复权）—— `tdx_adjust.py`

通达信本机 `vipdoc/{mkt}/lday/*.day` **只存不复权原始价**，复权缓存 `fzline/` 通常为空。  
做收益/回测必须用复权价。本工具**依本机数据本地计算**前复权与后复权，离线、确定、前后自洽。

```bash
PY="C:/Users/<用户名>/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
ADJ="C:/Users/<用户名>/.workbuddy/skills/tdx-data-reader/scripts/tdx_adjust.py"

"$PY" "$ADJ" 600519 --mode qfq --days 300 --csv --html     # 前复权(默认)
"$PY" "$ADJ" 300750 --mode hfq --days 300 --csv --html     # 后复权
"$PY" "$ADJ" 600519 --mode qfq --source tencent --days 60  # 与券商口径核对(仅 qfq, 联网)
```

Python 库用法（推荐）：

```python
from tdx_adjust import load_adjusted
full, rows, K = load_adjusted("600519", mode="qfq", days=250)   # rows: list[dict]
# row: {date, o,h,l,c(复权), v(原始股), amt(原始元), raw_c(原始收盘), factor, src}
```

- **口径**：对本机 `T0002/hq_cache/gbbq` 的每个除权除息事件，按通达信标准公式算事件因子  
  `k = P0 / ((P0 - 每股派现 + 配股×配股价) / (1 + 送转 + 配股))`；  
  累计因子 `cf(t)=∏_{除权日≤t} k`；**后复权 = 原始价×cf**（首日≈原始价），  
  **前复权 = 原始价×cf/K**（K=∏全部k，末日=原始价）。二者满足 `后复权 = 前复权 × K`，严格自洽。
- **精度**：前复权最近区间与券商/腾讯 qfq 逐日吻合（实测 600519 偏差 0.000%）；越早的历史，  
  各数据商对「现金分红是否复投」口径不同会有差异，本工具遵循**通达信标准公式**。
- **只复权价格**：成交量 / 成交额保持本地原始值（列 `factor` 供自行换算）。
- 输出：控制台 top/bottom5；`--csv` 写 `reports/{code}_{qfq|hfq}_lastN.csv`；`--html` 写带 K 线 + 不复权对比图的 HTML。
- 首次运行会解析 `gbbq`（约 1 分钟）并缓存到 `cw_cache/gbbq_xdxr.json`（之后秒读；gbbq 更新时自动重建）。
- 旧入口 `tdx_qfq.py` 仍可用（转发到 `tdx_adjust.py --mode qfq`；`--exdates` 已废弃）。

### 7b) 除权除息(xdxr)事件 —— `tdx_xdxr.py`

复权计算的底层数据：解析本机加密 `gbbq`，抽取「除权除息」事件（派现/送转/配股/配股价）。

```python
from tdx_xdxr import get_events
ev = get_events("600519")   # -> [dict(date, div, bonus, rights, rprice), ...]
```

```bash
"$PY" "C:/Users/<用户名>/.workbuddy/skills/tdx-data-reader/scripts/tdx_xdxr.py" 600519   # 打印事件
"$PY" "C:/Users/<用户名>/.workbuddy/skills/tdx-data-reader/scripts/tdx_xdxr.py" --rebuild # 强制重建缓存
```

### 8) 流通股本（换手率分母）—— `tdx_float.py`

纯 Python 解析 `{TDX_ROOT}/T0002/hq_cache/base.dbf`（dBase 头部 + 字段描述符，无第三方依赖）。  
关键字段：`GPDM`(代码) / `ZGB`(总股本,万股) / `LTAG`(流通A股,万股)；单位**万股**，已用 600519(茅台)/000001(平安) 反查验证。

```bash
"$PY" "C:/Users/<用户名>/.workbuddy/skills/tdx-data-reader/scripts/tdx_float.py" 600513
# 输出: 600513: 流通股本=2.8546亿股  总股本=2.8546亿股
```

- 换手率口径（已实测验证）：`换手率% = 成交量(股) / 流通股本(股) × 100 = volume / (LTAG×10000) × 100`。  
  例：600513 单日 4563.36万手 ÷ 2.8546亿股 ≈ 15.99%，与公开行情一致。

### 9) 技术指标（MA斜率/粘合度/量比/换手率/涨停/新高）—— `tdx_indicators.py`

纯 Python，依赖同目录 `tdx_reader.py` / `tdx_float.py` / `stock_names.py`（判定 ST）。计算最近 N 个交易日（默认 250）的逐日指标，输出 CSV。  
（`base.dbf` 在本进程内只解析一次，批量选股可直接用 `tdx_float.get_shares_map()` 查表。）

```bash
"$PY" "C:/Users/<用户名>/.workbuddy/skills/tdx-data-reader/scripts/tdx_indicators.py" 600513 --days 250 --out "reports/600513_indicators_250.csv"
```

输出列：`date, close, vol_hand, amount_wan, turnover_pct, MA5, MA10, MA20, MA60, MA120,
slope_MA5, slope_MA10, slope_MA20, slope_MA60, slope_MA120, ma_convergence_pct, volume_ratio,
turnover_20avg_pct, limitup_60_count, newhigh_60_break`

口径约定（已在脚本内实现并验证）：

- **MA 斜率**：对「该均线自身的序列」做最小二乘回归，输出 `%/天`（`b / 均值 × 100`）；窗口 = 均线周期。
- **均线粘合度** `ma_convergence_pct` = `(max−min)/均值 × 100`，越小越粘合（含 MA5/10/20/60/120）。
- **量比** `volume_ratio` = 当日成交量 / 前 5 个交易日平均成交量。
- **20日平均换手率** = 最近 20 日每日换手率的均值。
- **60日涨停次数** `limitup_60_count`：按板块判定涨停幅度（主板10% / 主板ST 5% / 双创20% / 北交所含920段30%），  
  涨停价按交易所口径**四舍五入到分**（非银行家舍入），精确判定 `收盘价==涨停价 且 封板(收≈高)`；统计最近 60 日（含当日）封板天数。
- **性能**：MA/斜率/涨停统计均为 O(n) 级实现，全量 5600+ 日约 1.2s（旧版约 7.8s）。
- **60日新高突破** `newhigh_60_break`：当日收盘 > 前 60 日最高收盘 记为 1，否则 0。

## 三、复权口径与财务字段要点（写给工具用，避免踩坑）

### 复权（前复权 / 后复权）

- **数据基础**：本机 `T0002/hq_cache/gbbq`（加密，除权除息事件）+ `vipdoc/.../lday/*.day`（不复权原始价）。  
  `fzline/` 复权线通常为空，故复权**由本工具本地计算**，不依赖外部源。
- **因子**：`k = P0 / ((P0 − 每股派现 + 配股×配股价) / (1 + 送转 + 配股))`（P0=除权日前收盘）；  
  `cf(t)=∏_{除权日≤t}k`；`后复权=原始价×cf`，`前复权=原始价×cf/K`（K=∏全部k）。二者关系 `hfq=qfq×K`。
- **常见误区**：
  - 不要把 `复权` 用到财务数据上（`tdx_fin.py` 无复权概念）。
  - 成交量/成交额不随价格复权（本工具保留原始值，另给 `factor` 列）。
  - 不同数据商对「现金分红是否复投」口径不同，早期历史数值可能不一致；本工具遵循**通达信标准公式**，  
    前复权与腾讯 qfq 在近期逐日吻合，且前/后复权严格自洽。

### 财务字段

- **字段来源**：`gpcw` 历史专业财务数据包（与通达信软件同源），列 `col1…col584` 对应通达信「专业财务数据」编号。字段名↔编号对照见 `scripts/cw_cache/tdx_fin_fields.json`。
- **常用别名**（已内置，直接写中文即可）：  
  `营业收入=74`、`净利润=95`、`归母净利润=96`、`应收账款=11`、`存货=17`、`货币资金=8`、`经营现金流=107`、`每股收益=1`、`每股净资产=4`、`ROE=6`、`毛利率=202`、`营收增长率=183`。
- **单季算法**：累计型科目（利润表/现金流量表）= 本期累计 − 同年前期累计；Q1 单季=累计。时点型（资产负债表/每股指标）无单季，列期末值。
- **量纲自动识别**：货币类→亿元、比率/百分比（名称含 `%`）→%、每股指标→元/股。**不要把比率当货币÷1亿**（早期 bug）。
- **口径**：季报/中报/三季报为**年初至报告期累计值**；年报即全年（本格式年报营收正常，无"营收只存Q1"坑）。
- **缓存**：已下载的 `gpcw*.zip` 缓存在 `CACHE`（默认脚本目录 `cw_cache`，可用环境变量 `TDX_FIN_CACHE` 覆盖）。`--recent` 的默认最新期会自动取缓存内最新一期。

## 四、与其他空间的协作

1. 在新 workspace 对话中提到「读取 300759 财务 / 画 K线 / 取前复权或后复权」→ 本 skill 被加载；
2. 按上面示例运行脚本，读的是**本机通达信数据**，输出落到该 workspace 的 `reports/`；
3. 验证：在任意 workspace 跑 `tdx_fin.py 300759 --fields 营收,净利 --recent 6`，结果与本机一致；  
   复权验证：`tdx_adjust.py 600519 --mode qfq --days 30` 的最末日因子应 =1.0。

> 维护提示：本 skill 可随时增删脚本或扩充字段别名；修改后同步更新本文件「能力清单 / 示例」即可，无需重新安装。  
> 脚本清单：`tdx_fin`(财务) · `tdx_reader`(日线) · `tdx_adjust`(前/后复权) · `tdx_xdxr`(除权除息) ·  
> `tdx_industry`(行业) · `tdx_float`(股本) · `tdx_indicators`(技术指标) · `tdx_blocks`(自定义板块) ·  
> `stock_names`(代码↔名称) · `chart_stock`(K线PNG) · `chart`(纯SVG图) · `tdx_qfq`(前复权兼容壳)。
