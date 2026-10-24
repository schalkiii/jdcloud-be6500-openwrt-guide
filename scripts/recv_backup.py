#!/usr/bin/env python3
# ============================================================
# 赵云 BE6500 备份接收端（跑在 PC 上，配合 backup_smart.sh）
# 监听 TCP 端口，逐个接受路由器发来的分区流，按 "PART:<name>" 头自动命名保存。
#
# 用法:
#   python3 recv_backup.py [PORT] [OUT_DIR]
#   默认 PORT=1234, OUT_DIR=backup_from_router
#
# 启动后，在路由器 Telnet 里执行:
#   sh backup_smart.sh nc <本机LAN_IP> 1234
# ============================================================
import socket, os, sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 1234
OUT = sys.argv[2] if len(sys.argv) > 2 else "backup_from_router"
os.makedirs(OUT, exist_ok=True)

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("0.0.0.0", PORT))
s.listen(128)
print(f"[recv_backup] 监听 0.0.0.0:{PORT} -> ./{OUT}", flush=True)
print("[recv_backup] 在路由器 Telnet 执行: sh backup_smart.sh nc <PC_IP> 1234", flush=True)

idx = 0
try:
    while True:
        conn, addr = s.accept()
        idx += 1
        buf = conn.recv(65536)
        if b"\n" in buf:
            head, rest = buf.split(b"\n", 1)
            name = head.decode(errors="replace").replace("PART:", "").strip() or f"part{idx}"
        else:
            rest, name = buf, f"part{idx}"
        fn = os.path.join(OUT, f"{idx:03d}_{name}.bin")
        n = len(rest)
        with open(fn, "wb") as f:
            f.write(rest)
            while True:
                chunk = conn.recv(65536)
                if not chunk:
                    break
                f.write(chunk)
                n += len(chunk)
        conn.close()
        print(f"[#{idx:03d}] {name} -> {fn}  ({n} bytes)", flush=True)
except KeyboardInterrupt:
    print("\n[recv_backup] 已停止。已接收 %d 个分区。" % idx, flush=True)
finally:
    s.close()
