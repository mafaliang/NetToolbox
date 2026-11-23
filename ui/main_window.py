# -*- coding: utf-8 -*-
"""
主窗口
======
基于 tkinter / ttk 的图形界面，包含五大功能区：
  1. 网络命令  —— Ping / 路由追踪 / DNS / 域名解析 / ipconfig / netstat / ARP / 路由表
  2. 网络工具  —— IPv4/IPv6 子网计算 / 子网拆分 / IP 类别 / IPv6 地址速查 / 端口扫描
  3. 诊断工具  —— HTTP 响应头 / WHOIS / 批量连通性测试
  4. 知识查阅  —— 分类 + 搜索网络知识库（路由、IPv6 为重点）
  5. 关于

借鉴 NETworkManager 的统一界面 / 工具栏 / 命令矩阵设计理念。
"""
from __future__ import annotations

import json
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from core import commands, diagnostics, portscan, subnet
from knowledge import data as kb
from .help_texts import HELP_TEXTS

# ---------- 主题配色（仅浅色柠檬青；输出框保持深色终端风格） ----------
THEMES = {
    "light": {
        "BG": "#e6efd6", "CARD": "#ffffff", "ACCENT": "#4c7a3c",
        "ACCENT_DARK": "#3a602e", "TEXT": "#243019", "MUTED": "#6a7b5c",
        "OUTPUT_BG": "#1b2619", "OUTPUT_FG": "#e6f0df",
        "HELP_BG": "#eaf3da",
    },
}
# 渐变底色：柠檬黄 -> 薄荷青，加深并提高两端对比
GRADIENTS = {
    "light": ("#dbe59a", "#9fd9cc"),
}
# 背景斜纹格子点缀：斜线 / 网格线，用 stipple 模拟半透明，避免喧宾夺主
PATTERNS = {
    "light": {"stripe": "#a8bd76", "grid": "#c3d59a", "stipple": "gray25"},
}
# 当前主题色（模块级变量，供各构建函数读取）
BG = CARD = ACCENT = ACCENT_DARK = TEXT = MUTED = OUTPUT_BG = OUTPUT_FG = HELP_BG = ""
THEME_NAME = "light"
CONFIG_PATH = Path.home() / ".nettoolbox.json"


def _set_palette(name: str = "light"):
    """统一走浅色主题；保留 name 参数仅为兼容旧调用，深色已移除。"""
    global BG, CARD, ACCENT, ACCENT_DARK, TEXT, MUTED, OUTPUT_BG, OUTPUT_FG, HELP_BG, THEME_NAME
    THEME_NAME = "light"
    palette = THEMES[THEME_NAME]
    BG, CARD, ACCENT, ACCENT_DARK = (
        palette["BG"], palette["CARD"], palette["ACCENT"], palette["ACCENT_DARK"]
    )
    TEXT, MUTED = palette["TEXT"], palette["MUTED"]
    OUTPUT_BG, OUTPUT_FG = palette["OUTPUT_BG"], palette["OUTPUT_FG"]
    HELP_BG = palette["HELP_BG"]


_set_palette()


def _detect_font_family() -> str:
    """自动选择可用的中文字体族，兼顾 Windows 与 Linux。"""
    try:
        import tkinter.font as tkfont
        families = set(tkfont.families())
    except Exception:  # noqa: BLE001
        return "Microsoft YaHei UI"
    for name in ("Microsoft YaHei UI", "Microsoft YaHei", "Noto Sans CJK SC",
                 "WenQuanYi Micro Hei", "Source Han Sans SC", "SimHei", "Arial Unicode MS"):
        if name in families:
            return name
    return "sans-serif"


FONT_FAMILY = _detect_font_family()


def _font(size=10, bold=False):
    return (FONT_FAMILY, size, "bold" if bold else "normal")


