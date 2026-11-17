#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
给已砸壳的 IPA 注入 dylib —— 不依赖 optool / macOS，纯 Python。

为什么手写而不走 LIEF.add_library：
  LIEF 会重建整份 load command 表，对 360MB / 161 条 LC 的巨型二进制有破坏风险。
  这些巨无霸 App 的 header 区通常留了十几 KB padding，直接在 sizeofcmds 末尾
  追加一条 LC_LOAD_DYLIB 就够了，一个字节都不用挪。

用法：
  python inject_dylib.py --ipa 汽水音乐_21.7.0.ipa --dylib seagull.dylib \
                         --out 汽水音乐_patched.ipa [--load-path @executable_path/seagull.dylib]

注入后再用 zsign 重签：
  zsign -k cert.p12 -p 密码 -m app.mobileprovision -o final.ipa -z 9 汽水音乐_patched.ipa
"""
import argparse
import os
import shutil
import struct
import sys
import tempfile
import zipfile

LC_LOAD_DYLIB = 0x0C
MH_MAGIC_64 = 0xFEEDFACF
LC_SEGMENT_64 = 0x19
LC_CODE_SIGNATURE = 0x1D


def find_app_dir(root):
    payload = os.path.join(root, "Payload")
    for name in sorted(os.listdir(payload)):
        if name.endswith(".app"):
            return os.path.join(payload, name)
    raise SystemExit("Payload/ 下找不到 .app")


def patch_macho(path, load_path):
    with open(path, "r+b") as f:
        f.seek(0)
        head = f.read(32)
        if len(head) < 32:
            raise SystemExit("读文件头失败：只拿到 %d 字节（path=%s, size=%d）"
                             % (len(head), path, os.path.getsize(path)))
        magic, cputype, cpusub, filetype, ncmds, sizeofcmds, flags = struct.unpack("<IiiIIII", head)
        if magic != MH_MAGIC_64:
            raise SystemExit("不是 MH_MAGIC_64（%08x），这个脚本只处理 arm64 主二进制" % magic)

        # 读整张 load command 表，找第一条 section 的真实起始 offset 作为可用上界
        f.seek(32)
        lc_blob = f.read(sizeofcmds)
        if len(lc_blob) != sizeofcmds:
            raise SystemExit("load command 读取不完整")

        limit = None
        off = 0
        existing = []
        for _ in range(ncmds):
            cmd, cmdsize = struct.unpack("<II", lc_blob[off:off + 8])
            if cmdsize < 8 or off + cmdsize > len(lc_blob):
                raise SystemExit("load command 表损坏 @%d" % off)
            if cmd == LC_SEGMENT_64:
                segname = lc_blob[off + 8:off + 24].rstrip(b"\0").decode("ascii", "replace")
                vmaddr, vmsize, fileoff, filesize = struct.unpack("<QQQQ", lc_blob[off + 24:off + 56])
                nsects = struct.unpack("<I", lc_blob[off + 64:off + 68])[0]
                so = off + 72
                for _ in range(nsects):
                    sect_off = struct.unpack("<I", lc_blob[so + 48:so + 52])[0]
                    if fileoff == 0 and sect_off > 0:      # __TEXT 里的真实数据起点
                        limit = sect_off if limit is None else min(limit, sect_off)
                    so += 80
            if cmd in (LC_LOAD_DYLIB, 0x18, 0x1F, 0x8000001F):  # 记录已有 dylib 防重复
                noff = struct.unpack("<I", lc_blob[off + 8:off + 12])[0]
                nm = lc_blob[off + noff:off + cmdsize].split(b"\0")[0].decode("ascii", "replace")
                existing.append(nm)
            off += cmdsize

        if limit is None:
            raise SystemExit("没找到 __TEXT 第一条 section 的起始 offset，拒绝盲写")

        if load_path in existing:
            print("[=] 已经存在 %s，跳过注入" % load_path)
            return False

        raw = load_path.encode("utf-8") + b"\0"
        name_pad = (len(raw) + 7) & ~7
        cmdsize = 24 + name_pad
        end = 32 + sizeofcmds
        if end + cmdsize > limit:
            raise SystemExit("header padding 不够：需要 %d 字节，只剩 %d" % (cmdsize, limit - end))

        dylib_cmd = struct.pack("<IIIIII", LC_LOAD_DYLIB, cmdsize, 24, 2, 0x00010000, 0x00010000)
        blob = dylib_cmd + raw + b"\0" * (name_pad - len(raw))

        f.seek(end)
        original = f.read(cmdsize)
        f.seek(end)
        f.write(blob)

        # 回填 ncmds / sizeofcmds
        f.seek(16)
        f.write(struct.pack("<II", ncmds + 1, sizeofcmds + cmdsize))

        print("[+] 注入 %s" % load_path)
        print("    ncmds      %d -> %d" % (ncmds, ncmds + 1))
        print("    sizeofcmds %d -> %d  (上界 %d)" % (sizeofcmds, sizeofcmds + cmdsize, limit))
        print("    覆盖原 padding 前 %d 字节: %s" % (cmdsize, original.hex()[:48]))
        return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ipa", required=True)
    ap.add_argument("--dylib", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--load-path", default=None, help="默认 @executable_path/<dylib 文件名>")
    args = ap.parse_args()

    dylib_name = os.path.basename(args.dylib)
    load_path = args.load_path or ("@executable_path/" + dylib_name)

    work = tempfile.mkdtemp(prefix="inject_")
    try:
        print("[*] 解包 ->", work)
        with zipfile.ZipFile(args.ipa) as z:
            z.extractall(work)

        app = find_app_dir(work)
        exe = os.path.basename(app)[:-4]  # 去掉 .app
        bin_path = os.path.join(app, exe)
        if not os.path.isfile(bin_path):
            # 兜底：从 Info.plist 读真实可执行名
            import plistlib
            with open(os.path.join(app, "Info.plist"), "rb") as fp:
                exe = plistlib.load(fp)["CFBundleExecutable"]
            bin_path = os.path.join(app, exe)
        if not os.path.isfile(bin_path):
            raise SystemExit("找不到主二进制")

        dst = os.path.join(app, dylib_name)
        shutil.copy2(args.dylib, dst)
        print("[+] 复制 dylib ->", dst)

        patch_macho(bin_path, load_path)

        out_abs = os.path.abspath(args.out)
        print("[*] 重新打包 ->", out_abs)
        with zipfile.ZipFile(out_abs, "w", zipfile.ZIP_DEFLATED) as z:
            for root, _, files in os.walk(work):
                for fn in files:
                    full = os.path.join(root, fn)
                    rel = os.path.relpath(full, work)
                    z.write(full, rel)
        print("[✓] 完成：%s" % out_abs)
        print("    下一步：zsign -k cert.p12 -p <密码> -m app.mobileprovision -o final.ipa -z 9 %s" % out_abs)
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
