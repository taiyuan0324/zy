#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 loon/ 源生成 GitHub 静态订阅仓库内容 -> gh/
静态托管没有 query 注入能力，所以把参数以 __SODA_ARGS__ 固化进 JS 头部，
并用「不同 JS + 不同 plugin」的方式提供参数变体。

Loon 3.5.1(983)+ 使用全新 Script 语法（script(...) / with ...），
主订阅默认输出 v2 语法；旧语法另存 -legacy 供 982 及以下版本使用。
"""
import os, json, shutil, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_JS = os.path.join(ROOT, "loon", "scripts", "soda.js")
SRC_REPLAY = os.path.join(ROOT, "loon", "scripts", "soda-replay.js")
SRC_SENTINEL = os.path.join(ROOT, "tools", "sentinel.js")
OUT = os.path.join(ROOT, "gh")

OWNER = "taiyuan0324"
REPO = "zy"
BRANCH = "main"
VER = "6"   # 改脚本后 +1，破 GitHub raw / CDN 缓存
SUB = "soda"  # 落在 zy 的 soda/ 子目录

# 关键：Loon 官方手册要求「GitHub 托管的插件/订阅 URL 必须以 http://raw 开头」。
# https://raw... 会被 Loon 直接判为非法订阅而不加载（v2~v4 零反应的根因）。
# 文件内容里的 script-path 不受此限制；jsDelivr 非 github 域名，也不受此限制。
BASES = {
    "raw":      "https://raw.githubusercontent.com/%s/%s/%s/%s" % (OWNER, REPO, BRANCH, SUB),
    "httpraw":  "http://raw.githubusercontent.com/%s/%s/%s/%s" % (OWNER, REPO, BRANCH, SUB),
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
# 诊断期扩大解密面，防 App 换域名 / 用 CDN 域名
MITM_ALL = SENTINEL_MITM


def meta(name, desc, minver=None):
    lines = [
        "#!name=%s" % name,
        "#!desc=%s" % desc,
        "#!author=海鸥",
        "#!system=ios",
        "#!homepage=https://github.com/%s/%s" % (OWNER, REPO),
    ]
    if minver:
        lines.append("#!loon_version=%s" % minver)
    lines.append("")
    return lines


def render_probe_plugin():
    """零脚本链路探针：只用 [Rule] REJECT，不下载 JS、不需要 MITM、不依赖通知权限。
    导入后打开汽水音乐，Loon「最近请求」里 api.qishui.com 显示 REJECT
    => 订阅确实被 Loon 加载；没显示 => 订阅 URL 格式/入口就是错的。"""
    lines = meta("汽水 · 链路探针（零脚本·测完删）",
                 "不加载任何 JS，只用一条 REJECT 规则验证订阅是否被 Loon 加载；测完删除本插件")
    lines += [
        "[Rule]",
        "DOMAIN,api.qishui.com,REJECT",
        "DOMAIN,beta-luna.douyin.com,REJECT",
        "",
    ]
    return "\n".join(lines)


def render_probe_http():
    """HTTP 探针：不加载任何 JS、不需要 MITM/CA、不需要汽水、不需要订阅脚本下载。
    用手机 Safari 打开 http://neverssl.com 验证 Loon 的规则引擎/TUN 是否活着。"""
    lines = meta("Loon · HTTP 引擎探针（Safari 测·零依赖）",
                 "不加载 JS、不需要 MITM/CA、不需要汽水；Safari 打开 http://neverssl.com 应看不到页面")
    lines += [
        "[Rule]",
        "DOMAIN,neverssl.com,REJECT",
        "DOMAIN,www.neverssl.com,REJECT",
        "",
    ]
    return "\n".join(lines)


