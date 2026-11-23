# -*- coding: utf-8 -*-
"""
网络命令封装模块
----------------
将常见的网络诊断命令封装为统一的 Python 接口，自动适配 Windows / Linux / macOS。

借鉴 NETworkManager 的命令工具矩阵设计：Ping、Traceroute、DNS、
ipconfig、netstat、arp、route 等。

每个函数均通过子进程执行系统原生命令，返回纯文本输出，供 GUI 展示。
"""
from __future__ import annotations

import ipaddress
import platform
import re
import shutil
import socket
import subprocess
import threading
from typing import Tuple

SYSTEM = platform.system().lower()  # 'windows' / 'linux' / 'darwin'

# 记录正在运行的子进程，供界面「取消」按钮终止
_ACTIVE_PROCS: set[subprocess.Popen] = set()
_PROC_LOCK = threading.Lock()

DNS_RECORD_TYPES = ("A", "AAAA", "CNAME", "MX", "NS", "PTR", "SOA", "TXT", "SRV")


def cancel_all() -> int:
    """终止所有正在运行的网络命令，返回被终止的进程数。"""
    with _PROC_LOCK:
        procs = list(_ACTIVE_PROCS)
    for proc in procs:
        try:
            proc.terminate()
        except OSError:
            pass
    return len(procs)


def _decode(data: bytes) -> str:
    """智能解码命令输出：优先 UTF-8，回退到系统本地编码（Windows 中文为 GBK）。"""
    for enc in ("utf-8", "gbk", "gb18030", "cp936", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _run(argv: list[str], timeout: int = 30) -> Tuple[str, str]:
    """在独立进程中执行命令，返回 (stdout+stderr, 命令本身)。"""
    creationflags = 0
    if SYSTEM == "windows":
        # Windows 下隐藏黑框
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
        )
    except FileNotFoundError:
        return "[错误] 找不到命令：%s\n" % argv[0], " ".join(argv)
    except Exception as exc:  # noqa: BLE001
        return "[错误] 命令执行失败：%s\n" % exc, " ".join(argv)

    with _PROC_LOCK:
        _ACTIVE_PROCS.add(proc)
    try:
        stdout, _ = proc.communicate(timeout=timeout)
        out = _decode(stdout)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, _ = proc.communicate()
        out = _decode(stdout) + "\n[超时] 命令执行超过 %d 秒，已终止。\n" % timeout
    except Exception as exc:  # noqa: BLE001
        out = "[错误] 命令执行失败：%s\n" % exc
    finally:
        with _PROC_LOCK:
            _ACTIVE_PROCS.discard(proc)
    return out, " ".join(argv)


def _validate_host(host: str) -> str:
    host = (host or "").strip()
    if not host:
        raise ValueError("请输入主机名或 IP 地址。")
    return host


# --------------------------------------------------------------------------- #
# Ping
# --------------------------------------------------------------------------- #
def ping(host: str, count: int = 4) -> Tuple[str, str]:
    host = _validate_host(host)
    count = max(1, min(20, int(count)))
    if SYSTEM == "windows":
        argv = ["ping", "-n", str(count), host]
    else:
        argv = ["ping", "-c", str(count), host]
    return _run(argv, timeout=count * 3 + 10)


# --------------------------------------------------------------------------- #
# Traceroute / Tracert
# --------------------------------------------------------------------------- #
def traceroute(host: str, max_hops: int = 30) -> Tuple[str, str]:
    host = _validate_host(host)
    max_hops = max(1, min(64, int(max_hops)))
    if SYSTEM == "windows":
        argv = ["tracert", "-h", str(max_hops), "-w", "1000", host]
    else:
        argv = ["traceroute", "-m", str(max_hops), "-w", "1", host]
    return _run(argv, timeout=max_hops * 3 + 15)


# --------------------------------------------------------------------------- #
# DNS 查询 (nslookup / dig / host)
# --------------------------------------------------------------------------- #
def dns_lookup(host: str, record_type: str = "A") -> Tuple[str, str]:
    host = _validate_host(host)
    if shutil.which("nslookup"):
        if record_type.upper() == "A":
            argv = ["nslookup", host]
        else:
            argv = ["nslookup", "-type=" + record_type.upper(), host]
        return _run(argv, timeout=20)
    if shutil.which("dig"):
        return _run(["dig", "+noall", "+answer", host, record_type.upper()], timeout=20)
    if shutil.which("host"):
        return _run(["host", "-t", record_type.upper(), host], timeout=20)
    # 纯 Python 兜底
    try:
        infos = socket.getaddrinfo(host, None)
        ips = sorted({item[4][0] for item in infos})
        return "\n".join(ips), "getaddrinfo(%s)" % host
    except Exception as exc:  # noqa: BLE001
        return "[错误] DNS 查询失败：%s" % exc, "getaddrinfo(%s)" % host


# --------------------------------------------------------------------------- #
# 本地网络配置 (ipconfig / ifconfig / ip addr)
# --------------------------------------------------------------------------- #
def ipconfig() -> Tuple[str, str]:
    if SYSTEM == "windows":
        return _run(["ipconfig", "/all"], timeout=20)
    if shutil.which("ip"):
        return _run(["ip", "addr", "show"], timeout=20)
    return _run(["ifconfig", "-a"], timeout=20)


