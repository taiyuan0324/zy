# 汽水音乐 · 激励广告配置改写（Loon 订阅）

仓库：`taiyuan0324/zy`，本目录 `soda/`。仓库根目录的 `qishui_vip.plugin` / `qishui_vip.js` 已删除（那两个只清开屏与信息流广告，不碰激励时长）。

只改写服务端**响应**里的倒计时字段，让 App 自己走完流程并发出**它自己签名**的领奖请求；请求体一个字节都不碰（请求带 `x-ss-stub`=md5(body)、`x-gorgon`、`x-helios`、`x-medusa`、`bd-ticket-guard` 多重签名，改了必被拒）。

---

## 1. 先选对版本（重要）

Loon **3.5.1(983)** 起换了全新 Script 语法：旧写法 `http-response ... script-path=...` 换成 `response if ${url} ~= /.../ then script(...) with ...`。版本选错会出现脚本被挂成 `CRON`、类型识别异常等问题。

| 你的 Loon | 订阅文件 |
|---|---|
| **3.5.1(983) 及以上**（含 3.5.3 / 1014） | `soda-noads.plugin` ← **主推** |
| 3.5.1(982) 及以下 | `soda-noads-legacy.plugin` |

截图环境是 `Loon 3.5.3(1014)`，用主地址。

**主地址（新语法 · GitHub raw）**

```
https://raw.githubusercontent.com/taiyuan0324/zy/main/soda/soda-noads.plugin
```

Loon 官方手册对 GitHub 文件的订阅地址要求**以 `http://raw` 开头**；若报格式错误改用：

```
http://raw.githubusercontent.com/taiyuan0324/zy/main/soda/soda-noads.plugin
```

| 备用 / 兼容地址 | URL |
|---|---|
| jsDelivr（新语法） | `https://cdn.jsdelivr.net/gh/taiyuan0324/zy@main/soda/soda-noads-jsdelivr.plugin` |
| 旧语法（Loon ≤982） | `https://raw.githubusercontent.com/taiyuan0324/zy/main/soda/soda-noads-legacy.plugin` |
| 订阅脚本入口 | `https://raw.githubusercontent.com/taiyuan0324/zy/main/soda/soda-noads.conf` |

> 从旧版订阅换到新语法后，建议**删除旧插件再重新添加**，别只刷新，避免残留规则。

---

## 2. 关于 `Script Type: CRON` 和 `Can't find variable: $request`

在「脚本」页面点开 `soda.js` 手动运行时，Loon 会用 **CRON / Generic 上下文**执行，此时**不注入** `$request` / `$response`（只有 http-request / http-response 触发才有）。旧版脚本顶层直接引用这两个变量，于是抛：

```
[JS Exception]:ReferenceError: Can't find variable: $request
```

**这不是订阅失败，也不是脚本坏了**。脚本现在已加无上下文守卫：CRON / 手动运行时打印一行提示并 `$done({})` 安全退出，不再抛异常。

正确验证方式：

1. Loon → 配置 → **插件**，确认订阅已加载、5 条 `response` 规则都启用、类型显示为 Response Script（不是 CRON）
2. 打开汽水音乐，触发一次「看广告领 VIP」
3. Loon → 脚本 → 日志，看 `[汽水]` 前缀输出（例如 `ads/config 改写: ...`）
4. 观察倒计时是否约 1 秒结束

**不要**用「脚本 → 运行」来判断这插件是否生效。

---

## 3. 导入步骤

1. Loon → 配置 → 插件 → `+` → **添加插件 URL** → 粘贴主地址
2. 打开插件开关（会提示添加 MITM 域名，确认）
3. 确认 MITM 含 `api.qishui.com`、`beta-luna.douyin.com`；iOS 需安装并**信任** CA 证书（设置 → 通用 → 关于本机 → 证书信任设置）
4. 按上一节用真实请求验证

---

## 4. 参数与变体

默认参数固化在 `scripts/soda.js` 第一行 `var __SODA_ARGS__ = {...}`：

| 参数 | 默认 | 说明 |
|---|---|---|
| `duration` | 1 | 目标倒计时秒数 |
| `adsconfig` | 1 | 改写 `/luna/ads/config` 的 `reward_duration` |
| `incentcfg` | 1 | 改写 `/luna/advert/incentive/config` 的 `advert_duration` |
| `retrieve` | 0 | 是否连 `/incentive/retrieve` 的 `launch_duration` 一起改（第二档） |
| `freq` | 1000 | 把 `freq_per_day` 抬到该值（0=不改） |
| `video` | 0 | 替换广告素材 URL（需 `videourl` + `videomd5`，客户端校验 md5） |
| `fake` | 0 | done 失败时本地伪成功（**仅 UI，无真实权益**） |
| `verbose` | 1 | 日志开关 |

换参数最省事：换订阅 URL（均为新语法）