def render_probe3(safe=False):
    """探针 v3：插件内直接掐 QUIC + 大范围后缀匹配，不用改主配置 [General]。
    safe=True 时去掉 AND 复合规则（老版本可能不认），只留域名规则。"""
    name = "汽水 · 链路探针 v3（掐QUIC+后缀匹配·测完删）" if not safe else \
           "汽水 · 链路探针 v3-safe（无AND规则·测完删）"
    desc = "不改主配置：插件内直接 REJECT UDP443 逼 App 回落 TCP；后缀匹配暴露 App 真实域名"
    lines = meta(name, desc)
    lines += ["[Rule]"]
    if not safe:
        lines += [
            "# A. 掐 QUIC(UDP 443)，等价 disable-udp-ports=443，但写成规则不用动主配置",
            "AND,((PROTOCOL,UDP),(DEST-PORT,443)),REJECT",
        ]
    lines += [
        "# B. 对照组：开着浏览器打不开 www.qq.com，说明规则引擎/插件加载都活着",
        "DOMAIN,www.qq.com,REJECT",
        "# C. 汽水侧：精确 + 后缀，命中就会在「最近请求」里留下真实 hostname",
        "DOMAIN,beta-luna.douyin.com,REJECT",
        "DOMAIN-SUFFIX,snssdk.com,REJECT",
        "DOMAIN-SUFFIX,bytegecko.com,REJECT",
        "DOMAIN-SUFFIX,douyinpic.com,REJECT",
        "DOMAIN-SUFFIX,bytedance.net,REJECT",
        "",
        "# D. 这一组不解密不拒绝，只开 MITM：如果流量真进来了，会在「最近请求」显示明文 :path",
        "[MITM]",
        "hostname = *.qishui.com, api.qishui.com, conf.qishui.com",
        "",
    ]
    return "\n".join(lines)


def render_probe_http2():
    """国内可达的 HTTP 引擎探针：neverssl.com 在国内本身可能不通，会误判成 REJECT 生效。
    换成本土一定可达的 HTTP 域名 + neverssl 对照，双证据。"""
    lines = meta("Loon · HTTP 引擎探针 v2（国内可达·Safari 测）",
                 "三个纯 HTTP 域名全部 REJECT；关掉本插件后应全部恢复，以此判定 Loon 是否接管流量")
    lines += [
        "[Rule]",
        "# 国内一定可达，关掉插件必能打开",
        "DOMAIN,www.qq.com,REJECT",
        "DOMAIN,qq.com,REJECT",
        "DOMAIN,www.163.com,REJECT",
        "# 海外对照（若本来就不通，说明网络问题而非 REJECT）",
        "DOMAIN,neverssl.com,REJECT",
        "DOMAIN,www.neverssl.com,REJECT",
        "",
    ]
    return "\n".join(lines)


def render_force_tcp():
    """掐 QUIC/UDP443 + 放宽解密域名。只放 [Rule]/[MITM]（插件确定支持的段），
    [General] 参数另存 soda-diagnostic-general.txt 让用户粘进主配置，避免插件解析器忽略整段。"""
    lines = meta("汽水 · 强制 TCP 回落（防 QUIC 绕过）",
                 "掐 UDP443/QUIC 逼 App 回落 TCP 让 MITM 解密；诊断期用，会影响其它 App 的 QUIC")
    lines += [
        "[Rule]",
        "# 3.5.1+ 可直接用：PROTOCOL,QUIC,REJECT（若报规则无效就删掉此注释下方两行之一）",
        "AND,((PROTOCOL,UDP),(DEST-PORT,443)),REJECT",
        "",
        "[MITM]",
        "hostname = " + MITM_ALL,
        "",
    ]
    return "\n".join(lines)


def render_diagnostic_general():
    """要粘进【主配置】[General] 段的诊断参数（不放插件里，插件 [General] 支持项有限）。
    sni-sniffing：App 硬编码 IP / HTTPDNS 时靠 TLS SNI 反查域名做规则匹配
    domain-reject-mode=Request：绕开 HTTPDNS，在转发阶段执行域名拒绝
    disable-udp-ports / udp-fallback-mode / disable-stun：掐 QUIC 逼回落 TCP
    """
    return "\n".join([
        "# 汽水诊断参数 —— 粘到 Loon【主配置】的 [General] 段，用完删掉",
        "# 1) App 用 HTTPDNS / 硬编码 IP 时靠 TLS SNI 反查域名，让 DOMAIN 规则能匹配",
        "#    3.5.0(968)+ 已自动探测，旧版才需显式写；写了无害",
        "sni-sniffing = true",
        "# 2) 域名拒绝放到转发阶段执行，绕开自建 DNS（默认 DNS 阶段会被 HTTPDNS 绕过）",
        "domain-reject-mode = Request",
        "# 3) 掐 QUIC(UDP 443)，逼 App 回落 TCP，MITM 才能解密",
        "#    与 soda-force-tcp.plugin 的 AND 规则二选一即可，不必重复",
        "disable-udp-ports = 443",
        "udp-fallback-mode = REJECT",
        "disable-stun = true",
        "",
    ])