# --------------------------------------------------------------------------- #
# 网络连接 / 监听端口 (netstat / ss)
# --------------------------------------------------------------------------- #
def netstat() -> Tuple[str, str]:
    if SYSTEM == "windows":
        return _run(["netstat", "-ano"], timeout=25)
    if shutil.which("ss"):
        return _run(["ss", "-tulnp"], timeout=25)
    return _run(["netstat", "-tulnp"], timeout=25)


# --------------------------------------------------------------------------- #
# ARP 缓存
# --------------------------------------------------------------------------- #
def arp() -> Tuple[str, str]:
    if SYSTEM == "windows":
        return _run(["arp", "-a"], timeout=20)
    if shutil.which("arp"):
        return _run(["arp", "-a"], timeout=20)
    return _run(["ip", "neigh", "show"], timeout=20)


# --------------------------------------------------------------------------- #
# 路由表 (route print / ip route)
# --------------------------------------------------------------------------- #
def route_table() -> Tuple[str, str]:
    if SYSTEM == "windows":
        return _run(["route", "print"], timeout=20)
    if shutil.which("ip"):
        out, _ = _run(["ip", "route", "show"], timeout=20)
        return out, "ip route show"
    return _run(["netstat", "-rn"], timeout=20)


# --------------------------------------------------------------------------- #
# IPv6 路由表
# --------------------------------------------------------------------------- #
def route_table6() -> Tuple[str, str]:
    if SYSTEM == "windows":
        return _run(["netsh", "interface", "ipv6", "show", "route"], timeout=20)
    if shutil.which("ip"):
        return _run(["ip", "-6", "route", "show"], timeout=20)
    if shutil.which("route"):
        return _run(["route", "-A", "inet6", "show"], timeout=20)
    return "[提示] 未找到可用的 IPv6 路由查看命令。\n", "route -A inet6"


# --------------------------------------------------------------------------- #
# 域名 -> IP / IP -> 域名
# --------------------------------------------------------------------------- #
def resolve(host: str) -> Tuple[str, str]:
    host = _validate_host(host)
    # 输入是 IP：优先反向解析；输入是域名：正向解析
    try:
        ipaddress.ip_address(host)
        is_ip = True
    except ValueError:
        is_ip = False
    if is_ip:
        try:
            name, aliases, _ = socket.gethostbyaddr(host)
            extra = ("\n别名：%s" % ", ".join(aliases)) if aliases else ""
            return "IP  ->  域名：%s  ->  %s%s" % (host, name, extra), "gethostbyaddr"
        except Exception as exc:  # noqa: BLE001
            return "[提示] 未找到 PTR 记录：%s" % exc, "gethostbyaddr"
    try:
        infos = socket.getaddrinfo(host, None)
        ips = sorted({item[4][0] for item in infos})
        return "%s  ->  %s" % (host, ", ".join(ips)), "getaddrinfo"
    except Exception as exc:  # noqa: BLE001
        return "[错误] 解析失败：%s" % exc, "getaddrinfo"


# --------------------------------------------------------------------------- #
# 本地主机概览
# --------------------------------------------------------------------------- #
def local_overview() -> str:
    lines = [
        "操作系统      : %s" % platform.platform(),
        "主机名        : %s" % socket.gethostname(),
    ]
    hostname = socket.gethostname()
    try:
        lines.append("本机 IPv4     : %s" % socket.gethostbyname(hostname))
    except Exception:  # noqa: BLE001
        pass

    # IPv6：从主机名解析获取全局/ULA 地址（跳过链路本地）
    try:
        v6 = sorted({
            item[4][0] for item in socket.getaddrinfo(hostname, None, socket.AF_INET6)
            if not item[4][0].lower().startswith("fe80")
        })
        if v6:
            lines.append("本机 IPv6     : %s" % ", ".join(v6))
    except Exception:  # noqa: BLE001
        pass

    # 通过 UDP connect 选择出口地址（不会真正发包）
    for family, target, label in (
        (socket.AF_INET, ("8.8.8.8", 80), "出口 IPv4"),
        (socket.AF_INET6, ("2001:4860:4860::8888", 80), "出口 IPv6"),
    ):
        try:
            with socket.socket(family, socket.SOCK_DGRAM) as s:
                s.connect(target)
                lines.append("%s : %s" % (label, s.getsockname()[0]))
        except Exception:  # noqa: BLE001
            pass

    if SYSTEM != "windows":
        try:
            with open("/etc/resolv.conf", encoding="utf-8", errors="replace") as fp:
                servers = [line.split()[1] for line in fp
                           if line.strip().startswith("nameserver")
                           and len(line.split()) > 1]
            if servers:
                lines.append("DNS 服务器    : %s" % ", ".join(servers))
        except OSError:
            pass
    return "\n".join(lines)


def is_windows() -> bool:
    return SYSTEM == "windows"
