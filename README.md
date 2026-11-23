# NetToolbox · 网络工具箱 v2.0

跨平台的图形化网络诊断工具箱，重点面向 Windows 用户。借鉴 GitHub 同类项目 **BornToBeRoot/NETworkManager**（8.9k stars，C#/WPF，GPLv3）的功能矩阵与「统一界面 + 命令工具」设计理念，用 Python 重新实现，可跨平台运行并打包为 Windows `.exe`。

## 一、调研结论（为什么这样选型）

按 star 排序检索 GitHub 上「network toolbox / network tools windows / network utility gui」等关键词：

| 项目 | Stars | 语言 | 契合度说明 |
|------|-------|------|-----------|
| [GyulyVGC/sniffnet](https://github.com/GyulyVGC/sniffnet) | 43.1k | Rust | 流量监控工具，非命令工具箱 |
| [jason5ng32/MyIP](https://github.com/jason5ng32/MyIP) | 12.4k | JS | Web 版 IP 工具箱，非桌面程序 |
| **BornToBeRoot/NETworkManager** | **8.9k** | C# | **Windows 桌面网络工具箱标杆，最契合** |
| [lissy93/networking-toolbox](https://github.com/lissy93/networking-toolbox) | 2.7k | Svelte | 100+ 在线工具，Web 形态 |

选定 NETworkManager 作为设计参考，用 Python + tkinter 实现等价工具箱，并补充「路由知识查阅」与「IPv6 支持」。

## 二、功能

### 1. 网络命令（图形化）
Ping、路由追踪、DNS 查询（A/AAAA/CNAME/MX/NS/PTR/SOA/TXT/SRV）、域名正反向解析、ipconfig、netstat、ARP 缓存、IPv4/IPv6 路由表、本机概览（含 IPv4/IPv6 出口地址与 DNS 服务器）。耗时命令可在执行中取消。

### 2. 网络工具
- **子网计算器**：IPv4 / IPv6 CIDR、掩码、反掩码、末位地址、可用地址范围
- **子网拆分**：按新前缀拆分父网，惰性生成避免大网段卡死
- **IP 类别判断**：IPv4 A/B/C/D/E 类、公私有、回环/组播；IPv6 类型判断
- **IPv6 地址速查**：压缩 / 展开形式、地址类型、IPv4 映射识别
- **TCP 端口扫描**：并发检测、常见服务识别、可中途停止、扫描前授权确认

### 3. 诊断工具（v2.0 新增）
- **HTTP 响应头检测**：状态码、响应头、耗时，HEAD 失败自动回退 GET
- **WHOIS 查询**：自动跟随 IANA → 注册局 → 注册商两级转介
- **批量连通性测试**：多主机 × 多端口 TCP 连通矩阵，支持中途取消

### 4. 知识查阅
29 篇结构化知识条目，6 大类，支持分类浏览与全文检索：

- **网络入门**：IP 地址、子网掩码、网关、DNS、端口、TCP/UDP、HTTP/HTTPS、MAC、NAT、DHCP、网络质量指标、故障排查
- **路由基础**：路由表与决策、最长前缀匹配、静态/动态路由、AD 与 Metric
- **路由协议**：OSPF、BGP、RIP、重分发与汇总
- **子网与地址**：CIDR/VLSM、私有与特殊地址
- **TCP/IP 基础**：协议与端口、三次握手四次挥手、ARP 与 ICMP
- **IPv6（新增）**：地址表示与结构、地址类型与子网划分、NDP 与 IPv6 路由、双栈与过渡技术

### 5. 体验增强
- **中文说明栏**：网络命令 / 网络工具 / 诊断工具右侧均有说明，点击哪个按钮就只显示那一项，解释它怎么用、返回结果各字段是什么意思；未操作时显示简短总览。
- **渐变 + 斜纹格子背景**：采用加深的「柠檬青」方案（柠檬黄 → 薄荷青，草绿主色）的窗口渐变底，叠加斜纹与细格线点缀 + 浅色卡片；仅保留浅色主题，结果输出框维持深色终端风格。
- 结果一键复制 / 导出为 txt、命令取消、主机输入历史、`~/.nettoolbox.json` 保存设置。

## 三、运行

需要 Python 3.8+（仅用标准库，无第三方运行时依赖；部分系统需单独安装 tkinter）。

```bash
cd NetToolbox
python main.py
```

## 四、打包为 Windows exe

在 Windows 上双击 `build.bat`（自动选择带 tkinter 的 Python 并安装 PyInstaller），或手动执行：

```bat
pip install pyinstaller
pyinstaller -F -w --clean -n NetToolbox main.py
```

产物：`dist/NetToolbox.exe`（单文件，约 12 MB，无需安装 Python）。

> 若默认 `python` 缺少 tkinter，脚本会自动尝试 `py -3`；两者都没有时需先安装完整版 Python。

## 五、项目结构

```
NetToolbox/
├── main.py                   # 程序入口
├── build.bat                 # Windows 打包脚本
├── requirements.txt          # 依赖说明（运行时无第三方依赖）
├── core/
│   ├── commands.py           # 系统网络命令封装 + 进程取消 + 本机概览
│   ├── subnet.py             # IPv4/IPv6 子网计算（常数时间求地址范围）
│   ├── portscan.py           # 并发端口扫描（支持取消）
│   └── diagnostics.py        # HTTP / WHOIS / 批量连通性（v2.0 新增）
├── knowledge/
│   └── data.py               # 29 篇知识条目 + 搜索
└── ui/
    ├── main_window.py        # 主界面（5 个标签页 + 渐变 + 斜纹格子背景）
    └── help_texts.py         # 中文用法 / 真实返回示例与字段解读
```

## 六、v2.0 变更要点

1. **修复严重性能缺陷**：原 `list(network.hosts())` 在 `/8` 等大网段会耗尽内存；现改用整数运算，任意前缀秒级返回；子网拆分改为惰性生成。
2. **补齐 IPv6**：子网计算、地址类型、路由表、本机出口地址、知识库全面支持 IPv6。
3. **修正常见错误**：127.x 归为 A 类回环；IP 输入优先反向解析；DNS 记录类型可选；队列消息与按钮状态边界处理。
4. **新增诊断工具**：HTTP 头、WHOIS（两级转介）、批量连通矩阵。
5. **体验增强**：复制/导出/清空、命令取消、输入历史持久化（仅浅色主题）。
6. **中文用法说明**：三个功能区右侧增加说明栏，按按钮切换、只显示当前命令/工具的用法、返回字段含义和常见误区。
7. **界面与知识扩充**：窗口改为加深的柠檬青渐变背景（叠加斜纹格子）；知识库由 17 篇增至 29 篇，新增「网络入门」12 篇；修正 IPv6 文档示例地址的类型判断。

## 七、说明

- 网络命令通过子进程调用系统原生命令，输出即系统真实结果；耗时命令在后台线程执行，不卡顿界面。
- 地址范围通过整数运算得出，不枚举地址列表；`/31`、`/127` 按 RFC 3021 处理为两个可用地址。
- 端口扫描基于 TCP connect()，WHOIS 走 43 端口；**请仅在授权范围内的网络上使用**。
- 本项目为学习/演示用途；NETworkManager 遵循 GPLv3，其设计思想仅供借鉴。

## 八、GitHub 同步

- 云端仓库：<https://github.com/mafaliang/Python>（公开仓库），**本项目源码即仓库根目录**，无子目录层级。
- 仅同步源码与文档；`build/`、`dist/`、`__pycache__`、`.spec`、`.nettoolbox.json` 已由 `.gitignore` 排除。
- 本地目录：
  - **实际运行/改代码**：`C:\Users\lenovo\Desktop\NetToolbox`（改完在本地验证效果）。
  - Git 工作副本：`D:\WorkBuddy\2026-11-23-10-46-25\_github_sync`（含 `.git`，源码在根目录）。
  - 资料库有 zip 备份。
- 换机恢复：`git clone https://github.com/mafaliang/Python.git`，克隆后根目录即本项目源码，直接 `py -3 main.py` 运行。

### 更新与推送流程

1. 改代码：在桌面副本 `C:\Users\lenovo\Desktop\NetToolbox` 修改并本地验证。
2. 同步到 Git 副本：把改动文件复制到 `_github_sync\` 同名路径（改 README 时别漏）。
3. 提交并推送（在 `_github_sync` 根目录执行）：
   ```bat
   git add .
   git commit -m "变更说明"
   git -c http.sslBackend=openssl -c http.version=HTTP/1.1 push origin main
   ```

### 认证与网络排障（重要）

- **认证用 PAT，不用连接器**：WorkBuddy 的 GitHub 连接器 MCP 无 contents 写权限（403/401），推送走本地 git CLI + Personal Access Token。
- **PAT 配置**：GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens，Resource owner 选 `mafaliang`，Repository access 勾选 `Python`，权限 `Contents: Read and write`。生成后写入 Windows 凭据管理器条目 `git:https://github.com`（用户名 `mafaliang`，密码 = token）。
- **CMD 找不到 git**：WorkBuddy 自带便携版 git 不在系统 PATH。用完整路径 `G:\HRSoftstore\Install\WorkBuddy\resources\vendor\PortableGit\mingw64\bin\git.exe`，或在 WorkBuddy 的 Bash 里执行。
- **代理导致推送失败**：环境 `HTTP(S)_PROXY` 指向 WorkBuddy 内部代理（端口会变），默认 schannel 后端会报 `schannel: failed to receive handshake`、`CONNECT tunnel failed 502` 或 `Empty reply from server`。推送命令固定加 `-c http.sslBackend=openssl -c http.version=HTTP/1.1`（见上）。绕过代理直连通常更慢或超时，不建议。
- **校验远程**：`git log -1 origin/main` 看提交；或访问 `https://raw.githubusercontent.com/mafaliang/Python/main/ui/main_window.py` 确认内容。远程与本地仅 CRLF/LF 行尾差异属正常。
