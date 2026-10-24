#!/bin/sh
# ============================================================
# 京东云 赵云 BE6500 (RE-CS-06) 智能 bs 全分区备份（nc 传 PC）
# 在路由器 Telnet / SSH 内执行（原厂系统或已刷系统均可）
#
# 用法:
#   sh backup_smart.sh nc <PC_IP> [PORT]
#
# 行为:
#   - 备份 p1-p27（按 godsun 智能脚本逻辑，按分区大小自动选 bs）
#   - 额外备份 GPT 主表前 34 扇区（gpt_primary）作为保护
#   - 按设计排除 p28(swap) / p29(storage 数据盘)，不影响救砖；
#     若要连 p29(~112G) 一起备，把下面循环改成 `seq 1 29` 并注意空间/时间
#   - 每个分区用【单次连接】发送: 首行 "PART:<name>\n" + dd 裸流
#     PC 端 recv_backup.py 据此自动命名文件
# ============================================================
set -u

PC_IP="${1:-}"
PORT="${2:-1234}"
[ -z "$PC_IP" ] && { echo "用法: sh backup_smart.sh nc <PC_IP> [PORT]"; exit 1; }
echo "目标 PC: $PC_IP : $PORT"

send_part() {
    name="$1"; dev="$2"
    [ -b "$dev" ] || { echo "[跳过] 无 $dev"; return; }
    sz=$(cat /sys/block/mmcblk0/${dev##*/}/size 2>/dev/null)
    bytes=$(( ${sz:-0} * 512 ))
    if [ "$bytes" -lt 4194304 ]; then bs=256k; else bs=1M; fi
    echo "[发送] $name ($dev) ${bytes} bytes  bs=$bs"
    { printf "PART:%s\n" "$name"; dd if="$dev" bs=$bs conv=noerror,sync; } | nc "$PC_IP" "$PORT"
    sleep 0.3
}

# GPT 主表前 34 扇区（保护用，方便后续恢复分区表）
echo "[发送] gpt_primary (前34扇区)"
{ printf "PART:gpt_primary\n"; dd if=/dev/mmcblk0 bs=512 count=34 conv=noerror,sync; } | nc "$PC_IP" "$PORT"
sleep 0.3

# p1 - p27 全量（排除 p28 swap / p29 storage）
for i in $(seq 1 27); do
    send_part "p$i" "/dev/mmcblk0p$i"
done

echo "✅ 备份发送完成：p1-p27 + gpt_primary。"
echo "   p28(swap) / p29(storage) 已按设计排除（与 godsun 智能脚本一致）。"
