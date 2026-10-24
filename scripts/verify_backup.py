#!/usr/bin/env python3
# verify_backup.py — 离线校验全量备份完整性（断网也能跑）
# 用法：python verify_backup.py [backup_dir]
# 默认校验 ./backup_from_router
import os
import sys

EXPECTED = {
    "001_gpt_primary.bin": 34 * 512,          # GPT 主表前 34 扇区
    "002_p1.bin": 1 * 1024 * 1024,             # 0:SBL1
    "003_p2.bin": 1 * 1024 * 1024,             # 0:SBL1_1
    "004_p3.bin": 256 * 1024,                  # 0:BOOTCONFIG
    "005_p4.bin": 256 * 1024,                  # 0:BOOTCONFIG1
    "006_p5.bin": 1835008,                     # 0:QSEE (1.8M)
    "007_p6.bin": 1835008,                     # 0:QSEE_1
    "008_p7.bin": 256 * 1024,                  # 0:DEVCFG
    "009_p8.bin": 256 * 1024,                  # 0:DEVCFG_1
    "010_p9.bin": 512 * 1024,                  # 0:TME
    "011_p10.bin": 512 * 1024,                 # 0:TME_1
    "012_p11.bin": 256 * 1024,                 # 0:CDT
    "013_p12.bin": 256 * 1024,                 # 0:CDT_1
    "014_p13.bin": 256 * 1024,                 # 0:APPSBLENV
    "015_p14.bin": 786432,                     # 0:APPSBL  (U-Boot A)
    "016_p15.bin": 786432,                     # 0:APPSBL_1 (U-Boot B)
    "017_p16.bin": 512 * 1024,                 # 0:ETHPHYFW
    "018_p17.bin": 1 * 1024 * 1024,            # 0:ART  ⭐ 无线校准
    "019_p18.bin": 256 * 1024,                 # 0:LICENSE
    "020_p19.bin": 12 * 1024 * 1024,           # 0:WIFIFW
    "021_p20.bin": 12 * 1024 * 1024,           # 0:WIFIFW_1
    "022_p21.bin": 7 * 1024 * 1024,            # 0:HLOS
    "023_p22.bin": 7 * 1024 * 1024,            # 0:HLOS_1
    "024_p23.bin": 122 * 1024 * 1024,          # rootfs
    "025_p24.bin": 122 * 1024 * 1024,          # rootfs_1
    "026_p25.bin": 256 * 1024,                 # factory ⭐ MAC/SN
    "027_p26.bin": 1 * 1024 * 1024 * 1024,     # plugin (1G)
    "028_p27.bin": 128 * 1024 * 1024,          # log (128M)
}

CRITICAL = ["018_p17.bin", "026_p25.bin", "015_p14.bin", "016_p15.bin", "001_gpt_primary.bin"]


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "backup_from_router")
    print(f"[verify] 校验目录: {d}\n")
    if not os.path.isdir(d):
        print("ERROR: 目录不存在")
        sys.exit(1)

    ok = True
    for name, sz in EXPECTED.items():
        p = os.path.join(d, name)
        if not os.path.exists(p):
            print(f"  MISSING      {name}")
            ok = False
            continue
        s = os.path.getsize(p)
        flag = "OK  " if s == sz else "BAD "
        if s != sz:
            ok = False
        print(f"  [{flag}] {name:22} {s:>14} B (期望 {sz} B)")

    files = sorted(os.listdir(d))
    print(f"\n文件数: {len(files)} (期望 28)")
    print("关键分区:")
    for c in CRITICAL:
        p = os.path.join(d, c)
        label = {
            "018_p17.bin": "ART（无线校准）",
            "026_p25.bin": "factory（MAC/SN）",
            "015_p14.bin": "U-Boot A (APPSBL)",
            "016_p15.bin": "U-Boot B (APPSBL_1)",
            "001_gpt_primary.bin": "GPT 主表",
        }[c]
        present = os.path.exists(p)
        print(f"  {'✅' if present else '❌'} {c}  {label}")

    result = ok and len(files) == 28
    print("\n==== 校验结论:", "全部通过 ✅，可放心进入闪写阶段" if result else "存在异常 ❌，请检查上方", "====")
    sys.exit(0 if result else 1)


if __name__ == "__main__":
    main()
