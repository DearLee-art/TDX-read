# -*- coding: utf-8 -*-
"""
[兼容壳] tdx_qfq.py —— 前复权工具（旧入口，保留以兼容既有调用）。
================================================================
复权逻辑已统一迁移到 `tdx_adjust.py`（支持前复权 qfq / 后复权 hfq，本地 gbbq 精确计算）。
本文件仅做参数转发，保证老命令仍可用：

  python tdx_qfq.py 600519 --days 300 --csv --html          # 等价 tdx_adjust --mode qfq
  python tdx_qfq.py 300750 --mode hfq --days 120            # 直接透传新参数

新代码建议直接用 `tdx_adjust.py`：
  python tdx_adjust.py 600519 --mode qfq|hfq --days 300 --csv --html
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from tdx_adjust import main as _adjust_main   # noqa: E402


def main():
    argv = list(sys.argv[1:])
    # 旧参数 --exdates（离线近似）已不需要：本机 gbbq 提供精确除权除息事件
    if "--exdates" in argv:
        i = argv.index("--exdates")
        if i + 1 < len(argv):
            del argv[i:i + 2]
        else:
            del argv[i]
        print("[tdx_qfq] 提示：--exdates 已废弃，复权现由本机 gbbq 除权除息数据精确计算。",
              file=sys.stderr)
    sys.argv = ["tdx_qfq"] + argv
    _adjust_main()


if __name__ == "__main__":
    main()
