# -*- coding: utf-8 -*-
"""
子网计算模块
------------
基于 Python 标准库 ipaddress，提供 IPv4 / IPv6 地址计算与子网规划。
借鉴 NETworkManager 的 Subnet Calculator 功能。

设计要点：
  · 不使用 list(network.hosts()) 枚举全部地址，/0、/8 等大网段同样秒级返回；
  · 子网拆分使用 islice 惰性生成，避免一次性物化上百万个子网；
  · /31、/32（以及 IPv6 的 /127、/128）按 RFC 3021 / 主机路由语义处理。
"""
from __future__ import annotations

import ipaddress
from itertools import islice

AnyNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network
AnyAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


def _network(ip: str, prefix_or_mask: str) -> AnyNetwork:
    """根据 IP 与前缀/掩码构造网络对象，自动识别 IPv4 / IPv6。"""
    text = (ip or "").strip()
    value = str(prefix_or_mask).strip()
    if not text:
        raise ValueError("请输入 IP 地址。")
    if not value:
        raise ValueError("请输入前缀长度或子网掩码。")
    return ipaddress.ip_network(f"{text}/{value}", strict=False)


def _usable_range(net: AnyNetwork) -> tuple[AnyAddress, AnyAddress, int]:
    """返回 (首个可用地址, 末个可用地址, 可用地址数)，不做全量枚举。"""
    last = net.network_address + net.num_addresses - 1
    if net.prefixlen >= net.max_prefixlen - 1:
        # /31、/32（IPv6 /127、/128）：全部地址均可用
        return net.network_address, last, net.num_addresses
    return net.network_address + 1, last - 1, net.num_addresses - 2


def calculate_cidr(ip: str, prefix: int) -> str:
    """根据 IP + 前缀长度计算网络信息（IPv4 / IPv6 通用）。"""
    return _format_network(_network(ip, prefix))


def calculate_mask(ip: str, mask: str) -> str:
    """根据 IP + 点分十进制子网掩码计算网络信息。"""
    return _format_network(_network(ip, mask))


def subnets_from_prefix(prefix: int, new_prefix: int, base: str = "0.0.0.0") -> str:
    """按新前缀把父网拆分为多个子网，仅展示前 64 个（惰性生成）。"""
    parent = _network(base, prefix)
    new_prefix = int(new_prefix)
    if not parent.prefixlen <= new_prefix <= parent.max_prefixlen:
        raise ValueError(
            "需满足 %d <= 新前缀 <= %d。" % (parent.prefixlen, parent.max_prefixlen)
        )
    count = 1 << (new_prefix - parent.prefixlen)
    addr_each = 1 << (parent.max_prefixlen - new_prefix)

    lines = [
        "父网：%s" % parent,
        "子网数量：%s" % format(count, ","),
        "每个子网地址数：%s" % format(addr_each, ","),
        "",
        "前 %d 个子网（共 %s 个）：" % (min(64, count), format(count, ",")),
    ]
    for sub in islice(parent.subnets(new_prefix=new_prefix), 64):
        first, last, usable = _usable_range(sub)
        lines.append(
            "  %-24s 可用 %s 个 (%s ~ %s)" % (
                str(sub), format(usable, ","), first, last
            )
        )
    if count > 64:
        lines.append("  ...（省略其余 %s 个）" % format(count - 64, ","))
    return "\n".join(lines)