def _hex_rgb(value: str):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _make_gradient(width: int, height: int, top: str, bottom: str):
    """先画小尺寸渐变再放大，避免逐像素填充整屏导致启动卡顿。"""
    sw = sh = 64
    img = tk.PhotoImage(width=sw, height=sh)
    c1, c2 = _hex_rgb(top), _hex_rgb(bottom)
    for y in range(sh):
        ratio = y / (sh - 1)
        color = "#%02x%02x%02x" % tuple(
            int(a + (b - a) * ratio) for a, b in zip(c1, c2)
        )
        img.put(" ".join([color] * sw), (0, y))
    return img.zoom(max(1, (width + sw - 1) // sw),
                    max(1, (height + sh - 1) // sh))


def _draw_pattern(canvas: tk.Canvas, w: int, h: int, theme: str):
    """在渐变底上叠加斜纹 + 细格线（半透明点画），仅画可见边缘，开销极低。"""
    conf = PATTERNS[theme]
    stripe, grid, stipple = conf["stripe"], conf["grid"], conf["stipple"]
    # 斜纹：45° 平行线，横向每 18px 一条
    step = 18
    for x in range(-h, w + h, step):
        canvas.create_line(x, h, x + h, 0, fill=stripe, width=1,
                           stipple=stipple)
    # 细格线：每 18px 横竖各一条，与斜纹叠出密集格子底纹
    for x in range(0, w, 18):
        canvas.create_line(x, 0, x, h, fill=grid, width=1, stipple=stipple)
    for y in range(0, h, 18):
        canvas.create_line(0, y, w, y, fill=grid, width=1, stipple=stipple)


class App(tk.Tk):
    def __init__(self):
        self.cfg = self._load_config()
        _set_palette()  # 仅浅色主题，忽略旧配置中的 theme 字段
        super().__init__()
        self.title("NetToolbox · 网络工具箱 v2.0")
        self.geometry("1120x780")
        self.minsize(940, 650)
        self.configure(bg=BG)
        self._center()
        self._init_style()

        # 渐变背景画布：置于最底层，窗口尺寸/主题变化时重绘
        self._grad_img = None
        self._grad_key = None
        self._bg_canvas = tk.Canvas(self, highlightthickness=0, bd=0)
        self._bg_canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self._bg_canvas.tk.call("lower", str(self._bg_canvas))
        self.bind("<Configure>", self._on_resize)

        # 线程安全的输出队列（工作线程 -> UI 线程）
        self.msg_queue: queue.Queue = queue.Queue()
        self._themed_texts: list[tuple[tk.Text, str]] = []
        self._help_boxes: dict[str, tk.Text] = {}
        self._help_titles: dict[str, ttk.Label] = {}
        self.scan_cancel = threading.Event()
        self.diag_cancel = threading.Event()

        # 四周留出更宽的渐变边框，让斜纹格子纹理可见
        self.container = tk.Frame(self, bg=BG, highlightthickness=0)
        self.container.pack(fill=tk.BOTH, expand=True, padx=20, pady=18)
        container = self.container
        container.columnconfigure(0, weight=1)
        container.rowconfigure(1, weight=1)

        self._build_toolbar(container)

        self.notebook = ttk.Notebook(container)
        self.notebook.grid(row=1, column=0, sticky="nsew", padx=10, pady=(6, 0))

        self.tab_commands = ttk.Frame(self.notebook)
        self.tab_tools = ttk.Frame(self.notebook)
        self.tab_diagnostics = ttk.Frame(self.notebook)
        self.tab_knowledge = ttk.Frame(self.notebook)
        self.tab_about = ttk.Frame(self.notebook)

        for tab, label in (
            (self.tab_commands, "  网络命令  "),
            (self.tab_tools, "  网络工具  "),
            (self.tab_diagnostics, "  诊断工具  "),
            (self.tab_knowledge, "  知识查阅  "),
            (self.tab_about, "  关于  "),
        ):
            self.notebook.add(tab, text=label)

        self._build_commands_tab(self.tab_commands)
        self._build_tools_tab(self.tab_tools)
        self._build_diagnostics_tab(self.tab_diagnostics)
        self._build_knowledge_tab(self.tab_knowledge)
        self._build_about_tab(self.tab_about)

        self.status = tk.StringVar(value="就绪 · NetToolbox v2.0")
        self.status_label = ttk.Label(
            self, textvariable=self.status, anchor=tk.W,
            foreground=MUTED, font=_font(9)
        )
        self.status_label.pack(fill=tk.X, side=tk.BOTTOM, padx=12, pady=(4, 6))
        self._on_resize()  # 首屏即绘制渐变，不依赖 Configure 事件触发时机
        self._poll_queue()

    # ------------------------------------------------------------------ #
    # 配置 / 主题
    # ------------------------------------------------------------------ #
    @staticmethod
    def _load_config() -> dict:
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_config(self):
        try:
            CONFIG_PATH.write_text(
                json.dumps(self.cfg, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            pass

    def _remember(self, key: str, value: str):
        value = (value or "").strip()
        if not value:
            return
        items = [v for v in self.cfg.get(key, []) if v != value]
        items.insert(0, value)
        self.cfg[key] = items[:10]
        self._save_config()

    def _center(self):
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw - w)//2}+{(sh - h)//2}")

    def _on_resize(self, event=None):
        if event is not None and event.widget is not self:
            return
        w, h = self.winfo_width(), self.winfo_height()
        if w < 2 or h < 2:
            return
        key = (w, h, THEME_NAME)
        if key == self._grad_key:
            return
        self._grad_key = key
        top, bottom = GRADIENTS[THEME_NAME]
        self._grad_img = _make_gradient(w, h, top, bottom)
        self._bg_canvas.delete("all")
        self._bg_canvas.create_image(0, 0, image=self._grad_img, anchor="nw")
        _draw_pattern(self._bg_canvas, w, h, THEME_NAME)
        self._bg_canvas.tk.call("lower", str(self._bg_canvas))

    def _init_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(12, 8), font=_font(10, True),
                        background=BG, foreground=TEXT)
        style.map("TNotebook.Tab", background=[("selected", CARD)],
                  foreground=[("selected", ACCENT)])
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD, relief="flat")
        style.configure("TLabel", background=BG, foreground=TEXT, font=_font(10))
        style.configure("Card.TLabel", background=CARD, foreground=TEXT, font=_font(10))
        style.configure("Title.TLabel", background=CARD, foreground=ACCENT,
                        font=_font(15, True))
        style.configure("Sub.TLabel", background=CARD, foreground=MUTED, font=_font(9))
        style.configure("TButton", font=_font(10), padding=5)
        style.configure("TEntry", font=_font(10), padding=5)
        style.configure("TCombobox", font=_font(10), padding=4)
        style.configure("TCheckbutton", background=CARD, font=_font(10))
        style.configure("TProgressbar", troughcolor=BG, background=ACCENT)
        style.configure("Treeview", fieldbackground=CARD, background=CARD,
                        foreground=TEXT, font=_font(10))
        style.configure("Treeview.Heading", background=BG, foreground=TEXT)

    # ------------------------------------------------------------------ #
    # 工具栏：复制 / 导出 / 清空 / 取消命令
    # ------------------------------------------------------------------ #
    def _build_toolbar(self, parent):
        bar = ttk.Frame(parent)
        bar.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))
        for text, cmd in (
            ("复制结果", self._copy_active),
            ("导出结果", self._export_active),
            ("清空结果", self._clear_active),
            ("取消命令", self._cancel_command),
        ):
            ttk.Button(bar, text=text, command=cmd).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Label(bar, text="提示：结果可一键复制 / 导出为 txt",
                  foreground=MUTED, font=_font(9)).pack(side=tk.RIGHT)

    def _active_output(self):
        idx = self.notebook.index(self.notebook.select())
        if idx == 0:
            return getattr(self, "_cmd_output", None)
        if idx == 1:
            return getattr(self, "tools_output", None)
        if idx == 2:
            return getattr(self, "diag_output", None)
        if idx == 3:
            return getattr(self, "kb_text", None)
        return None

    def _active_text(self) -> str:
        widget = self._active_output()
        return widget.get("1.0", tk.END).strip() if widget else ""

    def _copy_active(self):
        text = self._active_text()
        if not text:
            messagebox.showinfo("提示", "当前标签页没有可复制的结果。")
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status.set("已复制当前结果到剪贴板（%d 字符）" % len(text))

    def _export_active(self):
        text = self._active_text()
        if not text:
            messagebox.showinfo("提示", "当前标签页没有可导出的结果。")
            return
        path = filedialog.asksaveasfilename(
            title="导出结果", defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
            initialfile="NetToolbox_结果.txt",
        )
        if not path:
            return
        try:
            Path(path).write_text(text, encoding="utf-8")
            self.status.set("已导出到：" + path)
        except OSError as exc:
            messagebox.showerror("导出失败", str(exc))

    def _clear_active(self):
        widget = self._active_output()
        if widget:
            self._clear_output(widget)
            self.status.set("已清空当前结果")

    def _cancel_command(self):
        n = commands.cancel_all()
        self.status.set("已发送取消指令，终止 %d 个命令进程" % n if n else "当前没有运行中的命令")

    # ================================================================== #
    # 通用：队列轮询 + 工作线程执行
    # ================================================================== #
    def _poll_queue(self):
        try:
            while True:
                item = self.msg_queue.get_nowait()
                kind = item[0]
                if kind == "status":
                    self.status.set(item[1])
                elif kind == "clear":
                    self._clear_output(item[1])
                elif kind == "append":
                    self._append_output(item[1], item[2])
                elif kind == "scanprog":
                    if getattr(self, "scan_prog", None):
                        self.scan_prog["value"] = item[1]
                elif kind == "scandone":
                    if getattr(self, "scan_btn", None):
                        self.scan_btn.configure(state=tk.NORMAL)
                elif kind == "diagprog":
                    if getattr(self, "diag_prog", None):
                        self.diag_prog["value"] = item[1]
                elif kind == "diagdone":
                    if getattr(self, "diag_btn", None):
                        self.diag_btn.configure(state=tk.NORMAL)
                elif kind == "done":
                    self.status.set(item[1])
        except queue.Empty:
            pass
        self.after(80, self._poll_queue)

    def _run_async(self, target, *args, output=None):
        box = output if output is not None else getattr(self, "_cmd_output", None)

        def worker():
            try:
                target(*args)
            except Exception as exc:  # noqa: BLE001
                if box is not None:
                    self.msg_queue.put(("append", box, "[异常] %s\n" % exc))
                self.msg_queue.put(("done", "执行出错，请检查输入。"))

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------ #
    # 输出框工具
    # ------------------------------------------------------------------ #
    def _make_output(self, parent, kind="output"):
        box = scrolledtext.ScrolledText(
            parent, wrap=tk.WORD, font=("Consolas", 10),
            bg=OUTPUT_BG, fg=OUTPUT_FG, insertbackground=OUTPUT_FG,
            relief="flat", padx=10, pady=8,
        )
        self._themed_texts.append((box, kind))
        return box

    def _make_help_panel(self, parent, group: str):
        """在功能区右侧生成只读说明栏；默认显示总览，点按钮后只显示对应项。"""
        frame = ttk.Frame(parent, style="Card.TFrame", padding=8)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        title_label = ttk.Label(frame, text="", style="Sub.TLabel",
                                font=_font(10, True))
        title_label.grid(row=0, column=0, sticky="w", pady=(0, 6))
        box = scrolledtext.ScrolledText(
            frame, wrap=tk.WORD, font=_font(9), bg=HELP_BG, fg=TEXT,
            insertbackground=TEXT, relief="flat", padx=8, pady=6,
        )
        box.configure(state=tk.DISABLED)
        box.grid(row=1, column=0, sticky="nsew")
        self._help_boxes[group] = box
        self._help_titles[group] = title_label
        self._show_help(group, "default")
        return frame

    def _show_help(self, group: str, key: str):
        """切换说明栏内容：只展示当前点击功能的用法与返回说明。"""
        box = self._help_boxes.get(group)
        if box is None:
            return
        entries = HELP_TEXTS.get(group, {})
        title, content = entries.get(key, entries.get("default", ("", "")))
        self._help_titles[group].configure(text=title)
        box.configure(state=tk.NORMAL)
        box.delete("1.0", tk.END)
        box.insert(tk.END, content)
        box.configure(state=tk.DISABLED)
        box.see("1.0")

    def _clear_output(self, box):
        box.configure(state=tk.NORMAL)
        box.delete("1.0", tk.END)
        box.configure(state=tk.DISABLED)

    def _append_output(self, box, text):
        box.configure(state=tk.NORMAL)
        box.insert(tk.END, text)
        box.see(tk.END)
        box.configure(state=tk.DISABLED)

    # ================================================================== #
    # Tab 1：网络命令
    # ================================================================== #
    def _build_commands_tab(self, parent):
        parent.columnconfigure(0, weight=3)
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(0, weight=1)
        work = ttk.Frame(parent)
        work.grid(row=0, column=0, sticky="nsew")
        work.columnconfigure(0, weight=1)
        work.rowconfigure(1, weight=1)

        ctrl = ttk.Frame(work, style="Card.TFrame", padding=12)
        ctrl.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ctrl.columnconfigure(1, weight=1)

        ttk.Label(ctrl, text="目标主机 / IP：", style="Card.TLabel").grid(
            row=0, column=0, sticky="w")
        self.host_var = tk.StringVar(value="www.baidu.com")
        self.host_combo = ttk.Combobox(
            ctrl, textvariable=self.host_var,
            values=self.cfg.get("hosts", [])
        )
        self.host_combo.grid(row=0, column=1, sticky="ew", padx=6)

        self.count_var = tk.StringVar(value="4")
        ttk.Label(ctrl, text="次数/跳数：", style="Card.TLabel").grid(
            row=0, column=2, sticky="w", padx=(10, 0))
        ttk.Entry(ctrl, textvariable=self.count_var, width=6).grid(
            row=0, column=3, padx=4)

        self.dns_type = tk.StringVar(value="A")
        ttk.Label(ctrl, text="记录类型：", style="Card.TLabel").grid(
            row=0, column=4, sticky="w", padx=(10, 0))
        ttk.Combobox(ctrl, textvariable=self.dns_type, state="readonly",
                     values=list(commands.DNS_RECORD_TYPES), width=8).grid(
            row=0, column=5, padx=4)

        btn_frame = ttk.Frame(ctrl, style="Card.TFrame")
        btn_frame.grid(row=1, column=0, columnspan=6, sticky="ew", pady=(10, 0))
        for i, (text, cmd) in enumerate((
            ("Ping", self._do_ping), ("路由追踪", self._do_trace),
            ("DNS 查询", self._do_dns), ("域名解析", self._do_resolve),
            ("取消命令", self._cancel_command),
        )):
            ttk.Button(btn_frame, text=text, command=cmd).grid(
                row=0, column=i, padx=4, sticky="ew")
        btn_frame.columnconfigure("all", weight=1)

        local_frame = ttk.Frame(ctrl, style="Card.TFrame")
        local_frame.grid(row=2, column=0, columnspan=6, sticky="ew", pady=(8, 0))
        ttk.Label(local_frame, text="本机 / 系统信息：", style="Card.TLabel").grid(
            row=0, column=0, sticky="w")
        for i, (text, cmd) in enumerate((
            ("ipconfig", self._do_ipconfig), ("netstat", self._do_netstat),
            ("ARP 缓存", self._do_arp), ("路由表", self._do_route),
            ("IPv6 路由", self._do_route6), ("本机概览", self._do_overview),
        )):
            ttk.Button(local_frame, text=text, command=cmd).grid(
                row=1, column=i, padx=3, sticky="ew")
        local_frame.columnconfigure("all", weight=1)

        out_frame = ttk.Frame(work, style="Card.TFrame", padding=2)
        out_frame.grid(row=1, column=0, sticky="nsew")
        out_frame.columnconfigure(0, weight=1)
        out_frame.rowconfigure(0, weight=1)
        self._cmd_output = self._make_output(out_frame)
        self._cmd_output.grid(row=0, column=0, sticky="nsew")
        self._append_output(
            self._cmd_output,
            "NetToolbox · 网络命令控制台\n"
            "=====================================\n"
            "输入目标主机并选择命令；本机信息类命令无需输入目标。\n"
            "DNS 查询可切换 A / AAAA / MX / TXT 等记录类型。\n"
            "每个命令的用法与返回信息含义见右侧说明栏。\n"
            "耗时命令可在执行中点击「取消命令」终止。\n\n",
        )
        self._make_help_panel(parent, "commands").grid(
            row=0, column=1, sticky="nsew", padx=(8, 0))

    def _exec_command(self, fn, args, label, host_value=None):
        if host_value:
            self._remember("hosts", host_value)
            self.host_combo["values"] = self.cfg.get("hosts", [])
        box = self._cmd_output
        self.msg_queue.put(("clear", box))
        self.msg_queue.put(("append", box, f"$ {label}\n" + "-" * 50 + "\n"))
        self.status.set("正在执行：" + label)

        def target():
            out, cmdline = fn(*args)
            self.msg_queue.put(("append", box, out))
            self.msg_queue.put(
                ("append", box, "\n" + "=" * 50 + "\n[完成] " + cmdline + "\n")
            )
            self.msg_queue.put(("done", "完成：" + label))

        self._run_async(target, output=box)

    def _do_ping(self):
        self._show_help("commands", "ping")
        host = self.host_var.get()
        n = self.count_var.get().strip() or "4"
        self._exec_command(commands.ping, (host, n), f"ping {host}", host)

    def _do_trace(self):
        self._show_help("commands", "trace")
        host = self.host_var.get()
        n = self.count_var.get().strip() or "30"
        self._exec_command(commands.traceroute, (host, n), f"traceroute {host}", host)

    def _do_dns(self):
        self._show_help("commands", "dns")
        host = self.host_var.get()
        rtype = self.dns_type.get().strip() or "A"
        self._exec_command(commands.dns_lookup, (host, rtype),
                           f"nslookup -type={rtype} {host}", host)

    def _do_resolve(self):
        self._show_help("commands", "resolve")
        host = self.host_var.get()
        self._exec_command(commands.resolve, (host,), f"resolve {host}", host)

    def _do_ipconfig(self):
        self._show_help("commands", "ipconfig")
        self._exec_command(commands.ipconfig, (), "ipconfig /all")

    def _do_netstat(self):
        self._show_help("commands", "netstat")
        self._exec_command(commands.netstat, (), "netstat")

    def _do_arp(self):
        self._show_help("commands", "arp")
        self._exec_command(commands.arp, (), "arp -a")

    def _do_route(self):
        self._show_help("commands", "route")
        self._exec_command(commands.route_table, (), "route print")

    def _do_route6(self):
        self._show_help("commands", "route6")
        self._exec_command(commands.route_table6, (), "ip -6 route / netsh ipv6 route")

    def _do_overview(self):
        self._show_help("commands", "overview")
        box = self._cmd_output
        self._clear_output(box)
        self._append_output(box, commands.local_overview() + "\n")
        self.status.set("已生成本机概览（含 IPv6）")

    # ================================================================== #
    # Tab 2：网络工具
    # ================================================================== #
    def _build_tools_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        panes = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        panes.grid(row=0, column=0, sticky="nsew")

        left = ttk.Frame(panes, style="Card.TFrame", padding=14)
        ttk.Label(left, text="子网计算器", style="Title.TLabel").pack(anchor="w")
        ttk.Label(left, text="IPv4 / IPv6 · CIDR / 掩码 / 拆分 / 类别",
                  style="Sub.TLabel").pack(anchor="w", pady=(2, 12))

        ttk.Label(left, text="IP 地址：", style="Card.TLabel").pack(anchor="w")
        self.sub_ip = tk.StringVar(value="192.168.1.10")
        ttk.Entry(left, textvariable=self.sub_ip).pack(fill=tk.X, pady=4)

        ttk.Label(left, text="子网掩码 或 前缀（如 255.255.255.0 或 24）：",
                  style="Card.TLabel").pack(anchor="w", pady=(8, 0))
        self.sub_mask = tk.StringVar(value="24")
        ttk.Entry(left, textvariable=self.sub_mask).pack(fill=tk.X, pady=4)

        ttk.Button(left, text="计算子网", command=self._do_subnet).pack(fill=tk.X, pady=8)
        ttk.Button(left, text="判断 IP 类别", command=self._do_ipclass).pack(fill=tk.X, pady=2)

        ttk.Label(left, text="IPv6 地址速查（压缩/展开/类型）：",
                  style="Card.TLabel").pack(anchor="w", pady=(12, 0))
        self.v6_addr = tk.StringVar(value="2001:0db8:85a3::8a2e:370:7334")
        ttk.Entry(left, textvariable=self.v6_addr).pack(fill=tk.X, pady=4)
        ttk.Button(left, text="解析 IPv6", command=self._do_ipv6).pack(fill=tk.X, pady=2)

        ttk.Label(left, text="子网拆分：父前缀 / 新前缀 / 基准网络",
                  style="Card.TLabel").pack(anchor="w", pady=(12, 0))
        split_f = ttk.Frame(left, style="Card.TFrame")
        split_f.pack(fill=tk.X, pady=4)
        self.split_old = tk.StringVar(value="24")
        self.split_new = tk.StringVar(value="27")
        self.split_base = tk.StringVar(value="192.168.1.0")
        ttk.Entry(split_f, textvariable=self.split_old, width=5).pack(side=tk.LEFT, padx=2)
        ttk.Label(split_f, text="->", style="Card.TLabel").pack(side=tk.LEFT)
        ttk.Entry(split_f, textvariable=self.split_new, width=5).pack(side=tk.LEFT, padx=2)
        ttk.Entry(split_f, textvariable=self.split_base, width=16).pack(side=tk.LEFT, padx=2)
        ttk.Button(left, text="划分子网（支持 IPv6）",
                   command=self._do_split).pack(fill=tk.X, pady=6)

        right = ttk.Frame(panes, style="Card.TFrame", padding=14)
        ttk.Label(right, text="端口扫描 (TCP Connect)", style="Title.TLabel").pack(anchor="w")
        ttk.Label(right, text="检测目标主机哪些端口开放",
                  style="Sub.TLabel").pack(anchor="w", pady=(2, 10))

        pf = ttk.Frame(right, style="Card.TFrame")
        pf.pack(fill=tk.X)
        ttk.Label(pf, text="主机：", style="Card.TLabel").grid(row=0, column=0, sticky="w")
        self.scan_host = tk.StringVar(value="127.0.0.1")
        self.scan_combo = ttk.Combobox(
            pf, textvariable=self.scan_host, values=self.cfg.get("scan_hosts", [])
        )
        self.scan_combo.grid(row=0, column=1, padx=4, sticky="ew")
        ttk.Label(pf, text="端口：", style="Card.TLabel").grid(
            row=1, column=0, sticky="w", pady=(6, 0))
        self.scan_ports = tk.StringVar(value="80,443,3306,3389,8000-8010")
        ttk.Entry(pf, textvariable=self.scan_ports, width=18).grid(
            row=1, column=1, padx=4, pady=(6, 0), sticky="ew")
        pf.columnconfigure(1, weight=1)

        bf = ttk.Frame(right, style="Card.TFrame")
        bf.pack(fill=tk.X, pady=8)
        ttk.Button(bf, text="常用端口", command=self._fill_common).pack(side=tk.LEFT, padx=2)
        self.scan_btn = ttk.Button(bf, text="开始扫描", command=self._do_scan)
        self.scan_btn.pack(side=tk.LEFT, padx=2)
        ttk.Button(bf, text="停止", command=self._stop_scan).pack(side=tk.LEFT, padx=2)
        self.scan_prog = ttk.Progressbar(bf, mode="determinate", length=90)
        self.scan_prog.pack(side=tk.LEFT, padx=6)

        self.tools_output = self._make_output(right)
        self.tools_output.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        self._append_output(
            self.tools_output, "子网计算 / IPv6 / 端口扫描结果将显示在这里。\n"
        )

        panes.add(left, weight=1)
        panes.add(right, weight=2)
        panes.add(self._make_help_panel(panes, "tools"), weight=1)

    def _show_tools(self, result: str, status: str):
        self._clear_output(self.tools_output)
        self._append_output(self.tools_output, result + "\n")
        self.status.set(status)

    def _do_subnet(self):
        self._show_help("tools", "subnet")
        try:
            mask = self.sub_mask.get().strip()
            result = (subnet.calculate_cidr(self.sub_ip.get(), int(mask))
                      if mask.isdigit()
                      else subnet.calculate_mask(self.sub_ip.get(), mask))
        except Exception as exc:  # noqa: BLE001
            result = "[输入错误] %s" % exc
        self._show_tools(result, "子网计算完成")

    def _do_split(self):
        self._show_help("tools", "split")
        try:
            result = subnet.subnets_from_prefix(
                int(self.split_old.get()), int(self.split_new.get()),
                self.split_base.get())
        except Exception as exc:  # noqa: BLE001
            result = "[输入错误] %s" % exc
        self._show_tools(result, "子网划分完成")

    def _do_ipclass(self):
        self._show_help("tools", "ipclass")
        try:
            result = subnet.ip_class(self.sub_ip.get())
        except Exception as exc:  # noqa: BLE001
            result = "[输入错误] %s" % exc
        self._show_tools(result, "IP 类别判断完成")

    def _do_ipv6(self):
        self._show_help("tools", "ipv6")
        try:
            result = subnet.ipv6_format(self.v6_addr.get())
        except Exception as exc:  # noqa: BLE001
            result = "[输入错误] %s" % exc
        self._show_tools(result, "IPv6 地址解析完成")

    def _fill_common(self):
        self._show_help("tools", "scan")
        self.scan_ports.set(",".join(str(p) for p in portscan.WELL_KNOWN))

    def _stop_scan(self):
        self.scan_cancel.set()
        self.status.set("已请求停止端口扫描")

    def _do_scan(self):
        self._show_help("tools", "scan")
        host = self.scan_host.get().strip()
        ports = portscan.parse_ports(self.scan_ports.get())
        if not host or not ports:
            messagebox.showwarning("输入提示", "请输入有效的主机与端口。")
            return
        if not messagebox.askokcancel(
            "扫描确认", "即将扫描 %s 的 %d 个端口。\n请确认目标在授权范围内。" % (host, len(ports))
        ):
            return
        self._remember("scan_hosts", host)
        self.scan_combo["values"] = self.cfg.get("scan_hosts", [])
        box = self.tools_output
        self._clear_output(box)
        self._append_output(box, "正在扫描 %s 的 %d 个端口...\n" % (host, len(ports)))
        self.scan_btn.configure(state=tk.DISABLED)
        self.scan_cancel = threading.Event()
        self.scan_prog["value"] = 0
        self.scan_prog["maximum"] = len(ports)
        self.status.set("正在扫描端口...")

        def progress(done, total):
            self.msg_queue.put(("scanprog", done))

        def target():
            results = portscan.scan(
                host, ports, progress=progress, cancel_event=self.scan_cancel
            )
            report = portscan.format_results(host, results)
            if self.scan_cancel.is_set():
                report += "\n[提示] 扫描已停止，以上为部分结果。"
            self.msg_queue.put(("clear", box))
            self.msg_queue.put(("append", box, report + "\n"))
            self.msg_queue.put(("scandone",))
            self.msg_queue.put(("done", "端口扫描完成"))

        self._run_async(target, output=box)

    # ================================================================== #
    # Tab 3：诊断工具
    # ================================================================== #
    def _build_diagnostics_tab(self, parent):
        parent.columnconfigure(0, weight=3)
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(0, weight=1)
        work = ttk.Frame(parent)
        work.grid(row=0, column=0, sticky="nsew")
        work.columnconfigure(0, weight=1)
        work.rowconfigure(1, weight=1)

        top = ttk.Frame(work, style="Card.TFrame", padding=12)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="HTTP 响应头检测", style="Card.TLabel").grid(
            row=0, column=0, sticky="w")
        self.http_url = tk.StringVar(value="https://www.baidu.com")
        ttk.Entry(top, textvariable=self.http_url).grid(
            row=0, column=1, sticky="ew", padx=6)
        ttk.Button(top, text="检测", command=self._do_http).grid(row=0, column=2)

        ttk.Label(top, text="WHOIS 查询", style="Card.TLabel").grid(
            row=1, column=0, sticky="w", pady=(8, 0))
        self.whois_target = tk.StringVar(value="baidu.com")
        ttk.Entry(top, textvariable=self.whois_target).grid(
            row=1, column=1, sticky="ew", padx=6, pady=(8, 0))
        ttk.Button(top, text="查询", command=self._do_whois).grid(row=1, column=2, pady=(8, 0))

        ttk.Label(top, text="批量连通性（主机 / 端口）", style="Card.TLabel").grid(
            row=2, column=0, sticky="w", pady=(8, 0))
        self.bulk_hosts = tk.StringVar(value="127.0.0.1,localhost")
        ttk.Entry(top, textvariable=self.bulk_hosts).grid(
            row=2, column=1, sticky="ew", padx=6, pady=(8, 0))
        self.bulk_ports = tk.StringVar(value="80,443")
        ttk.Entry(top, textvariable=self.bulk_ports, width=18).grid(
            row=2, column=2, sticky="ew", padx=6, pady=(8, 0))
        self.diag_btn = ttk.Button(top, text="开始检测", command=self._do_bulk)
        self.diag_btn.grid(row=2, column=3, padx=2, pady=(8, 0))
        ttk.Button(top, text="停止", command=self._stop_diag).grid(
            row=2, column=4, pady=(8, 0))
        self.diag_prog = ttk.Progressbar(top, mode="determinate", length=80)
        self.diag_prog.grid(row=2, column=5, padx=6, pady=(8, 0))

        box_frame = ttk.Frame(work, style="Card.TFrame", padding=2)
        box_frame.grid(row=1, column=0, sticky="nsew")
        box_frame.columnconfigure(0, weight=1)
        box_frame.rowconfigure(0, weight=1)
        self.diag_output = self._make_output(box_frame)
        self.diag_output.grid(row=0, column=0, sticky="nsew")
        self._append_output(
            self.diag_output,
            "诊断工具说明\n"
            "============\n"
            "· HTTP 检测：显示响应状态码、响应头与耗时；超时默认 10 秒。\n"
            "· WHOIS：查询域名/IP 注册信息，自动跟随转介服务器。\n"
            "· 批量连通性：主机×端口矩阵，open 表示 TCP 可连接。\n"
            "  详细说明见右侧说明栏；请仅在授权网络上使用。\n\n",
        )
        self._make_help_panel(parent, "diagnostics").grid(
            row=0, column=1, sticky="nsew", padx=(8, 0))

    def _diag_prepare(self):
        self._clear_output(self.diag_output)
        self.status.set("正在执行诊断...")

    def _stop_diag(self):
        self.diag_cancel.set()
        self.status.set("已请求停止批量检测")

    def _do_http(self):
        self._show_help("diagnostics", "http")
        url = self.http_url.get().strip()
        self._diag_prepare()
        self._append_output(self.diag_output, "请求 %s ...\n" % url)

        def target():
            result = diagnostics.http_headers(url)
            self.msg_queue.put(("clear", self.diag_output))
            self.msg_queue.put(("append", self.diag_output, result + "\n"))
            self.msg_queue.put(("done", "HTTP 检测完成"))

        self._run_async(target, output=self.diag_output)

    def _do_whois(self):
        self._show_help("diagnostics", "whois")
        target_text = self.whois_target.get().strip()
        self._diag_prepare()
        self._append_output(self.diag_output, "查询 WHOIS：%s ...\n" % target_text)

        def target():
            result = diagnostics.whois(target_text)
            self.msg_queue.put(("clear", self.diag_output))
            self.msg_queue.put(("append", self.diag_output, result + "\n"))
            self.msg_queue.put(("done", "WHOIS 查询完成"))

        self._run_async(target, output=self.diag_output)

    def _do_bulk(self):
        self._show_help("diagnostics", "bulk")
        hosts = self.bulk_hosts.get().strip()
        ports = self.bulk_ports.get().strip()
        self._diag_prepare()
        self.diag_btn.configure(state=tk.DISABLED)
        self.diag_cancel = threading.Event()
        self.diag_prog["value"] = 0

        def progress(done, total):
            self.msg_queue.put(("diagprog", done))

        def target():
            result = diagnostics.bulk_connect(
                hosts, ports, progress=progress, cancel_event=self.diag_cancel
            )
            self.msg_queue.put(("clear", self.diag_output))
            self.msg_queue.put(("append", self.diag_output, result + "\n"))
            self.msg_queue.put(("diagdone",))
            self.msg_queue.put(("done", "批量连通性检测完成"))

        self._run_async(target, output=self.diag_output)

    # ================================================================== #
    # Tab 4：知识查阅
    # ================================================================== #
    def _build_knowledge_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        top = ttk.Frame(parent, style="Card.TFrame", padding=10)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(top, text="网络知识速查库", style="Title.TLabel").grid(
            row=0, column=0, sticky="w")
        ttk.Label(top, text="从入门到进阶：网络基础 / 路由 / IPv6 / 子网 / TCP/IP",
                  style="Sub.TLabel").grid(row=1, column=0, sticky="w")

        self.kw_var = tk.StringVar()
        kw_entry = ttk.Entry(top, textvariable=self.kw_var, width=30)
        kw_entry.grid(row=0, column=1, sticky="ew", padx=6)
        kw_entry.bind("<Return>", lambda e: self._search_kb())
        ttk.Button(top, text="搜索", command=self._search_kb).grid(row=0, column=2, padx=2)
        ttk.Button(top, text="全部", command=self._show_all_kb).grid(row=0, column=3, padx=2)
        top.columnconfigure(1, weight=1)

        body = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        body.grid(row=1, column=0, sticky="nsew")

        left = ttk.Frame(body, style="Card.TFrame", padding=8)
        ttk.Label(left, text="分类 / 条目", style="Card.TLabel").pack(anchor="w")
        self.kb_tree = ttk.Treeview(left, show="tree", selectmode="browse")
        self.kb_tree.pack(fill=tk.BOTH, expand=True, pady=6)
        self.kb_tree.tag_configure("cat", foreground=ACCENT)
        self.kb_tree.bind("<<TreeviewSelect>>", self._on_kb_select)
        self._populate_kb_tree()

        right = ttk.Frame(body, style="Card.TFrame", padding=2)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        self.kb_title = ttk.Label(right, text="欢迎使用知识库",
                                  style="Card.TLabel", font=_font(14, True))
        self.kb_title.grid(row=0, column=0, sticky="w", padx=12, pady=(10, 4))
        self.kb_text = scrolledtext.ScrolledText(
            right, wrap=tk.WORD, font=_font(11), bg=CARD, fg=TEXT,
            insertbackground=TEXT, relief="flat", padx=12, pady=8,
        )
        self._themed_texts.append((self.kb_text, "knowledge"))
        self.kb_text.grid(row=1, column=0, sticky="nsew")
        self.kb_text.configure(state=tk.DISABLED)
        self._show_kb_content(
            "欢迎使用网络知识速查库（共 %d 条）\n\n" % len(kb.KNOWLEDGE)
            + "  · 网络入门：IP 地址、掩码、网关、DNS、端口、TCP/UDP、NAT 等\n"
            "  · 路由基础：路由表、最长前缀匹配、静态/动态路由、AD 与 Metric\n"
            "  · 路由协议：OSPF、BGP、RIP、重分发与汇总\n"
            "  · 子网与地址：CIDR、VLSM、私有地址\n"
            "  · TCP/IP：三次握手、ARP/ICMP\n"
            "  · IPv6：地址表示、地址类型、NDP、双栈过渡\n\n"
            "左侧选择条目，或输入关键词（如「网关」「BGP」「IPv6」「子网」）搜索。\n"
        )

        body.add(left, weight=1)
        body.add(right, weight=3)

    def _populate_kb_tree(self, items=None):
        tree = self.kb_tree
        for child in tree.get_children():
            tree.delete(child)
        self._kb_index = {}
        source = items if items is not None else kb.KNOWLEDGE
        grouped: dict[str, list] = {}
        for item in source:
            grouped.setdefault(item["category"], []).append(item)
        for cat in kb.CATEGORIES:
            if cat not in grouped:
                continue
            cat_id = tree.insert("", tk.END, text="▼ " + cat, tags=("cat",), open=True)
            for item in grouped[cat]:
                iid = tree.insert(cat_id, tk.END, text="   " + item["title"])
                self._kb_index[iid] = item

    def _search_kb(self):
        kw = self.kw_var.get()
        results = kb.search(kw)
        self._populate_kb_tree(results)
        self.status.set("知识库搜索「%s」：找到 %d 条" % (kw, len(results)))

    def _show_all_kb(self):
        self.kw_var.set("")
        self._populate_kb_tree()
        self.status.set("知识库：显示全部条目")

    def _on_kb_select(self, event):
        sel = self.kb_tree.selection()
        if not sel:
            return
        item = self._kb_index.get(sel[0])
        if item:
            self._show_kb_content(item["content"], item["title"])

    def _show_kb_content(self, text, title="网络知识速查库"):
        self.kb_title.configure(text=title)
        self.kb_text.configure(state=tk.NORMAL)
        self.kb_text.delete("1.0", tk.END)
        self.kb_text.insert(tk.END, text)
        self.kb_text.configure(state=tk.DISABLED)

    # ================================================================== #
    # Tab 5：关于
    # ================================================================== #
    def _build_about_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        info = (
            "NetToolbox · 网络工具箱 v2.0\n"
            "====================================\n\n"
            "定位和设计参考：\n"
            "  借鉴 GitHub 项目 BornToBeRoot/NETworkManager（8.9k stars, C#/WPF）\n"
            "  的「统一界面 + 命令工具矩阵」理念，用 Python 重新实现，\n"
            "  可跨平台运行并轻松打包为 Windows 可执行程序。\n\n"
            "功能：\n"
            "  · 网络命令：Ping / 路由追踪 / DNS（多种记录类型）/ 域名解析 /\n"
            "    ipconfig / netstat / ARP / IPv4 与 IPv6 路由表 / 本机概览\n"
            "  · 网络工具：IPv4/IPv6 子网计算、子网拆分、IP 类别、IPv6 地址速查、\n"
            "    TCP 端口扫描（可中途停止）\n"
            "  · 诊断工具：HTTP 响应头、WHOIS、批量连通性矩阵\n"
            "  · 知识查阅：网络入门 / 路由 / IPv6 速查库（分类 + 搜索）\n"
            "  · 界面辅助：各功能区右侧的中文说明栏，解释用法与返回字段含义\n"
            "  · 体验增强：加深的柠檬青渐变 + 斜纹格子背景、结果复制/导出、\n"
            "    命令取消与输入历史\n\n"
            "技术说明：\n"
            "  · 仅用 Python 标准库（tkinter / socket / ipaddress / urllib 等）\n"
            "  · 大网段地址范围用整数运算得出，支持 /0 网段不卡顿\n"
            "  · 耗时任务在后台线程执行，队列同步输出，不阻塞界面\n"
            "  · 主机历史保存在 ~/.nettoolbox.json\n\n"
            "提示：端口扫描与连通性检测请确保目标在授权范围内。\n"
            "许可证：本项目为演示/学习用途编写。\n"
        )
        lbl = ttk.Label(parent, text=info, style="Card.TLabel",
                        font=_font(11), justify=tk.LEFT, anchor="nw", padding=10)
        lbl.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
