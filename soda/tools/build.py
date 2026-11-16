#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 loon/ 源生成 GitHub 静态订阅仓库内容 -> gh/
静态托管没有 query 注入能力，所以把参数以 __SODA_ARGS__ 固化进 JS 头部，
并用「不同 JS + 不同 plugin」的方式提供参数变体。
"""
import os, json, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_JS = os.path.join(ROOT, "loon", "scripts", "soda.js")
SRC_REPLAY = os.path.join(ROOT, "loon", "scripts", "soda-replay.js")
OUT = os.path.join(ROOT, "gh")

OWNER = "taiyuan0324"
REPO = "zy"
BRANCH = "main"
VER = "1"
# 本订阅落在 zy 仓库的 soda/ 子目录，不覆盖仓库根目录已有的 qishui_vip.*
SUB = "soda"

BASES = {
    "raw":      "https://raw.githubusercontent.com/%s/%s/%s/%s" % (OWNER, REPO, BRANCH, SUB),
    "jsdelivr": "https://cdn.jsdelivr.net/gh/%s/%s@%s/%s" % (OWNER, REPO, BRANCH, SUB),
}

DEFAULT = {
    "duration": 1, "adsconfig": 1, "incentcfg": 1, "retrieve": 0,
    "freq": 1000, "video": 0, "fake": 0, "verbose": 1
}
VARIANTS = {
    # 文件名 -> (参数覆盖, 说明)
    "retrieve": ({"retrieve": 1, "incentcfg": 1}, "第二档：连 retrieve 的 launch_duration 一起压到 1s"),
    "d5":       ({"duration": 5},                 "保守档：倒计时压到 5s，降低服务端时钟校验风险"),
    "fake":     ({"fake": 1, "verbose": 1},      "调试档：done 失败时本地伪成功（仅 UI，无真实权益）"),
}

ROUTES = [
    (r"^https?:\/\/api\.qishui\.com\/luna\/ads\/config", "汽水-广告总配置"),
    (r"^https?:\/\/beta-luna\.douyin\.com\/luna\/advert\/incentive\/config", "汽水-激励配置"),
    (r"^https?:\/\/beta-luna\.douyin\.com\/luna\/advert\/incentive\/retrieve", "汽水-广告素材"),
    (r"^https?:\/\/api\.qishui\.com\/luna\/advert\/incentive\/done", "汽水-领奖回调"),
    (r"^https?:\/\/beta-luna\.douyin\.com\/{1,2}luna\/advert\/fallback\/done\/info", "汽水-兜底token"),
]


def render_plugin(base, js_rel, name, desc):
    """base='' 表示本地相对路径版（离线导入用）"""
    lines = [
        "#!name=%s" % name,
        "#!desc=%s" % desc,
        "#!author=海鸥",
        "#!system=ios",
        "#!homepage=https://github.com/%s/%s" % (OWNER, REPO),
        "",
        "[Script]",
    ]
    for pattern, tag in ROUTES:
        path = (base + "/" + js_rel + "?v=" + VER) if base else js_rel
        lines.append(
            "http-response %s script-path=%s,requires-body=true,max-size=10485760,timeout=30,tag=%s,enable=true"
            % (pattern, path, tag)
        )
    lines += ["", "[MITM]", "hostname = api.qishui.com, beta-luna.douyin.com", ""]
    return "\n".join(lines)


def render_js(cfg, source=None):
    src = source if source is not None else open(SRC_JS, encoding="utf-8").read()
    head = "var __SODA_ARGS__ = %s;\n" % json.dumps(cfg, ensure_ascii=False, separators=(",", ":"))
    return head + src.replace("\r\n", "\n")


def write(rel, text):
    p = os.path.join(OUT, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text.replace("\r\n", "\n"))
    return p


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)

    # 1) 主脚本（默认参数）
    write("scripts/soda.js", render_js(DEFAULT))
    write("scripts/soda-replay.js", open(SRC_REPLAY, encoding="utf-8").read())

    # 2) 主订阅文件：GitHub raw 官方源 + jsDelivr 备用
    descs = {
        "raw": "GitHub raw 官方源",
        "jsdelivr": "jsDelivr CDN（备用）",
    }
    suffix = {"raw": "", "jsdelivr": "-jsdelivr"}
    for key, base in BASES.items():
        write("soda-noads%s.plugin" % suffix[key],
              render_plugin(base, "scripts/soda.js",
                            "汽水音乐 · 激励广告配置改写（%s）" % key,
                            "%s；只改写响应压缩倒计时，纯 [Script]+[MITM]，全版本 Loon 兼容" % descs[key]))
    # .conf 别名（部分 Loon 版本「订阅脚本」入口按文件名过滤）
    write("soda-noads.conf", render_plugin(BASES["raw"], "scripts/soda.js",
                                           "汽水音乐 · 激励广告配置改写",
                                           "订阅脚本入口用；内容与 soda-noads.plugin 一致"))

    # 3) 参数变体
    for name, (override, desc) in VARIANTS.items():
        cfg = dict(DEFAULT)
        cfg.update(override)
        js_rel = "variants/soda-%s.js" % name
        write(js_rel, render_js(cfg))
        write("variants/%s.plugin" % name,
              render_plugin(BASES["raw"], js_rel,
                            "汽水音乐 · %s" % name, desc + "；纯 [Script]+[MITM]"))

    # 4) 本地离线导入版（相对 script-path）
    write("local/soda-noads.plugin",
          render_plugin("", "scripts/soda.js", "汽水音乐 · 免广告领时长（离线版）",
                        "下载本目录整个 local/ 打成 zip 后导入 Loon，无需外网"))
    write("local/scripts/soda.js", render_js(DEFAULT))
    write("local/scripts/soda-replay.js", open(SRC_REPLAY, encoding="utf-8").read())

    # 5) 构建脚本与 README
    write("tools/build.py", open(os.path.abspath(__file__), encoding="utf-8").read())
    write("README.md", open(os.path.join(ROOT, "tools", "gh_readme.md"), encoding="utf-8").read())

    files = []
    for root, _, fs in os.walk(OUT):
        for f in fs:
            p = os.path.join(root, f)
            files.append((os.path.relpath(p, OUT).replace("\\", "/"), os.path.getsize(p)))
    for rel, sz in sorted(files):
        print("%7d  %s" % (sz, rel))
    print("--- %d files ---" % len(files))


if __name__ == "__main__":
    main()
