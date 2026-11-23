# -*- coding: utf-8 -*-
"""
网络诊断扩展模块
----------------
  · HTTP 响应头检测
  · WHOIS 域名 / IP 信息查询
  · 批量主机 × 端口连通性测试

仅使用标准库。所有功能都由用户主动触发，请仅在授权范围内使用。
"""
from __future__ import annotations

import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from core import portscan

_UA = "NetToolbox/2.0 (+network diagnostics)"
_REFERRAL_RE = re.compile(
    r"^\s*(?:Registrar WHOIS Server|Whois Server|ReferralServer|WHOIS server|refer)\s*:\s*(\S+)",
    re.IGNORECASE | re.MULTILINE,
)


def http_headers(url: str, timeout: float = 10) -> str:
    """请求 URL 并展示响应状态、关键头字段与耗时。"""
    url = (url or "").strip()
    if not url:
        raise ValueError("请输入 URL。")
    if not url.startswith(("http://", "https://")):
        url = "http://" + url

    started = time.monotonic()
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status, headers, final_url = resp.status, resp.headers, resp.geturl()
    except urllib.error.HTTPError as exc:
        # 部分服务器不支持 HEAD，改用 GET（只读取响应头）
        if exc.code in (403, 405, 501):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": _UA})
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    status, headers, final_url = resp.status, resp.headers, resp.geturl()
            except Exception as inner:  # noqa: BLE001
                return _http_error(url, inner, started)
        else:
            return _http_error(url, exc, started)
    except Exception as exc:  # noqa: BLE001
        return _http_error(url, exc, started)

    elapsed = (time.monotonic() - started) * 1000
    lines = [
        "请求地址    : %s" % url,
        "最终地址    : %s" % final_url,
        "状态码      : %s" % status,
        "耗时        : %.1f ms" % elapsed,
        "",
        "响应头：",
    ]
    for key, value in headers.items():
        lines.append("  %-24s %s" % (key, value))
    return "\n".join(lines)


def _http_error(url: str, exc: Exception, started: float) -> str:
    elapsed = (time.monotonic() - started) * 1000
    detail = getattr(exc, "reason", None) or exc
    return (
        "请求地址    : %s\n"
        "结果        : 失败\n"
        "错误        : %s\n"
        "耗时        : %.1f ms" % (url, detail, elapsed)
    )


def _whois_query(query: str, server: str, timeout: float = 8) -> str:
    with socket.create_connection((server, 43), timeout=timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall((query + "\r\n").encode("utf-8", errors="replace"))
        chunks = []
        while True:
            try:
                data = sock.recv(8192)
            except socket.timeout:
                break
            if not data:
                break
            chunks.append(data)
            if sum(len(c) for c in chunks) > 200_000:
                break
    return b"".join(chunks).decode("utf-8", errors="replace")


def whois(target: str, timeout: float = 8) -> str:
    """查询域名 / IP 的 WHOIS 信息，自动跟随一次 referral 服务器。"""
    target = (target or "").strip()
    if not target:
        raise ValueError("请输入域名或 IP。")
    parsed = urllib.parse.urlparse(target if "://" in target else "//" + target)
    target = parsed.hostname or target

    server = "whois.iana.org"
    text = _whois_query(target, server, timeout)
    visited = {server}
    # 最多跟随两级：IANA -> 注册局 -> 注册商
    for _ in range(2):
        match = _REFERRAL_RE.search(text)
        if not match:
            break
        referral = match.group(1)
        referral = re.sub(r"^[a-z]+://", "", referral, flags=re.IGNORECASE)
        referral = referral.split("/")[0].split(":")[0].strip()
        if not referral or referral.lower() in visited:
            break
        try:
            text = _whois_query(target, referral, timeout)
            server = referral
            visited.add(referral.lower())
        except OSError:
            break  # 跟随失败时保留上一级应答

    text = text.strip()
    if len(text) > 30_000:
        text = text[:30_000] + "\n...（结果过长，已截断）"
    return "查询对象    : %s\nWHOIS 服务器: %s\n%s\n%s" % (
        target, server, "-" * 48, text or "[空响应]"
    )


def bulk_connect(hosts_text: str, ports_text: str, timeout: float = 0.8,
                 workers: int = 60, progress=None, cancel_event=None) -> str:
    """批量测试「多个主机 × 多个端口」的 TCP 连通性，输出矩阵表。"""
    hosts = []
    for part in re.split(r"[,，\s]+", hosts_text or ""):
        part = part.strip()
        if part and part not in hosts:
            hosts.append(part)
    ports = portscan.parse_ports(ports_text)
    if not hosts or not ports:
        raise ValueError("请至少输入一个主机和一个端口。")

    def probe(host: str, port: int) -> tuple[str, int, bool]:
        if cancel_event is not None and cancel_event.is_set():
            return host, port, False
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return host, port, True
        except OSError:
            return host, port, False

    results: dict[tuple[str, int], bool] = {}
    total = len(hosts) * len(ports)
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(probe, host, port) for host in hosts for port in ports
        ]
        for fut in as_completed(futures):
            host, port, ok = fut.result()
            results[(host, port)] = ok
            done += 1
            if progress:
                progress(done, total)

    name_width = max(16, min(32, max(len(h) for h in hosts) + 2))
    header = ("%-*s" % (name_width, "主机")) + "".join(
        "%9d" % p for p in ports
    )
    lines = [
        "TCP 连通性矩阵（open = 可连接，.- = 不可连接）",
        "主机数：%d  端口数：%d  检测数：%d" % (len(hosts), len(ports), total),
        "",
        header,
        "-" * len(header),
    ]
    for host in hosts:
        row = "%-*s" % (name_width, host)
        row += "".join(
            "%9s" % ("open" if results.get((host, p), False) else "  .")
            for p in ports
        )
        lines.append(row)

    if cancel_event is not None and cancel_event.is_set():
        lines.append("")
        lines.append("[提示] 检测已被用户取消，以上为部分结果。")
    lines.append("")
    lines.append("提示：请仅在自己拥有或已获授权的网络上使用。")
    return "\n".join(lines)
