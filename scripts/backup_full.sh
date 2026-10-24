#!/bin/sh
# ============================================================
# 京东云 赵云 BE6500 (RE-CS-06) 刷机前全量备份脚本
# 在路由器 Telnet / SSH 内执行（原厂系统或已刷系统均可）
# 用途：把 eMMC 分区 p1-p27（跳过 p28 swap / p29 数据盘）读出来备份
# 用法：
#   全量（推荐，需 U 盘）：  sh backup_full.sh
#   仅关键 4 分区（nc）：    sh backup_full.sh nc <PC_IP> [PORT]
# ============================================================
set -u

MODE="usb"
PC_IP=""
PORT="1234"

if [ "${1:-}" = "nc" ]; then
    MODE="nc"; PC_IP="${2:-}"; PORT="${3:-1234}"
    [ -z "$PC_IP" ] && { echo "nc 模式用法: sh backup_full.sh nc <PC_IP> [PORT]"; exit 1; }
fi

# ---- 关键 4 分区优先（U-Boot / ART / FACTORY）----
backup_one() {
    name="$1"; dev=""
    for cand in "/dev/block/by-name/$name" "/dev/block/by-name/0:$(echo $name | tr '[:lower:]' '[:upper:]')"; do
        [ -e "$cand" ] && dev="$cand" && break
    done
    [ -z "$dev" ] && { echo "[跳过] 未找到分区: $name"; return; }
    echo "==> 备份关键分区 $name ($dev)"
    if [ "$MODE" = "nc" ]; then
        dd if="$dev" bs=1M conv=fsync | nc "$PC_IP" "$PORT"
    else
        dd if="$dev" of="$DEST/${name}.bin" bs=1M conv=fsync
    fi
}

echo "=== 关键分区（U-Boot / ART / FACTORY）==="
backup_one appsbl
backup_one appsbl_1
backup_one art
backup_one factory

# ---- nc 模式只做关键 4 分区即结束（全量请用 U 盘）----
if [ "$MODE" = "nc" ]; then
    echo "✅ nc 模式仅备份关键 4 分区（U-Boot+ART+FACTORY）。全量请用 U 盘模式。"
    exit 0
fi

# ---- USB 全量 p1-p27 ----
DEST=""
for m in /mnt/usb /mnt/sda1 /tmp/media /mnt; do
    [ -d "$m" ] && DEST="$m/be6500_backup" && break
done
[ -z "$DEST" ] && { echo "未找到 U 盘挂载点，请先 mount（如 mount /dev/sda1 /mnt/usb），或改用 nc 模式。"; exit 1; }
mkdir -p "$DEST"
echo "备份目标: $DEST"

echo "=== 全量分区 p1-p27（跳过 p28 swap / p29 数据）==="
for p in $(seq 1 27); do
    dev="/dev/mmcblk0p$p"
    [ -b "$dev" ] || { echo "[跳过] 无 $dev"; continue; }
    echo "==> 备份 $dev"
    dd if="$dev" of="$DEST/mmcblk0p$p.bin" bs=1M conv=fsync
done

echo "✅ 全量备份完成 -> $DEST"
echo "请用 PC 校验目录内文件数量与大小，再继续刷机。"