def _format_network(net: AnyNetwork) -> str:
    """格式化网络摘要。所有地址范围通过整数运算得出，绝不枚举地址列表。"""
    first, last, usable = _usable_range(net)
    last_addr = net.network_address + net.num_addresses - 1
    version = net.version
    lines = [
        "地址版本      : IPv%d" % version,
        "网络地址      : %s" % net.network_address,
        ("广播地址      : %s" % last_addr) if version == 4 else ("末位地址      : %s" % last_addr),
        "子网掩码      : %s" % net.netmask,
        "反掩码(wildcard): %s" % net.hostmask,
        "CIDR 表示     : %s" % net,
        "前缀长度      : /%d" % net.prefixlen,
        "地址总数      : %s" % format(net.num_addresses, ","),
        "可用地址数    : %s" % format(usable, ","),
        "第一个可用IP  : %s" % first,
        "最后一个可用IP: %s" % last,
    ]
    if net.prefixlen == net.max_prefixlen:
        lines.append("提示：这是单台主机地址（IPv4 /32、IPv6 /128）。")
    elif net.prefixlen == net.max_prefixlen - 1:
        lines.append(
            "提示：/31（IPv6 /127）常用于点到点链路，两个地址均可用（RFC 3021）。"
        )
    return "\n".join(lines)


def ip_class(ip: str) -> str:
    """判断 IP 类别；IPv6 给出地址类型与压缩/展开形式。"""
    addr = ipaddress.ip_address((ip or "").strip())
    if addr.version == 6:
        if addr.ipv4_mapped:
            scope = "IPv4 映射地址（::ffff:x.x.x.x）"
        elif addr.is_loopback:
            scope = "回环地址"
        elif addr.is_link_local:
            scope = "链路本地地址"
        elif addr.is_private:
            scope = "唯一本地地址 ULA / 私有地址"
        elif addr.is_multicast:
            scope = "组播地址"
        elif addr.is_unspecified:
            scope = "未指定地址 ::"
        elif addr.is_global:
            scope = "全球单播地址"
        else:
            scope = "特殊用途地址"
        return (
            "IP：%s\n"
            "版本：IPv6\n"
            "压缩形式：%s\n"
            "展开形式：%s\n"
            "范围：%s\n"
            "IPv4 映射：%s" % (
                addr, addr.compressed, addr.exploded, scope,
                str(addr.ipv4_mapped) if addr.ipv4_mapped else "否"
            )
        )

    first = int(str(addr).split(".")[0])
    if addr.is_private:
        scope = "私有地址"
    elif addr.is_loopback:
        scope = "回环地址"
    elif addr.is_link_local:
        scope = "链路本地"
    elif addr.is_multicast:
        scope = "组播地址"
    elif addr.is_reserved:
        scope = "保留地址"
    else:
        scope = "公网地址"
    if 1 <= first <= 127:
        cls = "A 类（127 保留作回环）" if first == 127 else "A 类"
    elif 128 <= first <= 191:
        cls = "B 类"
    elif 192 <= first <= 223:
        cls = "C 类"
    elif 224 <= first <= 239:
        cls = "D 类(组播)"
    elif 240 <= first <= 255:
        cls = "E 类(实验)"
    else:
        cls = "未知"
    return "IP：%s\n版本：IPv4\n类别：%s\n范围：%s" % (addr, cls, scope)


def ipv6_format(ip: str) -> str:
    """IPv6 地址的压缩/展开/类型速查。"""
    addr = ipaddress.IPv6Address((ip or "").strip())
    flags = []
    if addr.is_loopback:
        flags.append("回环")
    if addr.is_link_local:
        flags.append("链路本地")
    if addr in ipaddress.IPv6Network("fc00::/7"):
        flags.append("ULA 唯一本地")
    if addr in ipaddress.IPv6Network("2001:db8::/32"):
        flags.append("文档示例地址(RFC3849)")
    elif addr.is_private and not flags:
        flags.append("私有/保留")
    if addr.is_multicast:
        flags.append("组播")
    if addr.is_global:
        flags.append("全球单播")
    if addr.is_unspecified:
        flags.append("未指定")
    mapped = addr.ipv4_mapped
    if mapped:
        flags.insert(0, "IPv4 映射")
    return (
        "输入地址    : %s\n"
        "压缩形式    : %s\n"
        "展开形式    : %s\n"
        "地址类型    : %s\n"
        "IPv4 映射   : %s" % (
            ip.strip(), addr.compressed, addr.exploded,
            " / ".join(flags) or "特殊用途",
            str(mapped) if mapped else "否",
        )
    )
