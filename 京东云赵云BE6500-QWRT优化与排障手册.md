# 京东云 赵云 BE6500（QWRT）系统优化与排障手册

> 机型：京东云 赵云 BE6500（RE-CS-06，IPQ5322 + QCN9224）
> 固件：QWRT 25.12.2 / R26.9.18（QSDK 12.5，内核 5.4.213）
> 本文基于 2026-10-25 的一次完整只读排查 + 分步落地实测整理，所有数值均为该机快照。
> 刷机流程见仓库根目录 [README.md](README.md)；本文只讲**刷完之后**的系统优化、排障与平台陷阱。

---

## 目录

- [0. 一页速查](#0-一页速查)
- [1. 平台画像与硬约束](#1-平台画像与硬约束)
- [2. 方法论：只读侦察 → 验证 → 最小改动](#2-方法论只读侦察--验证--最小改动)
- [3. 实测结论与已落地优化](#3-实测结论与已落地优化)
- [4. NSS / ECM 深水区：为什么这台机器不建议开硬件加速](#4-nss--ecm-深水区为什么这台机器不建议开硬件加速)
- [5. Overlay 扩容的三条路线](#5-overlay-扩容的三条路线)
- [6. 平台陷阱清单](#6-平台陷阱清单)
- [7. 运维命令速查](#7-运维命令速查)
- [8. 变更记录、备份与回滚](#8-变更记录备份与回滚)
- [9. 参考来源](#9-参考来源)

---

## 0. 一页速查

| 项目 | 结论 | 依据 |
|---|---|---|
| DNS 境外 DoT | 该网络无境外直连，`tls://8.8.8.8:853` 全部超时 | SYN_SENT、mosdns `i/o timeout`、`wget dns.google` 超时 |
| DNS 境外上游 | 改为国内 DoH：`dns.alidns.com` + `doh.360.cn` | 实测 200，错误计数 0 |
| `doh.pub` | curl 可通，但 mosdns 的 RFC8484 请求被持续 RST | `connection reset by peer`，已剔除 |
| 广告规则 | 4 个源全部 0 字节（GitHub raw 不可达） | `wc -l` 全 0，`adlist_update` 失败 |
| 广告规则镜像 | jsdelivr（gcore）+ ghfast；AdRules 5.8MB 走 ghfast | 实测下载成功，44 万条 |
| 软件 flow offload | **本固件未编译** `xt_FLOWOFFLOAD` | fw3 reload 警告、0 条规则、无模块 |
| NSS / ECM | **不建议开启**（同平台有 D 状态 / conntrack 缺陷） | 见第 4 节 |
| eMMC swap | 关闭，只留 443MB zram | `pswpin/pswpout=0`、zram 未用、MemAvailable 450MB |
| swappiness | 设 10，但会被 `autocore` 覆盖回 100 | `/etc/init.d/autocore` 第 10 行 |
| 脏页 | `dirty_ratio=15`、`dirty_background_ratio=5` | 原为 50/1，SMB 写入易抖动 |
| 上行整形 | 试过 cake 15M，**已撤掉** | P2P 限速判断下会误伤普通上传；无 WebUI |
| 空转服务 | 关闭 ipsec / zerotier / msd_lite / openvpn / ddns | 端口与进程收敛 |
| Overlay | 21MB = p23 尾部 24.4MiB，**无法在线扩容** | `losetup -a` 显示 offset |
| p26 | 原厂京东云插件分区（1GB，856MB 空闲） | 内容为 jdc_docker/jdcbox 等 |
| opkg | 软件源签名失效，当前装不了包 | `Signature check failed` |

---

## 1. 平台画像与硬约束

### 1.1 硬件与系统

| 项 | 值 |
|---|---|
| SoC | IPQ5322 / IPQ53xx，4 × Cortex-A53，1.1–1.5GHz（ondemand） |
| 内存 | 887,912 kB（约 867 MiB） |
| 存储 | eMMC 约 116 GiB，GPT，29 个分区 |
| 无线 | QCN9224，Wi-Fi 7；2.4G HT20 ch11 21dBm，5G HT80 ch149 24dBm，`country=US` |
| 固件 | QWRT 25.12.2 R26.9.18（QSDK 12.5），内核 5.4.213 |
| 温度 | 空闲约 59.5°C，正常 |

### 1.2 网络现状

- WAN：PPPoE，运营商给的是 **CGNAT 私网地址，没有公网 IPv4**；IPv6 为公网地址 + `/56` PD。
- LAN：`192.168.10.1/24`，DHCP 池 `100–249`，约 15 台在线设备（含米家/追觅/ESP 类 IoT）。
- WAN 网口协商 1000Mb/s（2.5G 口未跑满，取决于光猫/网线）；LAN 交换口为千兆。
- PPPoE MTU 1492，MSS clamp 正常。
- NTP：路由器作为 LAN 时间源（`enable_server=1`），`/etc/firewall.user` 把 LAN:123 重定向到本机。

### 1.3 eMMC 分区用途（实测）

| 分区 | 名称 | 大小 | 用途 |
|---|---|---|---|
| p23 | `rootfs` | 122 MiB | squashfs 根文件系统；**overlay 在它的尾部**（offset 102432768，24.4MiB） |
| p24 | `rootfs_1` | 122 MiB | 备用 rootfs 槽 |
| p26 | `plugin` | 1 GiB ext4 | 原厂京东云插件/边缘计算数据区，已用约 90MB，空闲约 856MB |
| p27 | `log` | 128 MiB ext4 | 系统日志归档（`syslog.*.gz`），已用约 35MB |
| p28 | `swap` | 1 GiB | 交换分区；本次已禁用，可改作他用 |
| p29 | `storage` | 约 110 GiB ext4 | 数据盘，几乎为空 |

> 结论：**overlay 不是独立分区**，而是 p23 里 squashfs 之后的剩余空间。p23 的结束 LBA 决定了 overlay 上限（约 24MiB），不改 GPT 就无法变大。

### 1.4 三条硬约束（决定所有优化取舍）

1. **本固件没有软件 flow offload**：`xt_FLOWOFFLOAD` 未编译，`firewall.defaults.flow_offloading=1` 只会让 fw3 在 reload 时打印 `requires unavailable target extension FLOWOFFLOAD, disabling`。
2. **NSS/ECM 不可用（有缺陷）**：同平台（IPQ53xx + 5.4.213）实测开启后出现 D 状态 workqueue 与 conntrack 统计不同步，详见第 4 节。
3. **overlay 无法在线扩容**：见第 5 节。

---

## 2. 方法论：只读侦察 → 验证 → 最小改动

这部分是把 `openwrt-router-ops` skill 的原则与本机实践合并后的可复用流程。

### 2.1 六步闭环

1. **只读侦察**：先快照，不改任何配置。
   ```bash
   uci export > /tmp/uci-export-$(date +%s).txt
   ps w; netstat -tulpn; iptables-save | head -80
   cat /proc/net/nf_conntrack | head -20
   ```
2. **验证可疑断言**：不要凭教程/记忆下结论，能测就测。
   - 镜像能不能下？`wget/curl` 实测。
   - DoH 能不能用？带 RFC8484 查询实测。
   - 端口有没有人监听？`netstat` 实测。
3. **确认“层级真的生效”再报告**：配置项存在 ≠ 功能启用。
   - `adblock.global.adb_enabled=0` → 模块等于不存在。
   - `openclash.config.enable=0` → 进程不会起。
   - `turboacc.global.set=1` → 不代表有 offload 规则。
4. **改动前备份到持久分区**：`/tmp` 是 tmpfs，重启即丢；备份放 `/root/` 或 p26/p29。
5. **最小改动 + 单一入口**：一次只改一件事，能用 UCI 就不手改生成文件；改完立即验证。
6. **回归测试**：DNS、ping、下载、端口、日志、真实重拨/重启。**持久化必须用真实 ifdown/ifup 或重启验证**，不能只看脚本存在。

### 2.2 证据链：四重交叉验证

判断“硬件加速是否真的在工作”，只看 UCI 会被骗。至少交叉四种证据：

| 层 | 命令 | 期望 |
|---|---|---|
| 配置 | `uci show turboacc` | 选项值 |
| 模块 | `lsmod \| grep ecm` | 模块已加载 |
| 规则 | `iptables-save \| grep -c FLOWOFFLOAD` | 规则存在 |
| 流量 | `/proc/net/nf_conntrack` 是否有 `OFFLOAD` 标记 | 真实卸载 |

本机四项全部为“否”，所以“开了加速”只是配置幻觉。

### 2.3 常见误判（含本次自我纠正）

| 误判 | 事实 |
|---|---|
| “境外 DoT 只是慢” | 实测是 TCP 853 全阻断，SYN_SENT 堆积，不是慢 |
| “doh.pub 可用所以 mosdns 可用” | curl 200，但 mosdns 的 RFC8484 请求持续被 RST，二者行为不同 |
| “4 个广告源已配置” | 文件全部 0 字节，下载从未成功 |
| “开 NSS/ECM 一定更快” | 同平台实测有 D 状态与 conntrack 缺陷，1G WAN 下关闭反而稳定且吞吐相当 |
| “swap 越大越安全” | 该机 eMMC swap 从未使用（`pswpout=0`），开启只会增加磨损与优先级问题 |
| “配置了 DNS 分流就一定工作” | 分流依赖的境外上游本身不可达 |

### 2.4 安全边界

- 诊断与建议可以自由做；**写入必须显式确认**，并保留回滚锚点。
- 平台约束优先于“通用最佳实践”（例如 NSS 与透明代理互斥）。
- 不把口令、PSK、公网地址、MAC/SN 写进任何文档或仓库。

---

## 3. 实测结论与已落地优化

### 3.1 DNS：把境外上游换成国内 DoH

**问题**：mosdns `remote_dns` 原为 `tls://8.8.8.8 / 8.8.4.4 / 1.1.1.1`，日志持续：

```
forward_remote upstream error ... i/o timeout
```

`netstat` 可见大量 `->8.8.8.8:853 SYN_SENT`；实测 `https://dns.google/dns-query`、`https://1.1.1.1/dns-query` 均超时，`doh.pub` 正常。结论：**该网络没有可用的境外 DNS 直连**，保留境外上游只会让每次查询空等 5 秒。

**处理**：

```bash
uci -q delete mosdns.config.remote_dns
uci add_list mosdns.config.remote_dns='https://dns.alidns.com/dns-query'
uci add_list mosdns.config.remote_dns='https://doh.360.cn/dns-query'
uci commit mosdns
/etc/init.d/mosdns restart
/usr/share/mosdns/mosdns.sh flush
```

**验证**：

```bash
nslookup pypi.org 127.0.0.1        # 应返回 A 记录
nslookup www.baidu.com 192.168.10.1
grep -c 'upstream error' /var/log/mosdns.log   # 应为 0（或不再增长）
```

实测：pypi → `151.101.x`，github → `20.205.243.166`，baidu → `180.101.x`，mijia → `110.43.87.16`，错误计数 0。

> busybox `nslookup` 在 AAAA 为空时会打印 `*** Can't find X: No answer`，这不等于解析失败；看是否返回了 `Address` 行即可。

**取舍**：境外域名现在由国内 DoH 解析，可能拿到污染结果；但本网络本来也访问不了境外站点。若以后上了代理，应把 DNS 交给代理侧（fake-ip / 经代理的 DoH），而不是再改回 8.8.8.8。

### 3.2 广告规则：4 个源换成可用镜像

**问题**：`/etc/mosdns/rule/adlist/` 下 4 个文件全部 0 字节。原因：源是 `raw.githubusercontent.com`，本网络不可达；`github_proxy` 只对 geo 更新生效，且当时指向的镜像也不通。

**处理**：`ad_source` 改为

```text
geosite.dat
https://gcore.jsdelivr.net/gh/TG-Twilight/AWAvenue-Ads-Rule@main/Filters/AWAvenue-Ads-Rule-Mosdns_v5.txt
https://gcore.jsdelivr.net/gh/privacy-protection-tools/anti-AD@master/anti-ad-domains.txt
https://ghfast.top/https://raw.githubusercontent.com/Cats-Team/AdRules/main/mosdns_adrules.txt
https://gcore.jsdelivr.net/gh/neodevpro/neodevhost@master/domain
```

同时把 `github_proxy` 改为 `https://ghfast.top`，然后：

```bash
/usr/share/mosdns/mosdns.sh adlist_update
```

**结果**：987 + 112,082 + 115,793 + 211,198 = **440,060 行**，共约 10.2MB。`geosite_category-ads-all.txt`（720 条）作为兜底也在工作。

**注意**：
- AdRules 的 `mosdns_adrules.txt` 有 5.8MB，jsdelivr 会拒绝，必须走 ghfast。
- 规则占的是 **overlay**（`/etc/mosdns/rule/adlist`），本次让 overlay 从 14.8MB 剩余降到 **4.9MB**。若空间紧张，优先删最大的 AdRules（可释放约 5.9MB）。
- 每日 2:00 的 `mosdns.sh geodata` cron 会重新下载并重启 mosdns；镜像失效时规则会重新变 0，需定期看 `wc -l`。

### 3.3 内存与 swap：关掉 eMMC swap，只留 zram

**证据**：

```text
pswpin 0
pswpout 0
SwapTotal 443388 kB, SwapFree 443388 kB      # zram 一点没用
MemAvailable 450164 kB                        # 余量充足
```

**处理**：

```bash
uci set fstab.@swap[0].enabled='0'
uci commit fstab
swapoff /dev/mmcblk0p28
```

**为什么不再开**：
- 该 swap 从未被使用，开着只是“理论安全”。
- 原优先级里 eMMC（-2）高于 zram（-3），真到换页会优先写闪存，增加磨损与 IO 卡顿。
- 888MB 内存 + 443MB zram 对当前负载（mosdns、Samba、无 Docker）足够。

**若将来真的缺内存**：优先调大 zram（`system.@system[0].zram_size_mb`），而不是重开 eMMC swap。

### 3.4 swappiness：会被 `autocore` 覆盖

`/etc/sysctl.d/99-custom.conf` 里写了 `vm.swappiness=10`，但实际一直是 100：

```text
/etc/init.d/autocore:  echo '100' > /proc/sys/vm/swappiness
```

`autocore` 的 `START=95`，晚于 sysctl（`START=11`），所以每次启动都会覆盖。处理方式是在 `/etc/rc.local`（`S95done`，晚于 autocore）末尾补一行：

```bash
sysctl -w vm.swappiness=10
```

> 同文件里的 `vfs_cache_pressure=100` 生效，可作为“sysctl 确实加载过、只是被后面覆盖”的旁证。

### 3.5 脏页回写：降低 SMB 抖动

原值：`vm.dirty_ratio=50`、`vm.dirty_background_ratio=1`。在 888MB 内存上意味着最多可积累约 440MB 脏页，SMB 大文件拷贝时突发落盘，易卡顿、掉电风险高。

改为：

```text
vm.dirty_ratio=15
vm.dirty_background_ratio=5
```

写入 `/etc/sysctl.d/99-custom.conf` 后 `sysctl -p`，实测即时生效。

### 3.6 空转服务与残留 include/zone

关闭并禁用：

```bash
for s in ipsec zerotier msd_lite openvpn ddns; do
  /etc/init.d/$s stop
  /etc/init.d/$s disable
done
```

删除残留：

```bash
uci -q delete firewall.openclash      # 指向不存在的 /var/etc/openclash.include
uci -q delete firewall.zerotier       # zerotier 已禁用
uci -q delete firewall.openvpn        # 1194/tcp+udp 放行，但服务未启用
uci -q delete firewall.vpntowan
uci -q delete firewall.vpntolan
uci -q delete firewall.lantovpn
uci -q delete firewall.vpn            # tun0 实际不存在
uci -q delete network.vpn0
uci commit firewall; uci commit network
/etc/init.d/firewall reload
```

**验证**：

```bash
iptables-save | grep -cE 'dport 1194|zone_vpn'   # 0
uci show firewall | grep -cE 'openclash|zerotier' # 0
ip link | grep -c ipsec0                          # 0
netstat -tulpn | grep LISTEN
```

清理后仍保留的监听：21（vsftpd）、22（dropbear）、53（dnsmasq）、80/443（uhttpd）、139/445（smbd）、3702/5355（wsdd2）、5000（miniupnpd）、5335（mosdns）、7681（ttyd）、9091（mosdns API）。

> 这些是按需求保留的；其中 vsftpd 与 ttyd 是否保留，按各自使用情况决定。

### 3.7 QoS：为什么试了又关掉

**背景**：上行长期接近跑满时会有 bufferbloat（延迟从几 ms 涨到几百 ms）。标准做法是用 cake 把出口整形到签约上行的 85–90%。

**曾部署**（仅上行）：

```bash
tc qdisc replace dev pppoe-wan root cake \
  bandwidth 15Mbit overhead 8 nat dual-srchost ack-filter
```

实测：
- 下载不受影响：部署前 31.6 / 32.4 MB/s，部署后 35.1 / 24.2 / 19.5 MB/s（单连接镜像波动）；
- ping 223.5.5.5：6.28ms → 6.76ms，无实质变化；
- 真实 PPPoE 重拨后队列自动恢复；
- 饱和时 cake 丢包约 42%（这是整形的工作方式，不是故障）。

**为什么撤掉**：
- 该机上行疑似**只对 P2P 限速**（qB 多线程仍只有 1–2MB/s），若一刀切压到 15M，会误伤网盘备份、视频上传等非 P2P 流量。
- 没有 WebUI（原生 tc 方案，不是插件；且 opkg 签名失效，`luci-app-sqm` 装不上），开关不方便。
- 若确认签约上行明显高于 16M，正确做法是按“实测上行 × 0.9”设值，而不是按 P2P 表现设值。

**结论**：当前保持默认 `fq_codel`。如果以后要做，先确认真实上行（PC 端 speedtest），再按 0.9 倍配置；只想限制 P2P 的话，应按设备/端口分类，而不是全局整形。

### 3.8 本次未改（风险登记）

按用户要求保留，未做修改，但记录在此：

- root 与 Wi-Fi 口令强度、SSH 口令登录、Samba 匿名 + `guest account=root` 与各分区可写共享；
- `firewall.defaults.input='ACCEPT'`（默认应为 REJECT）；
- `dnsmasq rebind_protection='0'`；
- mosdns `:5335` 与 API `0.0.0.0:9091` 监听所有接口；
- vsftpd、ttyd、miniupnpd 的暴露面。

这些属于安全加固项，改动前应单独评估并备份。

---

## 4. NSS / ECM 深水区：为什么这台机器不建议开硬件加速

### 4.1 先厘清概念

- **NSS / PPE**：高通 SoC 内的硬件包处理引擎，能把已建立的流转发卸载到硬件，绕过 Linux 协议栈。
- **ECM**：Enhanced Connection Manager，负责决定哪些流交给哪个加速引擎。
- **SFE**：软件快捷转发引擎（Software Fastpath Engine），仍是软件，但绕过部分协议栈。
- **本机现状**：`ecm.ko`、`ecm-wifi-plugin.ko`、`qca-nss-ppe*` 都在磁盘上，Wi-Fi 通过 `ppe_vp=active` 挂在 PPE 虚拟口上；但 **ECM 未加载**，WAN↔LAN 转发完全走 Linux 协议栈。

### 4.2 为什么 `flow_offloading` 是空设

`turboacc.config.fastpath='flow_offloading'` 看似开了软件加速，实际：

```bash
lsmod | grep -i flowoffload          # 无
iptables-save | grep -c FLOWOFFLOAD  # 0
nft list ruleset | wc -l             # 0
grep -c OFFLOAD /proc/net/nf_conntrack  # 0
```

firewall reload 时 fw3 明确报：

```text
Warning: Section 'defaults' requires unavailable target extension FLOWOFFLOAD, disabling
```

即**该固件没编译 `xt_FLOWOFFLOAD`**，选这个 fastpath 不会有任何效果。

### 4.3 开 ECM 后为什么会“两个核 D 状态、load 飙升”

这是同平台（IPQ53xx、内核 5.4.213）已被公开记录的缺陷，不是本机个例：

1. **D 状态来自 ECM 的内核工作队列**：`kworker/u8:N+ecm_sfe_ipv4_workqueue`、`..._ecm_sfe_ipv6_workqueue` 在等待设备 I/O 时进入不可中断睡眠（D）。Linux 的 loadavg **会把 D 状态任务计入**，于是出现 **load ≈ 2.0、CPU 97% idle** 的“假高负载”。GL.iNet 官方也确认 D 状态本身可能是预期行为。
2. **但它也可能是真卡死**：同型号用户实测该 workqueue 会持续 wedged——PID 轮换、`restart` 57 秒内复发、**只有 stop 才干净**；伴随路由器对自己的 LAN IP 每小时丢几十个包、`__flush_work` 内核 WARNING。关闭 ECM 后 load 0.04、丢包 0，吞吐 1077Mbps（开 ECM 约 1100Mbps，差距可忽略）。
3. **另有 PPE 前端的 conntrack 统计缺陷**：PPE 加速流的 conntrack 计数会冻结、timeout 单调衰减，UDP 约 180s、TCP 约 7440s 后被删除，NAT 映射消失——表现为游戏/会议每 3 分钟断一次、长传中断，而 ping/DNS/PPPoE 全部正常。
4. **流传的“解法”都有代价**：
   - `acceleration_engine='ppe-sfe'`：原作者可用，但另一用户 7 分钟内复发，吞吐降到 836Mbps；
   - 单用 `sfe`：修好 conntrack，但会破坏 MLO Wi-Fi 客户端（PPE-DS 绑在 wifi 上）。

### 4.4 决策树

```text
需要 >1Gbps 转发，且不需要 QoS / 透明代理 / 精确流量统计？
  ├─ 是 → 可评估 ECM，但必须先读 4.3，接受 D 状态与 conntrack 风险，并准备回滚
  └─ 否 → 保持 ECM 关闭（本机选择）
```

本机 WAN 是 1G PPPoE。本次单连接镜像测试只有 24–35MB/s（受镜像与单连接窗口限制，不代表上限）；同平台案例显示关闭 ECM 后仍可跑到约 1077Mbps。因此**关 ECM 的吞吐代价很小，换来的是稳定与 QoS 可用性**。

### 4.5 观测命令（只读）

```bash
cat /proc/loadavg
for p in /proc/[0-9]*; do
  s=$(awk '{print $3}' $p/stat 2>/dev/null)
  [ "$s" = "D" ] && cat $p/comm
done
lsmod | grep -E '^ecm|qca_nss_sfe'
cat /sys/kernel/debug/ecm/ecm_sfe_ipv4/{accelerated_count,stats_request_counter} 2>/dev/null
dmesg | grep -i 'blocked for more than'
```

判据是 **D 状态 + 实际丢包/延迟**，不是 load 数字本身。

---

## 5. Overlay 扩容的三条路线

### 5.1 先看清机制

```bash
losetup -a
# /dev/loop0: (/mmcblk0p23), offset 102432768
cat /sys/block/loop0/loop/backing_file   # /mmcblk0p23
cat /sys/block/loop0/loop/offset         # 102432768
```

overlay 是 **p23（122MiB）里 squashfs 之后的 24.4MiB 尾巴**。p23 的结束 LBA 决定上限，所以**不动 GPT 无法真正扩容**。

### 5.2 路线 A：把 p28（1GB swap）改成 overlay（推荐，风险低）

前提：swap 已关闭且从未使用（见 3.3）。步骤（需重启一次）：

```bash
mkfs.ext4 -F -L rootfs_data /dev/mmcblk0p28
mkdir -p /mnt/new && mount /dev/mmcblk0p28 /mnt/new
mkdir -p /mnt/new/upper /mnt/new/work
cp -a /overlay/upper/. /mnt/new/upper/
sync && umount /mnt/new
NEW=$(blkid -s UUID -o value /dev/mmcblk0p28)
uci set fstab.@mount[0].uuid="$NEW"
uci set fstab.@mount[0].target='/overlay'
uci set fstab.@mount[0].enabled='1'
uci -q delete fstab.@swap[0]
uci commit fstab
reboot
```

验证：`df -h /overlay` 应约 1GB，配置与已装包都在。

回滚：把 `fstab.@mount[0].uuid` 改回原 overlay UUID（见备份的 `uci-export.txt`），重启。旧的 loop0 overlay 未被破坏。

代价与注意：
- 放弃 1GB swap（本来就没用）；
- overlay 在独立分区，sysupgrade 后建议检查一次配置与包是否完整；
- 不要格式化 p26/p27/p29 来当 overlay（会丢原厂插件数据/日志/数据盘）。

### 5.3 路线 B：2G GPT（高风险，能到约 1.9GB）

`gpt_JDCloud-BE6500_2G.bin` 已用 `scripts/gpt_inspect.py` 验证：17408 字节、28 个分区、头/条目 CRC 全对、`rootfs=2048MiB`。**文件没问题**；之前“只剩空 GPT 壳”是沉心 U-Boot WebUI 只写了 GPT 头、条目未提交，不是文件坏了。可靠做法是 TTL：

```text
setenv ipaddr 192.168.1.2; setenv serverip 192.168.1.25
tftpboot 0x50000000 gpt_JDCloud-BE6500_2G.bin
mmc write 0x50000000 0 22      # 34 扇区 = 17408 字节
```

**两个必须知道的隐藏风险**：

1. **p25 factory 的 LBA 会移动**：原厂 `601122–601633` → 2G 表 `4545570–4546081`。原数据不在新位置，旧位置又会被新 rootfs 覆盖，所以刷完必须用备份还原 p25：
   ```bash
   dd if=/path/mmcblk0p25_factory.bin of=/dev/mmcblk0p25 bs=256k conv=fsync
   ```
   `0:ART`（p17）LBA 不变，是安全的。教程里“ART/factory 不用回刷”只适用于**原厂 GPT**。
2. **2G 表没有 storage**：尾部约 118GB 变成未分配，进系统后要 `cfdisk /dev/mmcblk0` 新建 p29 再 `mkfs.ext4`。

顺序铁律：**GPT → 当次刷 factory.bin → 重启**，中间不能单独重启。

### 5.4 路线 C：不动（当前选择）

- overlay 保持 21MB；用 p26（856MB 空闲）或 p29（110GB）放数据/规则/大插件；
- 若 overlay 吃紧，优先删最大的 AdRules 规则（约 5.9MB）；
- 等确实需要装大量包时再考虑 A 或 B。

---

## 6. 平台陷阱清单

| # | 现象 | 真正原因 | 证据命令 | 处置 |
|---|---|---|---|---|
| 1 | “开了 flow offload 但 CPU 没降” | 固件没编译 `xt_FLOWOFFLOAD` | `iptables-save \| grep -c FLOWOFFLOAD` | 忽略该选项，或改用 ECM（但见第 4 节） |
| 2 | 开 ECM 后 load 2.0、CPU 97% idle | ECM workqueue 进 D 状态，被 loadavg 计入 | `cat /proc/loadavg` + 找 D 状态线程 | 关 ECM；不要用 load 判断 CPU |
| 3 | 游戏/会议每 3 分钟断 | PPE 前端不同步 conntrack，UDP 180s 被删 | 看 conntrack timeout 是否单调衰减 | 关 ECM，或 `ppe-sfe`（有代价） |
| 4 | mosdns 日志刷 timeout | 境外 DoT 被阻断，不是 DNS 配置错 | `netstat \| grep 853` | 换国内 DoH |
| 5 | 广告规则不生效 | 4 个源全是 0 字节 | `wc -l /etc/mosdns/rule/adlist/*` | 换镜像并手动 `adlist_update` |
| 6 | 改了 swappiness 无效 | `autocore` 在 S95 覆盖为 100 | `grep -n swappiness /etc/init.d/autocore` | 写到 rc.local |
| 7 | eMMC swap 优先级高于 zram | 分区先挂载得到 -2，zram 得 -3 | `cat /proc/swaps` | 关 eMMC swap，只留 zram |
| 8 | 共享盘里出现固件分区 | Samba `autoshare=1` 自动共享所有挂载点 | `cat /var/etc/smb.conf` | 关 autoshare，只共享 p29 |
| 9 | overlay 很快满 | overlay 只有 p23 尾部 24MB | `losetup -a` | 见第 5 节 |
| 10 | 刷 2G GPT 后 MAC/SN 为空 | p25 factory 的 LBA 移动，旧数据被覆盖 | `parted unit s print` | 刷完用备份还原 p25 |
| 11 | 刷 2G GPT 后没有数据盘 | 2G 表不含 storage | `parted print` | `cfdisk` 新建 p29 + `mkfs.ext4` |
| 12 | 装不了任何包 | opkg 源签名失效 | `opkg update` | 修源签名/换源，别硬装 |
| 13 | PPPoE 重拨后 UPnP 短暂报错 | miniupnpd 拿不到新 WAN IP | `logread \| grep miniupnpd` | 瞬态，映射会自动恢复 |
| 14 | busybox `nslookup` 报 No answer | AAAA 为空时的提示噪声 | 看是否有 `Address` 行 | 不是故障 |
| 15 | Samba/FTP/WebUI 都能被匿名或弱口令进入 | 默认配置与弱口令 | `cat /var/etc/smb.conf` | 单独做安全加固（本次未改） |

---

## 7. 运维命令速查

### 7.1 系统与资源

```bash
uptime; free -m; df -h / /overlay
cat /proc/loadavg
ps w | awk '$3 ~ /D/'
cat /proc/swaps
grep -E 'pswpin|pswpout' /proc/vmstat
cat /sys/class/thermal/thermal_zone*/temp
```

### 7.2 网络与 DNS

```bash
ip -br addr; ip route
netstat -tulpn | grep LISTEN
nslookup pypi.org 127.0.0.1
nslookup www.baidu.com 192.168.10.1
grep -c 'upstream error' /var/log/mosdns.log
grep -oE '"(tls|https|quic|h3)://[^"]+"' /var/etc/mosdns.json | sort -u
```

### 7.3 无线

```bash
iw dev
iw dev ath1 station dump | grep -c '^Station'
uci show wireless
```

### 7.4 Offload / ECM

```bash
lsmod | grep -E '^ecm|qca_nss|flowoffload'
iptables-save | grep -c FLOWOFFLOAD
nft list ruleset | wc -l
grep -c OFFLOAD /proc/net/nf_conntrack
cat /sys/kernel/debug/ecm/ecm_sfe_ipv4/accelerated_count 2>/dev/null
```

### 7.5 存储与分区

```bash
losetup -a
cat /sys/block/loop0/loop/{backing_file,offset}
parted /dev/mmcblk0 unit s print
blkid
cat /etc/config/fstab
```

### 7.6 日志

```bash
logread | tail -50
dmesg | grep -iE 'error|fail|blocked for more than'
tail -50 /var/log/mosdns.log
```

---

## 8. 变更记录、备份与回滚

### 8.1 本次变更（2026-10-25）

| 类别 | 变更 | 验证 |
|---|---|---|
| DNS | `remote_dns` → alidns + 360 DoH | 解析正常，错误 0 |
| 广告 | 4 源换镜像 + `github_proxy` | 44 万条，非 0 |
| 内存 | 关闭 eMMC swap，保留 zram | 仅 zram，0 使用 |
| 内核参数 | swappiness 10、dirty 15/5 | 实时生效 |
| 服务 | 停用 ipsec/zerotier/msd_lite/openvpn/ddns | 进程/端口收敛 |
| 防火墙 | 删除 openclash/zerotier include、vpn zone、vpn0、1194 | 规则计数 0 |
| QoS | 曾部署 15M cake，后按要求撤除 | 恢复 fq_codel |

### 8.2 备份

- 建议每次改动前：`uci export > /root/owrt-backup-<ts>/uci-export.txt`，并复制将改的 `/etc/config/*`、`/etc/rc.local`、`/etc/sysctl.d/99-custom.conf`。
- **不要放 `/tmp`**（tmpfs，重启即丢）。
- 回滚文档建议与备份放在一起，逐项写命令。

### 8.3 回滚示例

```bash
# DNS / 广告
cp /root/owrt-backup-<ts>/mosdns /etc/config/mosdns
uci commit mosdns && /etc/init.d/mosdns restart

# sysctl
cp /root/owrt-backup-<ts>/99-custom.conf /etc/sysctl.d/99-custom.conf
cp /root/owrt-backup-<ts>/rc.local /etc/rc.local
sysctl -p /etc/sysctl.d/99-custom.conf

# swap
uci set fstab.@swap[0].enabled='1'; uci commit fstab; swapon /dev/mmcblk0p28

# 防火墙 / 网络
cp /root/owrt-backup-<ts>/firewall /etc/config/firewall
cp /root/owrt-backup-<ts>/network /etc/config/network
uci commit firewall; uci commit network; /etc/init.d/firewall reload
```

### 8.4 回归测试清单

- [ ] `nslookup` 国内/国外域名均有 A 记录
- [ ] `grep -c 'upstream error' /var/log/mosdns.log` 不增长
- [ ] `ping 223.5.5.5` 0 丢包、延迟正常
- [ ] 下载速率与改动前相当
- [ ] `ifdown wan; ifup wan` 后 WAN、DNS、队列/规则自动恢复
- [ ] `iptables-save` 无残留规则，端口列表符合预期
- [ ] `logread` 无新增 error
- [ ] overlay 剩余空间可接受

---

## 9. 参考来源

- 本仓库刷机教程：[README.md](README.md)（GPT / factory / 救砖 / 2G 分区）
- `openwrt-router-ops` skill：只读侦察、备份先行、平台约束优先、NSS 与透明代理互斥
- GL.iNet 论坛：Flint 3（同 IPQ53xx + 5.4.213）PPE/ECM 缺陷与 D 状态讨论
  - https://forum.gl-inet.com/t/flint-3-gl-be9300-ppe-ecm-bug-causes-packet-deaths/70449
  - https://forum.gl-inet.com/t/question-flint-3-be9300-load-average-consistently-2-0-on-idle-despite-0-actual-cpu-usage-hardware-acceleration-enabled/70640
- OpenWrt 文档：extroot / overlay、SQM、dnsmasq、fw3 行为
- 本机实测日志与 UCI 快照（2026-10-25，QWRT R26.9.18）

---

## 许可证

本文档以 MIT License 发布，与仓库其余内容一致。文中命令涉及分区、GPT、swap、防火墙等高风险操作，执行前请自行备份并确认机型与固件版本。
