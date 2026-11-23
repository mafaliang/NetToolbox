# -*- coding: utf-8 -*-
"""
NetToolbox · 网络工具箱 —— 程序入口

运行方式：
    python main.py

打包为 Windows exe（在 Windows 上执行）：
    1) pip install pyinstaller
    2) pyinstaller -F -w -n NetToolbox main.py
    生成 dist/NetToolbox.exe
"""
import os
import sys

# 保证从任意目录启动都能找到本地包
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui.main_window import main  # noqa: E402

if __name__ == "__main__":
    main()
