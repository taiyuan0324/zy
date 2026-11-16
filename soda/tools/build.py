#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 loon/ 源生成 GitHub 静态订阅仓库内容 -> gh/
静态托管没有 query 注入能力，所以把参数以 __SODA_ARGS__ 固化进 JS 头部，
并用「不同 JS + 不同 plugin」的方式提供参数变体。

Loon 3.5.1(983)+ 使用全新 Script 语法（script(...) / with ...），
主订阅默认输出 v2 语法；旧语法另存 -legacy 供 982 及以下版本使用。
"""
import os, json, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_JS = os.path.join(ROOT, "loon", "scripts", "soda.js")
SRC_REPLAY = os.path.join(ROOT, "loon", "scripts", "soda-replay.js")
OUT = os.path.join(ROOT, "gh")

OWNER = "taiyuan0324"
REPO = "zy"
BRANCH = "main"
VER = "2"   # 改脚本后 +1，破 GitHub raw / CDN 缓存
SUB = "soda"  # 落在 zy 的 soda/ 子目录

BASES = {
    "raw":      "https://raw.githubusercontent.com/%s/%s/%s/%s" % (OWNER, REPO, BRANCH, SUB),
    "jsdelivr": "https://cdn.jsdelivr.net/gh/%s/%s@%s/%s" % (OWNER, REPO, BRANCH, SUB),
}

DEFAULT = {
    "duration": 1, "adsconfig": 1, "incentcfg": 1, "retrieve": 0,
    "freq": 1000, "video": 0, "fake": 0, "verbose": 1
}
VARIANTS = {
    "retrieve": ({"retrieve": 1, "incentcfg": 1}, "第二档：连 retrieve 的 launch_duration 一起压到 1s"),
    "d5":       ({"duration": 5},                 "保守档：倒计时压到 5s，降低服务端时钟校验风险"),
    "fake":     ({"fake": 1, "verbose": 1},      "调试档：done 失败时本地伪成功（仅 UI，无真实权益）"),
}

# 旧语法（Loon <= 3.5.1(982)）
ROUTES_LEGACY = [
    (r"^https?:\/\/api\.qishui\.com\/luna\/ads\/config", "汽水-广告总配置"),
    (r"^https?:\/\/beta-luna\.douyin\.com\/luna\/advert\/incentive\/config", "汽水-激励配置"),
    (r"^https?:\/\/beta-luna\.douyin\.com\/luna\/advert\/incentive\/retrieve", "汽水-广告素材"),
    (r"^https?:\/\/api\.qishui\.com\/luna\/advert\/incentive\/done", "汽水-领奖回调"),
    (r"^https?:\/\/beta-luna\.douyin\.com\/{1,2}luna\/advert\/fallback\/done\/info", "汽水-兜底token"),
]

# 新语法（Loon >= 3.5.1(983)）：Response Script 强制要求 URL guard
ROUTES_V2 = [
    (r"/^https?:\/\/api\.qishui\.com\/luna\/ads\/config/", "汽水-广告总配置"),
    (r"/^https?:\/\/beta-luna\.douyin\.com\/luna\/advert\/incentive\/config/", "汽水-激励配置"),
    (r"/^https?:\/\/beta-luna\.douyin\.com\/luna\/advert\/incentive\/retrieve/", "汽水-广告素材"),
    (r"/^https?:\/\/api\.qishui\.com\/luna\/advert\/incentive\/done/", "汽水-领奖回调"),
    (r"/^https?:\/\/beta-luna\.douyin\.com\/{1,2}luna\/advert\/fallback\/done\/info/", "汽水-兜底token"),
]
REPLAY_V2 = r"/^https?:\/\/api\.qishui\.com\/luna\/advert\/incentive\/done/"


def meta(name, desc):
    return [
        "#!name=%s" % name,
        "#!desc=%s" % desc,
        "#!author=海鸥",
        "#!system=ios",
        "#!homepage=https://github.com/%s/%s" % (OWNER, REPO),
        "",
    ]


def render_plugin_v2(base, js_rel, name, desc):
    """新语法：response if ${url} ~= /.../ then script(...) with ..."""
    path = (base + "/" + js_rel + "?v=" + VER) if base else js_rel
    lines = meta(name, desc) + ["[Script]"]
    for regex, tag in ROUTES_V2:
        lines.append(
            'response if ${url} ~= %s then script("%s") with tag="%s", timeout=30, requires_body=true, enable=true'
            % (regex, path, tag)
        )
    lines += ["", "[MITM]", "hostname = api.qishui.com, beta-luna.douyin.com", ""]
    return "\n".join(lines)


def render_plugin_legacy(base, js_rel, name, desc):
    """旧语法：http-response <regex> script-path=...（不含 max-size 也兼容）"""
    path = (base + "/" + js_rel + "?v=" + VER) if base else js_rel
    lines = meta(name, desc) + ["[Script]"]
    for pattern, tag in ROUTES_LEGACY:
        lines.append(
            "http-response %s script-path=%s,requires-body=true,max-size=10485760,timeout=30,tag=%s,enable=true"
            % (pattern, path, tag)
        )
    lines += ["", "[MITM]", "hostname = api.qishui.com, beta-luna.douyin.com", ""]
    return "\n".join(lines)


def render_replay_v2(base):
    """方案 C：新语法 http-request 拦截 done → 本地假成功 + 原样重放"""
    path = (base + "/scripts/soda-replay.js?v=" + VER) if base else "scripts/soda-replay.js"
    lines = meta("汽水音乐 · done 重放（方案 C）",
                 "截获 done → 本地秒成功 → 原样重放；仅当服务端强校验 30s 时使用")
    lines += [
        "[Script]",
        'request if ${url} ~= %s then script("%s") with tag="汽水-done重放", timeout=30, requires_body=true, enable=true'
        % (REPLAY_V2, path),
        "",
        "[MITM]",
        "hostname = api.qishui.com",
        "",
    ]
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

    # 1) 脚本
    write("scripts/soda.js", render_js(DEFAULT))
    write("scripts/soda-replay.js", open(SRC_REPLAY, encoding="utf-8").read())

    # 2) 主订阅：v2 新语法（raw / jsdelivr）+ legacy 旧语法
    write("soda-noads.plugin",
          render_plugin_v2(BASES["raw"], "scripts/soda.js",
                           "汽水音乐 · 激励广告配置改写（新语法）",
                           "Loon 3.5.1(983)+ 新版 Script 语法；只改响应压缩倒计时，[Script]+[MITM]"))
    write("soda-noads-jsdelivr.plugin",
          render_plugin_v2(BASES["jsdelivr"], "scripts/soda.js",
                           "汽水音乐 · 激励广告配置改写（新语法·jsDelivr）",
                           "Loon 3.5.1(983)+ 新版 Script 语法；jsDelivr CDN 通道"))
    write("soda-noads-legacy.plugin",
          render_plugin_legacy(BASES["raw"], "scripts/soda.js",
                               "汽水音乐 · 激励广告配置改写（旧语法）",
                               "Loon 3.5.1(982) 及以下用这条；旧版 Script 语法"))
    write("soda-noads.conf",
          render_plugin_v2(BASES["raw"], "scripts/soda.js",
                           "汽水音乐 · 激励广告配置改写",
                           "订阅脚本入口用；内容与 soda-noads.plugin 一致（新语法）"))

    # 3) 参数变体（v2）
    for name, (override, desc) in VARIANTS.items():
        cfg = dict(DEFAULT)
        cfg.update(override)
        js_rel = "variants/soda-%s.js" % name
        write(js_rel, render_js(cfg))
        write("variants/%s.plugin" % name,
              render_plugin_v2(BASES["raw"], js_rel, "汽水音乐 · %s" % name,
                               desc + "；新语法"))

    # 4) 方案 C 重放（v2 http-request）
    write("variants/replay.plugin", render_replay_v2(BASES["raw"]))

    # 5) 本地离线导入版
    write("local/soda-noads.plugin",
          render_plugin_v2("", "scripts/soda.js", "汽水音乐 · 免广告领时长（离线·新语法）",
                           "下载整个 local/ 打包 zip 导入 Loon，无需外网"))
    write("local/soda-noads-legacy.plugin",
          render_plugin_legacy("", "scripts/soda.js", "汽水音乐 · 免广告领时长（离线·旧语法）",
                               "Loon 982 及以下用这条"))
    write("local/scripts/soda.js", render_js(DEFAULT))
    write("local/scripts/soda-replay.js", open(SRC_REPLAY, encoding="utf-8").read())

    # 6) 构建脚本与 README
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
