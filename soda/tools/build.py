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
SRC_SENTINEL = os.path.join(ROOT, "tools", "sentinel.js")
OUT = os.path.join(ROOT, "gh")

OWNER = "taiyuan0324"
REPO = "zy"
BRANCH = "main"
VER = "4"   # 改脚本后 +1，破 GitHub raw / CDN 缓存
SUB = "soda"  # 落在 zy 的 soda/ 子目录

BASES = {
    "raw":      "https://raw.githubusercontent.com/%s/%s/%s/%s" % (OWNER, REPO, BRANCH, SUB),
    "jsdelivr": "https://cdn.jsdelivr.net/gh/%s/%s@%s/%s" % (OWNER, REPO, BRANCH, SUB),
}

DEFAULT = {
    "duration": 1, "adsconfig": 1, "incentcfg": 1, "retrieve": 1, "alltime": 1,
    "freq": 1000, "notify": 1, "snapshot": 1, "probe": 1, "video": 0,
    "fake": 0, "verbose": 1
}
VARIANTS = {
    "d5":       ({"duration": 5},                        "保守档：倒计时压到 5s，降低服务端时钟校验风险"),
    "quiet":    ({"notify": 0, "snapshot": 0, "verbose": 0}, "静默档：关掉命中通知与日志，功能完全一致"),
    "original": ({"retrieve": 0, "alltime": 0},          "对照档：恢复 v2 行为（只改 ads/config + incentcfg）"),
    "fake":     ({"fake": 1, "verbose": 1},              "调试档：done 失败时本地伪成功（仅 UI，无真实权益）"),
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
# 哨兵：极宽 URL 匹配，用来判定「Loon 有没有执行插件脚本」这条链路
SENTINEL_V2 = r"/(qishui|luna|douyin|bytedance|snssdk|bytegecko)/i"
SENTINEL_MITM = ("*.qishui.com, *.douyin.com, *.douyinpic.com, *.snssdk.com, "
                 "*.bytedance.net, *.bytegecko.com, api.qishui.com, "
                 "beta-luna.douyin.com, conf.qishui.com")


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
    # request 阶段只观测不改：确认 App 实际上报的 launch_duration
    lines.append(
        'request if ${url} ~= %s then script("%s") with tag="汽水-领奖请求观测", timeout=30, requires_body=true, enable=true'
        % (REPLAY_V2, path)
    )
    lines += ["", "[MITM]", "hostname = api.qishui.com, beta-luna.douyin.com", ""]
    return "\n".join(lines)


def render_plugin_legacy(base, js_rel, name, desc):
    """旧语法：http-response <regex> script-path=..."""
    path = (base + "/" + js_rel + "?v=" + VER) if base else js_rel
    lines = meta(name, desc) + ["[Script]"]
    for pattern, tag in ROUTES_LEGACY:
        lines.append(
            "http-response %s script-path=%s,requires-body=true,max-size=10485760,timeout=30,tag=%s,enable=true"
            % (pattern, path, tag)
        )
    lines.append(
        "http-request ^https?:\\/\\/api\\.qishui\\.com\\/luna\\/advert\\/incentive\\/done script-path=%s,requires-body=true,timeout=30,tag=汽水-领奖请求观测,enable=true"
        % path
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


def render_sentinel_v2(base):
    """链路哨兵：极宽 URL 正则 + 通配 MITM，只发通知与日志，不改包"""
    path = (base + "/scripts/sentinel.js?v=" + VER) if base else "scripts/sentinel.js"
    lines = meta("汽水 · 链路哨兵（只诊断）",
                 "极宽 URL 匹配，命中即通知并打印真实 URL；诊断时只启用本插件，用完关闭")
    lines += [
        "[Script]",
        'response if ${url} ~= %s then script("%s") with tag="汽水-哨兵-RESP", timeout=30, requires_body=true, enable=true'
        % (SENTINEL_V2, path),
        'request if ${url} ~= %s then script("%s") with tag="汽水-哨兵-REQ", timeout=30, requires_body=true, enable=true'
        % (SENTINEL_V2, path),
        "",
        "[MITM]",
        "hostname = " + SENTINEL_MITM,
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

    sentinel_src = open(SRC_SENTINEL, encoding="utf-8").read()

    # 1) 脚本
    write("scripts/soda.js", render_js(DEFAULT))
    write("scripts/soda-replay.js", open(SRC_REPLAY, encoding="utf-8").read())
    write("scripts/sentinel.js", sentinel_src)

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

    # 3) 链路哨兵（诊断用，独立插件）
    write("soda-sentinel.plugin", render_sentinel_v2(BASES["raw"]))
    write("soda-sentinel-jsdelivr.plugin", render_sentinel_v2(BASES["jsdelivr"]))

    # 4) 参数变体（v2）
    for name, (override, desc) in VARIANTS.items():
        cfg = dict(DEFAULT)
        cfg.update(override)
        js_rel = "variants/soda-%s.js" % name
        write(js_rel, render_js(cfg))
        write("variants/%s.plugin" % name,
              render_plugin_v2(BASES["raw"], js_rel, "汽水音乐 · %s" % name,
                               desc + "；新语法"))

    # 5) 方案 C 重放（v2 http-request）
    write("variants/replay.plugin", render_replay_v2(BASES["raw"]))

    # 6) 本地离线导入版
    write("local/soda-noads.plugin",
          render_plugin_v2("", "scripts/soda.js", "汽水音乐 · 免广告领时长（离线·新语法）",
                           "下载整个 local/ 打包 zip 导入 Loon，无需外网"))
    write("local/soda-noads-legacy.plugin",
          render_plugin_legacy("", "scripts/soda.js", "汽水音乐 · 免广告领时长（离线·旧语法）",
                               "Loon 982 及以下用这条"))
    write("local/soda-sentinel.plugin", render_sentinel_v2(""))
    write("local/scripts/soda.js", render_js(DEFAULT))
    write("local/scripts/soda-replay.js", open(SRC_REPLAY, encoding="utf-8").read())
    write("local/scripts/sentinel.js", sentinel_src)

    # 7) 构建脚本与 README
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