| 变体 | 订阅 URL | 用途 |
|---|---|---|
| `retrieve` | `https://raw.githubusercontent.com/taiyuan0324/zy/main/soda/variants/retrieve.plugin` | 改完仍等 30 秒时用这档 |
| `d5` | `https://raw.githubusercontent.com/taiyuan0324/zy/main/soda/variants/d5.plugin` | 保守档，5 秒 |
| `fake` | `https://raw.githubusercontent.com/taiyuan0324/zy/main/soda/variants/fake.plugin` | 只看 UI 流程 |
| **方案 C 重放** | `https://raw.githubusercontent.com/taiyuan0324/zy/main/soda/variants/replay.plugin` | 服务端硬校验 30s 时用；绑定 **http-request** 规则，截获 done → 本地秒成功 → 原样重放 |

其他改法：

- 直接编辑 `soda/scripts/soda.js` 第一行 → 提交 → 把各 `.plugin` 里 script-path 的 `?v=2` 递增（破缓存）→ Loon 刷新订阅
- Loon 插件 `[Argument]`（Build 733+）：脚本对 `$argument` 的 String / Object / null 都做了兼容
- `$persistentStore` 写 key `soda.cfg`，值形如 `duration=5&verbose=1`，优先级最高

---

## 5. 缓存与更新

| 项 | 说明 |
|---|---|
| GitHub raw | 约 5 分钟缓存；script-path 后 `?v=2` 递增即可破 |
| jsDelivr `@main` | 约 12 小时；可用 commit sha：`...@<40位sha>/soda/scripts/soda.js` |
| Loon 侧 | 订阅请求带 `If-None-Match`，改文件后 ETag 会变；必要时删除插件重新添加 |

改完在 Loon 里**刷新订阅 + 重启插件**。

---

## 6. 排错

| 现象 | 处理 |
|---|---|
| `Script Type: CRON` / `$request undefined` | 见第 2 节：手动运行属正常现象，脚本已安全跳过；用真实请求验证 |
| 插件里规则显示为 CRON 而非 Response | 版本选错，换 `soda-noads-legacy.plugin`（≤982）或确认主订阅是新语法 |
| 订阅加载失败 / 报格式错误 | 按第 1 节把 `https://raw` 换成 `http://raw` 开头 |
| 订阅成功但脚本下载超时 | 手机浏览器打开 plugin 里那条 `script-path` URL，确认能返回 JS 文本 |
| 完全无 `[汽水]` 日志 | MITM 没生效：CA 未信任 / 域名未加 / App 走 QUIC(HTTP/3)，关掉该 App 的 UDP 或开强制 HTTPS 解密 |
| 还是等 30 秒 | 换 `variants/retrieve.plugin`；再看日志里哪个字段没被改到 |
| `status_code≠0` | 服务端按自己时钟校验了 30 秒，改走 `variants/replay.plugin` |
| 多个订阅同时超时 | 抓包里 `adrules.top` / `yfamilys.com` / `kelee.one` 等订阅请求同样只有 request 没有 response，属于本机网络 / DNS / Loon 隧道整体问题，先排查代理与 DNS |
| 短时狂刷后失效 | `freq_per_day` 只是**客户端**上限，服务端自己有统计，会触发风控。别贪 |

---

## 7. 校验面提醒

- 请求侧不可改：`x-ss-stub = md5(body)` 已实测一致；`x-gorgon`(20B) 含 body/时间，`x-helios`、`x-medusa`、`bd-ticket-guard-static-sign`(DER ECDSA-P256) 均为设备/签名绑定，重算不现实
- `time_token` 是服务端密钥加密的 AEAD 密文（约 76 字符），客户端无法伪造，只能原样透传
- 因此本方案**只改响应**；若服务端用自己下发的时长做时序校验，唯一补法是重放（见上）
- 仅供个人设备调试与协议学习使用

---

## 8. 文件清单（均位于仓库 `soda/` 下）

| 路径 | 说明 |
|---|---|
| `soda-noads.plugin` | **主订阅**，Loon 983+ 新语法，raw 通道 |
| `soda-noads-jsdelivr.plugin` | 新语法 + jsDelivr 备用通道 |
| `soda-noads-legacy.plugin` | 旧语法，Loon ≤982 |
| `soda-noads.conf` | 「订阅脚本」入口别名（新语法） |
| `scripts/soda.js` | 主脚本，5 条路由统一分发，含 CRON 无上下文守卫 |
| `scripts/soda-replay.js` | 方案 C 兜底脚本，同样含守卫 |
| `variants/*.plugin` + `variants/soda-*.js` | 参数变体 / 重放订阅 |
| `local/` | 离线版（相对 script-path），整目录打包 zip 可直接导入 |
| `tools/build.py` | 从 `loon/` 源重新生成本目录内容 |
