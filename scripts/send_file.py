#!/usr/bin/env python3
# send_file.py — PC 端 TCP 文件发送器（无需 nc / ncat）
# 用途：刷机阶段把 U-Boot 等文件从 PC 推给路由器。
# 路由器用自带 BusyBox nc 接收即可。
#
# 用法（在 刷机包 目录）：
#   python send_file.py <端口> <文件路径>
# 例：
#   python send_file.py 1234 uboot-ipq53xx-jdcloud_re-cs-06-260907_172823_3e89586.bin
#
# 路由器端配套命令（Telnet 内）：
#   cd /tmp && nc <PC_IP> 1234 > uboot.bin
#   md5sum uboot.bin
import socket
import os
import sys


def main():
    if len(sys.argv) < 3:
        print("Usage: python send_file.py <port> <file>")
        sys.exit(1)

    port = int(sys.argv[1])
    path = sys.argv[2]
    if not os.path.isfile(path):
        print(f"ERROR: file not found: {path}")
        sys.exit(1)

    size = os.path.getsize(path)
    name = os.path.basename(path)
    print(f"[send_file] 待发送: {name} ({size} 字节)  监听端口 {port}")
    print(f"[send_file] 路由器端命令： nc <PC_IP> {port} > /tmp/{name}")

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", port))
    srv.listen(1)
    print("[send_file] 等待路由器连接（nc <PC_IP> %d）…" % port)

    conn, addr = srv.accept()
    print(f"[send_file] 收到连接: {addr}")
    sent = 0
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            conn.sendall(chunk)
            sent += len(chunk)
    conn.close()
    srv.close()
    print(f"[send_file] 发送完成: {sent} 字节")


if __name__ == "__main__":
    main()
