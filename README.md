# 京东云 赵云 BE6500（RE-CS-06）免拆刷 OpenWrt / QWRT 完整教程

> 一份面向「想给路由器换第三方固件、但不想拆机焊 TTL」用户的实战教程。
> 全部步骤均在 **京东云 赵云 BE6500（型号 RE-CS-06）** 上验证通过，最终成功运行 QWRT。

---

## 0. 适用前提与风险提示

### 适用前提

- 设备：**京东云 赵云 BE6500**，型号 **RE-CS-06**（硬件平台 IPQ5322 + QCN9224，WiFi7，全 2.5G 网口，eMMC 存储约 116 GiB）。
- 原厂固件版本：**4.5.3.r4530**（其他版本未验证，Telnet 开启方式可能不同）。
- 目标固件：**QWRT**（基于 OpenWrt / QSDK 的第三方固件，闭源无线驱动）。
- 方式：**免拆机、免 TTL**，纯在线刷写（F12 控制台注入开 Telnet → 刷 U-Boot → U-Boot WebUI 刷固件）。

### 风险提示（必读）

1. 刷机有**变砖风险**，操作即代表自担后果。
2. 任何刷写前**必须完整备份 `ART` 与 `factory` 分区**——这两分区每台机器唯一（含无线校准、MAC、序列号），丢了只能借别人的备份（虚拟 SN，可能和官方 App 冲突），基本无解。
3. **切勿触发官方自动升级**：升级会覆盖 U-Boot 或封堵漏洞。已绑定无线宝 App 的，先关闭「系统自动升级」。
4. 免拆方案的最大风险：一旦硬变砖，回退通常要拆机焊 TTL，成本陡增。请确保备份到位、文件哈希正确、机型文件对应，再点重启。

---

## 目录

