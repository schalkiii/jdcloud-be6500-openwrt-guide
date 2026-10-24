#!/usr/bin/env python3
# gpt_inspect.py — 离线检查 GPT 镜像是否合法、条目是否完整（断网可跑）
# 用法：python gpt_inspect.py <gpt.bin>
# 适用于 34 扇区(17408B) 的 primary GPT 镜像（保护 MBR + GPT 头 + 条目数组）
import struct
import sys
import binascii


def read_guid(b):
    # 前 3 段小端，后 2 段大端
    d1 = struct.unpack("<I", b[0:4])[0]
    d2 = struct.unpack("<H", b[4:6])[0]
    d3 = struct.unpack("<H", b[6:8])[0]
    d4 = b[8:10].hex().upper()
    d5 = b[10:16].hex().upper()
    return f"{d1:08X}-{d2:04X}-{d3:04X}-{d4}-{d5}"


def main():
    if len(sys.argv) < 2:
        print("Usage: python gpt_inspect.py <gpt.bin>")
        sys.exit(1)
    path = sys.argv[1]
    with open(path, "rb") as f:
        data = f.read()

    print(f"文件: {path}")
    print(f"大小: {len(data)} 字节 ({len(data)/1024:.2f} KiB, {len(data)//512} 扇区)\n")

    # 保护 MBR
    mbr_sig = data[510:512]
    print(f"[LBA0] 保护 MBR 结束标志: {mbr_sig.hex().upper()} "
          f"({'OK 0x55AA' if mbr_sig == b'\x55\xAA' else '异常'})")
    mbr_type = data[446 + 4]
    print(f"[LBA0] 第一个 MBR 分区类型: 0x{mbr_type:02X} "
          f"({'0xEE = 保护性 MBR，正常' if mbr_type == 0xEE else '非 0xEE'})")

    # GPT 头在 LBA1
    hdr = data[512:512 + 512]
    sig = hdr[0:8]
    print(f"\n[LBA1] GPT 头签名: {sig!r} "
          f"({'OK EFI PART' if sig == b'EFI PART' else '❌ 不是 GPT 头'})")
    if sig != b"EFI PART":
        print("→ 这不是合法的 GPT 镜像，不用继续解析。")
        sys.exit(2)

    hsize = struct.unpack("<I", hdr[12:16])[0]
    hcrc = struct.unpack("<I", hdr[16:20])[0]
    mylba = struct.unpack("<Q", hdr[24:32])[0]
    altlba = struct.unpack("<Q", hdr[32:40])[0]
    first_usable = struct.unpack("<Q", hdr[40:48])[0]
    last_usable = struct.unpack("<Q", hdr[48:56])[0]
    entry_lba = struct.unpack("<Q", hdr[72:80])[0]
    num_entries = struct.unpack("<I", hdr[80:84])[0]
    entry_size = struct.unpack("<I", hdr[84:88])[0]
    entries_crc = struct.unpack("<I", hdr[88:92])[0]

    # 校验头 CRC（把 CRC 字段置 0 后算）
    hdr_for_crc = bytearray(hdr[:hsize])
    hdr_for_crc[16:20] = b"\x00\x00\x00\x00"
    calc_hcrc = binascii.crc32(bytes(hdr_for_crc)) & 0xFFFFFFFF
    print(f"[LBA1] 头大小={hsize}  MyLBA={mylba}  AlternateLBA={altlba}")
    print(f"[LBA1] 可用区 LBA: {first_usable} - {last_usable}")
    print(f"[LBA1] 条目数组: LBA={entry_lba}  条目数={num_entries}  每条={entry_size}B")
    print(f"[LBA1] 头 CRC32: 存储=0x{hcrc:08X}  计算=0x{calc_hcrc:08X} "
          f"{'✅ 一致' if hcrc == calc_hcrc else '❌ 不一致'}")

    # 条目数组
    arr_off = entry_lba * 512
    arr_len = num_entries * entry_size
    if arr_off + arr_len > len(data):
        print(f"\n❌ 条目数组超出文件范围（需要 {arr_off+arr_len} 字节，文件只有 {len(data)}）")
        print("→ 这说明镜像被截断了，条目不全。")
        sys.exit(3)
    arr = data[arr_off:arr_off + arr_len]
    calc_ecrc = binascii.crc32(arr) & 0xFFFFFFFF
    print(f"[LBA{entry_lba}] 条目数组 CRC32: 存储=0x{entries_crc:08X}  计算=0x{calc_ecrc:08X} "
          f"{'✅ 一致' if entries_crc == calc_ecrc else '❌ 不一致'}")

    zero_guid = b"\x00" * 16
    print("\n序号  名称                      起始LBA      结束LBA      大小")
    print("-" * 78)
    found = {}
    count = 0
    for i in range(num_entries):
        e = arr[i * entry_size:(i + 1) * entry_size]
        if e[0:16] == zero_guid:
            continue
        start = struct.unpack("<Q", e[32:40])[0]
        end = struct.unpack("<Q", e[40:48])[0]
        name = e[56:128].decode("utf-16-le", errors="replace").split("\x00")[0]
        sectors = end - start + 1
        size_mb = sectors * 512 / 1024 / 1024
        count += 1
        found[name.strip()] = size_mb
        print(f"{count:>3}   {name:<26} {start:<12} {end:<12} {size_mb:>10.1f} MiB")

    print("-" * 78)
    print(f"有效分区条目数: {count}")

    # 关键分区检查
    print("\n关键分区检查:")
    for key in ["0:HLOS", "HLOS", "rootfs", "0:SBL1", "0:ART", "factory", "0:WIFIFW"]:
        if key in found:
            print(f"  ✅ {key}  ({found[key]:.1f} MiB)")
    has_hlos = any(k.upper().endswith("HLOS") or k.upper() == "HLOS" for k in found)
    has_rootfs = any("rootfs" in k.lower() for k in found)
    print(f"\n含 0:HLOS : {'✅ 是' if has_hlos else '❌ 否'}")
    print(f"含 rootfs : {'✅ 是' if has_rootfs else '❌ 否'}")

    ok = count > 0 and has_hlos and has_rootfs and hcrc == calc_hcrc and entries_crc == calc_ecrc
    print("\n==== 结论:", "GPT 合法且条目完整，可用于恢复 ✅" if ok else "GPT 有问题 ❌", "====")
    sys.exit(0 if ok else 4)


if __name__ == "__main__":
    main()