def render_plugin_v2(base, js_rel, name, desc, mitm_section="[MITM]"):
    """新语法：response if ${url} ~= /.../ then script(...) with ...
    mitm_section 可切 [Mitm]（官方 3.5.1+ Plugin 示例写法），排除段名大小写导致解密段被忽略。"""
    path = (base + "/" + js_rel + "?v=" + VER) if base else js_rel
    lines = meta(name, desc, "3.5.1(983)") + ["[Script]"]
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
    lines += ["", mitm_section, "hostname = api.qishui.com, beta-luna.douyin.com", ""]
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
    # 源文件可能自带一行 var __SODA_ARGS__（本地调试用）。必须先剥掉，
    # 否则生成物里两行 var，后者覆盖注入值，所有参数变体全部失效。
    src = re.sub(r"(?m)^\s*var\s+__SODA_ARGS__\s*=\s*\{[^}]*\}\s*;\s*\r?\n",
                 "", src.replace("\r\n", "\n"), count=1)
    head = "var __SODA_ARGS__ = %s;\n" % json.dumps(cfg, ensure_ascii=False, separators=(",", ":"))
    return head + src


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
    # 保守备选：连 script-path 也用 http://raw（排除 Loon 对远程脚本 URL 的格式检查）
    write("soda-noads-httpraw.plugin",
          render_plugin_v2(BASES["httpraw"], "scripts/soda.js",
                           "汽水音乐 · 激励广告配置改写（http-raw 通道）",
                           "新语法；订阅 URL 与脚本 URL 均为 http://raw 前缀，排除格式检查问题"))
    write("soda-noads.conf",
          render_plugin_v2(BASES["raw"], "scripts/soda.js",
                           "汽水音乐 · 激励广告配置改写",
                           "订阅脚本入口用；内容与 soda-noads.plugin 一致（新语法）"))
    # 段名变体：官方 3.5.1+ Plugin 示例用 [Mitm]，旧社区插件用 [MITM]，两个都给
    write("soda-noads-mitm.plugin",
          render_plugin_v2(BASES["raw"], "scripts/soda.js",
                           "汽水音乐 · 激励广告配置改写（[Mitm] 段名）",
                           "若 [MITM] 段在新版被忽略导致不解密，换这条；新语法不变",
                           mitm_section="[Mitm]"))

    # 2.5) 零依赖诊断：完全绕开 https / MITM / CA / 汽水 / 订阅脚本下载
    write("soda-probe.plugin", render_probe_plugin())
    write("soda-probe-jsdelivr.plugin", render_probe_plugin())
    write("soda-probe-http.plugin", render_probe_http())
    write("soda-probe-http2.plugin", render_probe_http2())
    write("soda-probe3.plugin", render_probe3())
    write("soda-probe3-safe.plugin", render_probe3(safe=True))
    write("soda-force-tcp.plugin", render_force_tcp())
    write("soda-diagnostic-general.txt", render_diagnostic_general())

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
    write("local/soda-probe.plugin", render_probe_plugin())
    write("local/soda-probe-http.plugin", render_probe_http())
    write("local/soda-probe-http2.plugin", render_probe_http2())
    write("local/soda-probe3.plugin", render_probe3())
    write("local/soda-probe3-safe.plugin", render_probe3(safe=True))
    write("local/soda-force-tcp.plugin", render_force_tcp())
    write("local/soda-noads-mitm.plugin",
          render_plugin_v2("", "scripts/soda.js", "汽水音乐 · 免广告领时长（离线·[Mitm]）",
                           "若 [MITM] 段被忽略导致不解密，换这条", mitm_section="[Mitm]"))
    write("local/soda-diagnostic-general.txt", render_diagnostic_general())
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