- [一、原理与风险](#一原理与风险)
- [二、准备工作](#二准备工作)
- [三、阶段 0 ｜ 关闭自动升级](#三阶段-0--关闭自动升级)
- [四、阶段 1 ｜ 开启 Telnet](#四阶段-1--开启-telnet)
- [五、阶段 2 ｜ 全量备份](#五阶段-2--全量备份)
- [六、阶段 3 ｜ 获取 U-Boot 到路由器](#六阶段-3--获取-u-boot-到路由器)
- [七、阶段 4 ｜ 刷入 U-Boot](#七阶段-4--刷入-u-boot)
- [八、阶段 5 ｜ 进 U-Boot WebUI](#八阶段-5--进-u-boot-webui)
- [九、阶段 6 ｜ GPT → factory.bin → 重启](#九阶段-6--gpt--factorybin--重启)
- [十、阶段 7 ｜ 首次启动后](#十阶段-7--首次启动后)
- [十一、首次登录密码（重点）](#十一首次登录密码重点)
- [十二、常见问题 / 踩坑实录](#十二常见问题--踩坑实录)
- [十三、救砖 / 9008 / TTL](#十三救砖--9008--ttl)
- [十四、关于 2G 大分区扩容（后续做法）](#十四关于-2g-大分区扩容后续做法)
- [十五、仓库目录结构与脚本说明](#十五仓库目录结构与脚本说明)
- [十六、参考来源](#十六参考来源)
- [许可证](#许可证)

---

## 一、原理与风险

**为什么必须换 U-Boot？** 原厂 bootloader 不认 OpenWrt / QWRT，必须换成第三方 U-Boot 才能启动第三方固件。这是免拆路线**无法跳过**的一步。

**免拆路线的本质**：利用原厂固件里的一个漏洞（通过浏览器 F12 控制台注入 JS）开启 Telnet，从而在不拆机的情况下把第三方 U-Boot 写进启动分区；之后重启进 U-Boot 的 Web 界面，在线刷入 GPT 分区表与 QWRT 固件。

**最大风险**：U-Boot 写错机型文件会直接硬变砖，且回退要拆机焊 TTL。因此「备份 → 校验哈希 → 确认机型文件」每一步都不能省。

---

## 二、准备工作

### 2.1 物料清单

| 文件 | 用途 | 校验 |
|---|---|---|
| `uboot-ipq53xx-jdcloud_re-cs-06-260907_172823_3e89586.bin` | 第三方 U-Boot（刷入启动分区） | MD5 `49f84b72b9a7b2463f1ae3ae56f4090a`（640 KB） |
| `QWRT-...-squashfs-factory.bin` | **首刷**固件（首次刷入用） | MD5 `ae443a020d288d4f361f8c1b71c35e64`（约 105 MB） |
| `QWRT-...-squashfs-sysupgrade.bin` | **系统内升级**固件（日后升级用，不可首刷） | MD5 `a53deb5c041e16dd6cd20afa4c40838b`（约 105 MB） |
| `gpt_JDCloud-BE6500_2G.bin` | 2G 大分区 GPT 表（**可选**，见第十四节） | MD5 `028c7b41a64f435cee1623934aa01bde`（17408 字节） |

> 上述三个 `*.bin` 体积较大，以 **GitHub Release** 形式提供（不放在仓库源码里）。`gpt_JDCloud-BE6500_2G.bin` 因来源获取方式不同，请按第十四节说明取得。
> 完整的哈希见仓库根目录 `checksums.txt`。

### 2.2 PC 与网络

- 一台能运行 Python 3 的电脑（用于运行备份接收脚本；若电脑没有 `nc`/`netcat`，则必须用这里的 Python 脚本）。
- 路由器与电脑**用网线直连**（不要用 WiFi：刷机过程中 WiFi 必然中断，网线才稳）。
- 固件获取来源见[第十六节](#十六参考来源)。

---

## 三、阶段 0 ｜ 关闭自动升级

进入原厂后台，关闭「系统自动升级」。这一步必须在开 Telnet、刷任何东西**之前**完成，否则官方升级可能在你操作途中覆盖 U-Boot 或封堵漏洞。

---

## 四、阶段 1 ｜ 开启 Telnet

> 参考 gwrt.uk 的「F12 控制台注入」方法（通用亚瑟 / 赵云 / 雅典娜）。

1. 浏览器登录原厂后台（默认管理 IP 通常为 `192.168.68.1`）。
2. 打开浏览器开发者工具（F12）→ Console（控制台）。
3. 按来源页说明，粘贴注入脚本执行，触发开启 Telnet 的接口。
4. Telnet 登录：
   ```bash
   telnet 192.168.68.1
   # 用户名: root
   # 密码: 路由器 WebUI 登录密码（即你后台管理设置的密码，不是空密码）
   ```
5. 登录后建议立刻改密，防止会话被踢：
   ```bash
   passwd root
   ```

---

## 五、阶段 2 ｜ 全量备份

> **核心原则**：`ART`（无线校准）与 `factory`（MAC / 序列号）每台机器唯一，必须备份。这两个分区丢了，基本只能借别人备份救砖。

### 5.1 分区表概览

赵云 BE6500 有 **29 个真实分区**（eMMC 约 116 GiB，GPT 分区表）。关键分区：

| 分区 | 名称 | 大小 | 是否必备份 |
|---|---|---|---|
| p17 | `0:ART` ⭐无线校准 | 1M | ✅ 核心 |
| p25 | `factory` ⭐MAC/SN | 256K | ✅ 核心 |
| p14 / p15 | `0:APPSBL`（U-Boot A/B） | 768K | ✅ |
| p1–p13, p16, p18–p24, p26, p27 | 各类固件 / 系统 / 日志 | 不等 | ✅ |
| p28 | `swap` | 1G | ❌ 排除 |
| p29 | `storage`（PCDN 数据盘，约 112 GB） | ~112G | ❌ 排除 |

> 备份按「智能 bs」规则：分区 `< 4MiB` 用 `256k`，`≥ 4MiB` 用 `1M`。`p28/p29` 为系统运行用的交换与数据盘，**备份按设计排除**（不影响救砖）。

### 5.2 PC 端接收

在电脑上运行仓库里的 `scripts/recv_backup.py`（纯 Python，无需 `nc`）：

```bash
cd scripts
python3 recv_backup.py 1234 backup_output
```

脚本监听 `0.0.0.0:1234`，收到的每个分区按首行 `PART:<name>` 头自动命名落盘到 `backup_output/`。

### 5.3 路由器端执行

把下面整段粘贴进路由器 Telnet（把 `PC_IP` 改成你电脑的实际 IP）：

```bash
PC_IP=192.168.68.100   # 改成你 PC 的实际 IP
PO=1234
# GPT 主表前 34 扇区
{ printf "PART:gpt_primary\n"; dd if=/dev/mmcblk0 bs=512 count=34 conv=noerror,sync; } | nc $PC_IP $PO
# p1 - p27 全量（智能 bs）
for i in $(seq 1 27); do
  d=/dev/mmcblk0p$i
  [ -b $d ] || continue
  sz=$(cat /sys/block/mmcblk0/mmcblk0p$i/size 2>/dev/null)
  b=$(( ${sz:-0} * 512 ))
  if [ $b -lt 4194304 ]; then bs=256k; else bs=1M; fi
  echo "[p$i] ${b}B bs=$bs"
  { printf "PART:p$i\n"; dd if=$d bs=$bs conv=noerror,sync; } | nc $PC_IP $PO
  sleep 0.3
done
echo "BACKUP_DONE"
```

> 若路由器里没有 `nc`，用 `scripts/send_file.py` 反向从 PC 推文件、路由用其他方式收；或参考 `scripts/backup_smart.sh`（路由器端智能备份脚本，用法 `sh backup_smart.sh nc <PC_IP> 1234`）。

### 5.4 核对

PC 端 `backup_output/` 应出现 `001_gpt_primary.bin` + `002_p1.bin` … `028_p27.bin` 共 **28 个文件**。强烈建议用 `scripts/verify_backup.py` 离线校验：

```bash
python3 verify_backup.py backup_output
```

确认 `ART`、`factory`、双 U-Boot、GPT 全部通过，再进入下一步。

---

## 六、阶段 3 ｜ 获取 U-Boot 到路由器

把 U-Boot 文件弄到路由器的 `/tmp`。两种办法：

### 方法 A（推荐，路由能上网时）：路由直连下载

```bash
cd /tmp
curl -k -O https://godsun.pro/jdc9008/uboot-ipq53xx-jdcloud_re-cs-06-260907_172823_3e89586.bin
md5sum uboot-ipq53xx-jdcloud_re-cs-06-260907_172823_3e89586.bin
# 必须 = 49f84b72b9a7b2463f1ae3ae56f4090a
```

### 方法 B（PC 本地传，无 nc 也行）：Python 发送

```bash
# PC 端（在 scripts 目录）：
python3 send_file.py 1234 /path/to/uboot-ipq53xx-jdcloud_re-cs-06-260907_172823_3e89586.bin
# 路由端 Telnet 内：
cd /tmp
nc <PC_IP> 1234 > uboot.bin
md5sum uboot.bin        # 必须 = 49f84b72b9a7b2463f1ae3ae56f4090a
```

---

## 七、阶段 4 ｜ 刷入 U-Boot

先确认 APPSBL 节点（通常 p14 / p15）：

```bash
ls -l /dev/block/by-name/ | grep -i appsbl
```

写入（**256K 分区必须 `bs=256k`**）：

```bash
cd /tmp
dd if=/tmp/uboot.bin of=/dev/mmcblk0p14 bs=256k conv=fsync
dd if=/tmp/uboot.bin of=/dev/mmcblk0p15 bs=256k conv=fsync
# 清 A/B 启动配置，让新 U-Boot 走默认启动逻辑
dd if=/dev/zero of=/dev/mmcblk0p3 bs=256k count=1
dd if=/dev/zero of=/dev/mmcblk0p4 bs=256k count=1
sync
```

⚠️ `p3/p4` 是 BOOTCONFIG 小分区，必须用 `bs=256k`，否则写坏。

---

## 八、阶段 5 ｜ 进 U-Boot WebUI

1. **拔电 → 长按 reset 不放 → 插电**，灯闪几下后变蓝 / 绿常亮即进入 U-Boot 模式。
2. PC 网卡手动设 IP（如 `192.168.3.2`，掩码 `255.255.255.0`）。
3. 浏览器打开 **`http://192.168.3.3`**（沉心版默认；旧 hugo 版是 `192.168.1.1`；以 PC 实际获取到的网关为准）。
4. 看到 U-Boot WebUI 即成功。

---

## 九、阶段 6 ｜ GPT → factory.bin → 重启

> **顺序铁律：GPT → factory.bin → 重启，三步连续做完，中间不要单独重启。**
> GPT 改写了 `rootfs` / `HLOS` 起始位置，旧固件数据对不上号会无法启动；这里的「固件」指 QWRT `factory.bin`，**不是 GPT**（GPT 只是分区表）。

### 9.1 先刷 GPT 大分区表

WebUI 的 GPT 页有两种形态，按你实际看到的来：

- **(a) 容量 + HLOS 选择式**（godsun.pro「一页搞定」文描述的那种）：选容量 512 / 1024 / 2048（即 512M / 1G / 2G 数据分区）+ **HLOS 内核分区 6M / 12M**，再点刷入。
- **(b) 纯文件上传式**（沉心 260907 实测形态）：页面只有「选择本地文件 + 更新」，**没有容量 / HLOS 选项**。直接选 `gpt_JDCloud-BE6500_2G.bin`（17408 字节，MD5 `028c7b41a64f435cee1623934aa01bde`），点 **「更新」**（**不是「更新并重启」**），等成功提示。

> **「2G」是什么**：指把 OpenWrt 装包 / 插件用的**系统分区（rootfs/overlay）扩容到 2GB** 这一档（另有 512M / 1G 档），**不是 GPT 文件大小**（GPT 本身才几十 KB），**也不是 `p29` 存储盘**。原厂布局该分区只有约 122MB，只有装插件空间紧张时才需要 2G 大分区；普通家用原厂布局（已含约 112GB `storage`）完全够用，2G 是可选增强，不是必做。详见[第十四节](#十四关于-2g-大分区扩容后续做法)。

> ⚠️ GPT 写完**必须接着刷 factory.bin 最后才重启**，不能单独重启。报「找不到 0:HLOS」的处理见[第十二节](#十二常见问题--踩坑实录)。

> **ART / factory 不需要单独回刷**：正常流程里 GPT 只改分区表、factory.bin 只写 `0:HLOS`+`rootfs`，二者都不碰 `p17 ART` / `p25 factory` 的数据；用原厂 GPT 备份写回后 p17/p25 仍指回原 LBA、数据完好。备份是**保险**不是必做步骤，只有出现**无线 MAC 显示 00:00 或 WiFi 异常**时才单独还原这两个分区（在 QWRT 的 SSH 里 `dd`，非 U-Boot 单刷）。

### 9.2 再刷固件（必须是 factory 镜像）

上传 RE-CS-06 专用 `factory.bin`（首刷用 factory，**不要勾保留配置**）。

- ⚠️ `...-squashfs-sysupgrade.bin` 是**系统内升级**用的，**不能首刷**；首刷必须 `...-squashfs-factory.bin`。
- HLOS 内核分区：没特殊癖好直接 6M；想多刷不同 ROM 选 12M。

### 9.3 立刻在同一 WebUI 点重启

盯指示灯，最后**绿灯常亮**即进系统。默认 IP 看 PC 获取到的网关（刷完进系统后地址通常会变，见[第十一 / 十六节](#十一首次登录密码重点) IP 速查，别死守 `192.168.3.3`）。

---

## 十、阶段 7 ｜ 首次启动后

- 进 OpenWrt / QWRT 后台；**已启动新系统后用 SSH 登录**（不是原厂 Telnet）。
- **可选**：把刷完 GPT 后剩余的未分配空间建成数据分区（仅当刷了 2G 大分区 GPT 且需要时才做）：
  ```bash
  cfdisk /dev/mmcblk0
  # 移到最下方 Free Space → New → 容量默认（全用）回车 → Write → 输入 yes → Quit
  mkfs.ext4 /dev/mmcblk0p29
  ```
  > **为什么是 SSH 而不是原厂 Telnet？** 刷机前用 F12 注入开的 shell 是原厂京东云固件的（备份、刷 U-Boot 都在那里面做）。刷完 GPT + factory 重启后，原厂固件已被 QWRT 取代，那个 Telnet 已经不存在了。重启进的是 **QWRT（OpenWrt 衍生）**，它的远程登录方式是 **SSH**（`ssh root@<网关IP>`），首启后可用。
  > 而且 `cfdisk` 操作的是**新 GPT 布局**——这布局只有 U-Boot 刷完 GPT 并重启进 QWRT 之后才生效；原厂 Telnet 环境下既没有新 GPT，也通常**不带 `cfdisk`**（原厂 BusyBox 精简，未必含此工具）。所以这一步只能在 QWRT 的 SSH 里做。
  > **用原厂 GPT 时不需要 cfdisk**：原厂布局里 `storage`（p29）已经存在且约 112GB，直接 `mkfs.ext4 /dev/mmcblk0p29` 即可，无需新建。
- 后续系统内升级才刷 `sysupgrade.bin`（可勾保留配置）。

---

## 十一、首次登录密码（重点）

QWRT / OpenWrt **没有出厂写死的默认 WebUI 密码**（不存在 `admin/admin` 这类）。

- **情况 A（最常见）**：首次启动后浏览器进网关（通常 `192.168.1.1`），LuCI 直接弹出**「请设置 root 密码」**强制页，你设什么密码就是什么；设完才能进后台，SSH 也要求先设密码才能远程登录。
- **情况 B（部分预编译构建自带预设）**：少数 QWRT / Lean 构建预埋密码，最常见组合 `root` / `password`。若登录页要求输入密码，先试 `root / password`；连不上再试空密码或直接走情况 A 的设密码页。

> 进后台后第一件事：确认「网络 → 接口」里 LAN 的 MAC 不是 `00:00:00:00:00:00`、WiFi 能正常搜到信号。若 MAC 全零或 WiFi 异常，按[第十二节](#十二常见问题--踩坑实录)用备份单独还原 `p17 ART` / `p25 factory`（在 QWRT 的 **SSH** 里 `dd`，非 U-Boot 单刷）。

### 各阶段 IP 速查

| 场景 | 地址 | PC 网卡设置 |
|---|---|---|
| 原厂后台 / Telnet | `192.168.68.1` | 自动 DHCP |
| U-Boot WebUI（沉心版） | `192.168.3.3` | 手动 `192.168.3.2/24` |
| QWRT / OpenWrt 系统（首启后） | 通常为 `192.168.1.1`（以 PC 获取到的网关为准） | 改回自动 DHCP |

> 旧 hugo 版 U-Boot WebUI 是 `192.168.1.1`；沉心版是 `192.168.3.3`。**刷完进系统后地址会变**（QWRT 默认 `192.168.1.1`），别死守 `192.168.3.3`。

---

## 十二、常见问题 / 踩坑实录

### 12.1 刷完无限重启（bootloop）

进 U-Boot（长按 reset），执行：

```
setenv bootargs 'console=ttyMSM0,115200n8'
setenv fsbootargs
saveenv
```

再重启。若仍 loop，进 U-Boot WebUI 重刷一遍 factory.bin（不保留配置）。

### 12.2 无线 MAC 显示 00:00（factory 丢）

用备份还原 `p25`：

```bash
dd if=/path/to/mmcblk0p25_factory.bin of=/dev/mmcblk0p25 bs=256k conv=fsync
```

没自家备份则借别人 factory（虚拟 SN，可能与官方 App 冲突）。

### 12.3 刷 factory.bin 报「找不到分区 0:HLOS」

`0:HLOS` = 内核分区、`rootfs` = 根文件系统，刷写器靠它们定位。按以下顺序处理：

1. **固件页缓存 / 未重读 GPT（最常见）**：GPT 页点「更新」成功后，**浏览器 Ctrl+F5 强制刷新**，或退回首页重新进入「固件更新」页，让它重新读取分区表，再刷 factory。
2. **GPT 没真正写成功**：确认点的是 **「更新」**（**不是「更新并重启」**）且有成功提示；文件用 `gpt_JDCloud-BE6500_2G.bin`（17408 字节，MD5 `028c7b41a64f435cee1623934aa01bde`）。
3. **改用自己备份的原厂 GPT**：同一页面选备份里的 `001_gpt_primary.bin`（17408 字节），点「更新」，Ctrl+F5 刷新，再刷 factory。原厂 GPT 必含 `0:HLOS`+`rootfs` 且与机器原始布局完全匹配，最稳；代价是无 2G 扩容，QWRT 起来后可[第十四节](#十四关于-2g-大分区扩容后续做法)再扩容。
4. **固件文件选错**：首刷必须是 `...-squashfs-factory.bin`，**不是** `sysupgrade.bin`。

> 全程**不要点「更新并重启」**：现在没固件，重启只会起不来。GPT + factory 都刷完，最后才重启。

### 12.4 「分区信息」只剩 `0:GPT`，一个真实分区都没有

说明 GPT 条目被写空 / 写坏（只剩 GPT 头），所以刷 factory 必然报「找不到 0:HLOS」。设备仍停在 WebUI，用备份即可恢复：

1. 在「分区表更新」页选备份里的 `001_gpt_primary.bin`（可用 `scripts/gpt_inspect.py` 验证：29 个分区、头 / 条目 CRC 全对、含 `0:HLOS`+`rootfs`+`factory`+`0:ART`），点 **「更新」**（**不是**「更新并重启」），等成功提示。
2. 回「分区信息」页确认已出现 **29 行**（`0:SBL1` … `storage`），再进「固件更新」刷 factory.bin。
3. **若仍只有 `0:GPT`**（说明 WebUI 没真正把条目写进 eMMC），走 TTL 兜底：
   ```
   # TTL 接线 RX↔TX / TX↔RX / GND↔GND，115200，打断密码 jdqca
   setenv ipaddr 192.168.1.2; setenv serverip 192.168.1.25
   tftpboot 0x50000000 gpt_JDCloud-BE6500_2G.bin
   mmc write 0x50000000 0 22      # 0x22 = 34 扇区 = 17408 字节
   reset
   ```
   再进 WebUI 刷 factory。同理可用 `001_gpt_primary.bin` 替代 2G GPT。

### 12.5 WebUI 是「纯文件上传式」，没有容量 / HLOS 下拉选项

网上有些教程（如 godsun.pro「一页搞定」）描述的是**带下拉选项**的 GPT 页；但**沉心 260907 这个构建是纯文件上传式**——只有「选择本地文件 + 更新 / 更新并重启」，没有容量、HLOS 选项。直接选对应的 GPT 文件即可，这是正常现象，不是你操作错了。

### 12.6 为什么「分区信息」显示 30 行，而网上教程写 1–29 分区？

同一套布局，只是显示口径不同：

- 这台机器真实分区就是 **29 个**（0:SBL1、0:QSEE、0:HLOS、rootfs、factory、0:ART … 一直到 storage）。
- 沉心 WebUI 的「分区信息」会把 **GPT 表头自身也列成第 1 行**，名字叫 `0:GPT`（17 KiB，即那 34 扇区），再列出后面 29 个真实分区。
- 所以你看到的是：**1 行 GPT 头 + 29 行真实分区 = 30 行**。网上教程数的是「29 个真实分区」，没把 GPT 头算进去。你之前恢复后看到的 30 行里，第 1 行是 `0:GPT`，第 2–30 行恰好是 0:SBL1 … storage 共 29 个——和标准布局一一对应，没多也没少。

### 12.7 2G GPT 的 bin 是不是坏了、不能用了？

**文件没坏，可以继续用。**

- `gpt_JDCloud-BE6500_2G.bin`（17408 字节，MD5 `028c7b41a64f435cee1623934aa01bde`）是官方原版，**不是损坏文件**。
- 之前「刷完只剩 `0:GPT`、报找不到 `0:HLOS`」的锅，是**沉心 260907 这个 WebUI 的 GPT 写步骤没把分区条目真正提交进 eMMC（只写了 GPT 头）**，不是文件问题。证据：用**同一页面**上传原厂备份 `001_gpt_primary.bin`，就正常写出了 29 行——同一个写逻辑，原厂备份能成、2G 不行，说明是 WebUI 对 2G 这种「非本机原始布局」的解析 / 提交不可靠，而不是 bin 坏了。
- 所以：**bin 可用，只是别走 WebUI 上传，改走[第十四节](#十四关于-2g-大分区扩容后续做法)的 `mmc write`**。

### 12.8 storage 已经 100 多 G，还有必要 cfdisk 吗？

**用原厂 GPT 时完全不需要 cfdisk。**

- 原厂 GPT 布局里 `p29 storage` 已经存在、约 112GB，是可用的数据盘。cfdisk 只是「从**空闲空间新建分区**」的工具——你没空闲空间要建，所以不用动。
- cfdisk 只有在一种情况下才需要：**刷了 2G 大分区 GPT 之后**，如果新布局尾部留出未分配空间、你想把它划成数据盘，才进 QWRT 的 SSH 用 `cfdisk /dev/mmcblk0` 建。即便那样，若 2G 布局本身已带 storage 分区，你也只需 `mkfs.ext4` 格式化，未必需要 cfdisk 新建。

---

## 十三、救砖 / 9008 / TTL

- **现象排查**：开机插 USB 到电脑，若识别出 **高通 9008** 设备 → SoC 还活着但启动卡住。进 U-Boot 执行 `mmc info`：
  - 能识别 eMMC → 分区表 / 固件刷坏，用 TTL 重刷 U-Boot + 固件；
  - 不能识别 / 报错 → eMMC 物理损坏，需拆下编程器重刷或更换。
- **TTL 救砖通用**（任何状态含 Telnet 刷坏都可救）：
  - U-Boot 打断密码：`jdqca`（2025-06 起无需短接 eMMC）。
  - 接线：USB-TTL 的 RX↔路由 TX，TX↔路由 RX，GND↔GND（VCC 不接）。波特率 **115200**。
  - 通电后看到 `console and autoboot in 3 seconds` 立刻粘贴 `jdqca`，出现 `ipq5322#` 即打断成功。
  - 完整重刷：`tftpboot` 拉 U-Boot → `flash 0:APPSBL && flash 0:APPSBL_1`，再刷固件。

---

## 十四、关于 2G 大分区扩容（后续做法）

**先说结论**：家用 QWRT 装几个插件、跑点 docker，122MB overlay + 112GB storage 完全够。**2G 是「插件装到爆」才需要的增强项，不是必做。** 而且实测沉心 260907 的 WebUI「分区表更新」上传 2G GPT 不可靠（见 [12.4](#124-分区信息只剩-0gpt一个真实分区都没有) / [12.7](#127-2g-gpt-的-bin-是不是坏了不能用了)），所以扩容时**不要走 WebUI 上传**，改用 `mmc write` 直接写扇区。

### 14.1 获取 2G GPT 文件

`gpt_JDCloud-BE6500_2G.bin`（17408 字节，MD5 `028c7b41a64f435cee1623934aa01bde`）来自 godsun.pro 的 BE6500 教程页。下载后务必 `md5sum` 核对 = `028c7b41a64f435cee1623934aa01bde`。

### 14.2 用 mmc write 直写（绕过 WebUI）

进 U-Boot（长按 reset，或 TTL 命令行），用 TFTP 拉 2G GPT 直写：

```
setenv ipaddr 192.168.1.2; setenv serverip 192.168.1.25   # 改成你的 TFTP/PC IP
tftpboot 0x50000000 gpt_JDCloud-BE6500_2G.bin
mmc write 0x50000000 0 22        # 0x22 = 34 扇区 = 17408 字节，整张 GPT 原样落盘
```

### 14.3 写完必须当次连刷 factory.bin → 重启

GPT 改了 rootfs 位置，不能单独重启。**写完 2G GPT 当次立刻刷 factory.bin → 重启**，三步连续。进系统后若新布局尾部有未分配空间，再按[第十节](#十阶段-7--首次启动后)用 `cfdisk` 处理。

---

## 十五、仓库目录结构与脚本说明

```
jdcloud-be6500-openwrt-guide/
├── README.md            # 本教程
├── checksums.txt        # Release 二进制文件的 MD5 校验和
├── LICENSE              # 许可证
├── .gitignore           # 忽略 *.bin 与私人备份目录
└── scripts/             # 工具脚本（纯文本，纳入版本管理）
    ├── gpt_inspect.py   # 离线解析 GPT 镜像：校验签名/CRC、列出分区、判断是否含 0:HLOS
    ├── recv_backup.py   # PC 端备份接收器（监听端口，无需 nc）
    ├── send_file.py     # PC→路由器 文件发送器（无 nc 时传 U-Boot 用）
    ├── verify_backup.py # 离线校验备份目录里的 28 个文件完整性
    ├── backup_smart.sh  # 路由器端智能 bs 全分区备份脚本
    └── backup_full.sh   # 路由器端全量备份脚本
```

> **二进制固件不在仓库里**：U-Boot、QWRT factory / sysupgrade 体积大且有分发考量，统一作为 **GitHub Release** 资产发布（见[第二节](#二准备工作)哈希表与 `checksums.txt`）。
> **私人备份不上传**：你自己路由器的 `backup_from_router/` 含唯一的 ART / factory / MAC / SN，切勿提交到任何公开仓库。

---

## 十六、参考来源

- 恩山原帖（HugoYuan，QWRT）：`https://www.right.com.cn/forum/thread-8389740-1-1.html`
- godsun.pro BE6500 完整教程（分区表 / 备份 / GPT / 救砖）：`https://godsun.pro/blog/jdc-be6500openwrt.html`
- godsun.pro U-Boot 单页速查：`https://godsun.pro/blog/jdc-uboot-be6500.html` / `https://godsun.pro/?p=1132`
- gwrt.uk 开 Telnet 页（F12 注入，通用亚瑟 / 赵云 / 雅典娜）：`https://gwrt.uk/jdc-arthur-telnet-4546.html`
- gwrt.uk BE6500 刷机：`https://gwrt.uk/jdc-be6500-openwrt.html`
- SWRT 官改说明：`https://blog.paldier.com/jdcbe6500`
- QWRT 固件共享（factory / sysupgrade，免费）：`https://www.123pan.com/s/XriKVv-dVOSv.html` 提取码 `7ru4`

---

## 许可证

本教程与 `scripts/` 下脚本以 **MIT License** 发布，详见 `LICENSE`。

> 第三方固件（QWRT / U-Boot / GPT 表）的版权归原作者 / 项目所有，本仓库仅作教程与校验用途，重分发请遵守原项目许可与当地法律法规。
