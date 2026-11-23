# -*- coding: utf-8 -*-
"""
端口扫描模块
------------
基于 TCP connect() 的端口连通性检测，无需第三方依赖。
借鉴 NETworkManager 的 Port Scanner 功能。
"""
from __future__ import annotations

import socket
from concurrent.futures import ThreadPoolExecutor, as_completed

# 常见端口服务名
COMMON_PORTS = {
    21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP", 53: "DNS",
    80: "HTTP", 110: "POP3", 119: "NNTP", 123: "NTP", 135: "MS-RPC",
    139: "NetBIOS", 143: "IMAP", 161: "SNMP", 389: "LDAP", 443: "HTTPS",
    445: "SMB", 465: "SMTPS", 514: "Syslog", 587: "SMTP(提交)",
    631: "IPP", 636: "LDAPS", 873: "rsync", 993: "IMAPS", 995: "POP3S",
    1080: "SOCKS", 1433: "MSSQL", 1521: "Oracle", 2049: "NFS",
    3306: "MySQL", 3389: "RDP", 4443: "HTTPS-alt", 5060: "SIP",
    5432: "PostgreSQL", 5900: "VNC", 6379: "Redis", 8080: "HTTP-Proxy",
    8443: "HTTPS-alt", 9200: "Elasticsearch", 11211: "Memcached",
}

WELL_KNOWN = sorted(COMMON_PORTS.keys())


def parse_ports(text: str) -> list[int]:
    """解析端口表达式，如 '80,443,8000-8010'。"""
    ports: set[int] = set()
    for part in (text or "").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            try:
                a, b = part.split("-", 1)
                start, end = int(a), int(b)
                if start > end:
                    start, end = end, start
                ports.update(range(max(1, start), min(65535, end) + 1))
            except ValueError:
                continue
        else:
            try:
                p = int(part)
                if 1 <= p <= 65535:
                    ports.add(p)
            except ValueError:
                continue
    return sorted(ports)


def _probe(host: str, port: int, timeout: float,
           cancel_event=None) -> tuple[int, bool, str]:
    if cancel_event is not None and cancel_event.is_set():
        return port, False, ""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return port, True, COMMON_PORTS.get(port, "")
    except (socket.timeout, ConnectionRefusedError, OSError):
        return port, False, ""
    except Exception:  # noqa: BLE001
        return port, False, ""


def scan(host: str, ports: list[int], timeout: float = 0.6,
         workers: int = 80, progress=None, cancel_event=None) -> list[tuple[int, bool, str]]:
    """并发扫描端口，返回 [(端口, 是否开放, 服务名), ...]；支持中途取消。"""
    results: list[tuple[int, bool, str]] = []
    pending = list(ports)
    if cancel_event is not None and cancel_event.is_set():
        return results
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {
            ex.submit(_probe, host, p, timeout, cancel_event): p for p in pending
        }
        done = 0
        for fut in as_completed(futures):
            results.append(fut.result())
            done += 1
            if progress:
                progress(done, len(pending))
            if cancel_event is not None and cancel_event.is_set():
                # 已提交的探测会继续完成，但不再阻塞等待剩余结果
                break
    results.sort(key=lambda x: x[0])
    return results


def format_results(host: str, results: list[tuple[int, bool, str]]) -> str:
    opened = [r for r in results if r[1]]
    lines = [
        "目标主机：%s" % host,
        "扫描端口数：%d" % len(results),
        "开放端口数：%d" % len(opened),
        "",
    ]
    if opened:
        lines.append("端口        状态    服务")
        lines.append("-" * 40)
        for port, _, service in opened:
            lines.append("%-12d open    %s" % (port, service))
    else:
        lines.append("未发现开放端口（或主机不可达 / 被防火墙过滤）。")
    return "\n".join(lines)
