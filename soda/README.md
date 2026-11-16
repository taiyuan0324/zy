# 汽水音乐 · 激励广告配置改写（Loon 订阅）· v5

仓库：`taiyuan0324/zy`，本目录 `soda/`。

只改写服务端**响应**里的倒计时字段，让 App 自己走完流程并发出**它自己签名**的领奖请求；请求体一个字节都不碰（请求带 `x-ss-stub`=md5(body)、`x-gorgon`、`x-helios`、`x-medusa`、`bd-ticket-guard` 多重签名，改了必被拒）。

---

## 0. v5：找到「四轮零反应」的真凶了

之前给的订阅地址是：

```
https://raw.githubusercontent.com/taiyuan0324/zy/main/soda/soda-noads.plugin   ← 错的
```

**Loon 官方手册（LoonManual / Plugin_Format）逐字要求**：

> 文件上传至 github 库的，订阅地址 URL 必须以 `http://raw` 开头

`https://raw...` 会被 Loon 判为非法订阅而**直接不加载**。这解释了全部现象：

| 版本 | 订阅 URL | 结果 |
|---|---|---|
| v1 | `http://192.168.1.18:8765/...`（本地 HTTP） | 加载成功 → 有 `CRON / $request undefined` 报错，说明脚本**确实被执行过** |
| v2 / v3 / v4 | `https://raw.githubusercontent.com/...` | 订阅压根没加载 → 零规则、零日志、零通知、零效果，连哨兵都哑 |

所以 v3 改 `retrieve`、v4 修阶段判断，全都没机会跑。**不是脚本逻辑问题，是订阅 URL 格式。**

### 正确地址（任选一条，按顺序试）

```
# ① 官方要求的 GitHub 格式（主推）
http://raw.githubusercontent.com/taiyuan0324/zy/main/soda/soda-noads.plugin

# ② jsDelivr：非 github 域名，不受 http://raw 规则约束，https 直连
https://cdn.jsdelivr.net/gh/taiyuan0324/zy@main/soda/soda-noads-jsdelivr.plugin

# ③ 本地文件导入：完全不用订阅 URL（最确定，见第 3 节）
soda-noads.zip
```

> `http://raw...` 会 301 跳 https，这是 GitHub 的正常行为，Loon 会自行处理，不用管。
> 若 ① 在你网络里 301 后被重置，直接用 ②。

`?v=5` 已写进各 `.plugin` 的 `script-path` 用于破脚本缓存；**换版务必删除旧插件重新添加**，别只刷新。

---

## 1. 第一件事：跑零脚本探针

别再靠通知栏判断了。新版 Loon 的 Response Script 是 **first-match**，且 `$notification.post` 还受 iOS 通知权限影响，两者都会造成"零反应"的假象。

`soda-probe.plugin` **不加载任何 JS、不需要 MITM、不需要通知权限**，只有两条 `[Rule]` REJECT：

```
http://raw.githubusercontent.com/taiyuan0324/zy/main/soda/soda-probe.plugin
```

操作：

1. **临时只启用探针这一个插件，其它插件全部关掉**
2. 打开汽水音乐随便点几下
3. 看 Loon → **最近请求**

| 现象 | 结论 |
|---|---|
| `api.qishui.com` / `beta-luna.douyin.com` 显示 `REJECT`，汽水转圈/报错 | **订阅被成功加载了** → 链路通，之前的零反应就是 URL 格式问题。删探针，加主订阅 |
| 最近请求里照样正常 200，没有任何 REJECT | 订阅仍然没加载 → 检查填的是不是「插件 URL」入口、是不是精确复制了 `http://raw` 开头、有无多余空格；或改用 jsDelivr 那条 / 本地 zip |

探针测完**一定要删**，它会把汽水的接口全断掉。

### 探针通了之后，再跑链路哨兵（可选，判断脚本引擎）

```
http://raw.githubusercontent.com/taiyuan0324/zy/main/soda/soda-sentinel.plugin
```

极宽正则 `/(qishui|luna|douyin|bytedance|snssdk|bytegecko)/i` + 通配 MITM，不改任何包，命中就在 **Loon → 脚本 → 日志**打 `[哨兵] RESP/REQ ... | 真实URL`。同样要只开这一个插件。

| 日志 | 结论 |
|---|---|
| 有 `[哨兵]` 行 | 脚本引擎 + 远程下载都正常，主订阅能跑 |
| 连 `[哨兵]` 都没有 | 远程脚本下载失败 / MITM 没解密 / 规则被别的插件抢 |
| 出现没见过的域名或路径 | App 换了接口，把那行 URL 发我改正则 |

> CA 已信任 ≠ MITM 真的解密了。SSL pinning / QUIC(HTTP/3) 都能绕过 MITM，Loon「最近请求」里看是明文 HTTP/2 还是 CONNECT 隧道即可确认。

---

## 2. 版本对照

Loon **3.5.1(983)** 起换了全新 Script 语法，主订阅用新语法并带 `#!loon_version=3.5.1(983)` 元数据。

| 你的 Loon | 订阅文件 |
|---|---|
| **3.5.1(983)+**（含 3.5.3 / 1014） | `soda-noads.plugin` ← 主推 |
| 3.5.1(982) 及以下 | `soda-noads-legacy.plugin` |
| 新语法但怀疑远程脚本 URL 格式检查 | `soda-noads-httpraw.plugin`（订阅与脚本 URL 均 `http://raw`） |

新语法逐字按官方模板：

```ini
response if ${url} ~= /^https?:\/\/api\.qishui\.com\/luna\/ads\/config/ then script("https://.../soda.js?v=5") with tag="汽水-广告总配置", timeout=30, requires_body=true, enable=true
```

`with` 只认 `enable / tag / img_url / timeout / debug / requires_body / binary_body_mode`；Response Script 强制要求 URL guard。

---

## 3. 导入步骤

**方式 A · 本地文件（零网络依赖，最稳）**

把 `soda-noads.zip` 传到手机（AirDrop / 文件 App / iCloud），在 Loon 里以本地插件导入。包内 `soda-noads.plugin` 用相对路径 `scripts/soda.js`，不走任何远程下载，也不受 `http://raw` 规则约束。

**方式 B · 订阅 URL**

1. Loon → 配置 → **插件** → `+` → **添加插件 URL** → 粘贴第 0 节的地址
2. 打开插件开关（会提示添加 MITM 域名，确认）
3. 确认 MITM 含 `api.qishui.com`、`beta-luna.douyin.com`；iOS 需**安装并信任 CA 证书**
4. 触发一次「看广告领 VIP」，看 **Loon → 脚本 → 日志**（不是通知栏）

**不要**用「脚本 → 运行」判断生效：那是 CRON / Generic 上下文，Loon 不注入 `$request` / `$response`。脚本已加守卫，此时只打印一行提示并安全退出（历史上 `ReferenceError: Can't find variable: $request` 就是这个，不是订阅失败）。

---

## 4. 生效判定（以日志为准）

导入主订阅 → 触发一次领奖。v4/v5 脚本一执行就先打 `[汽水] EXEC ...`，命中改写打 `[汽水] HIT ...`：

| 日志 / 通知 | 结论 | 下一步 |
|---|---|---|
| 连 `EXEC` 都没有 | 规则没匹配 / 脚本没下载 / 订阅还是旧版 | 回第 1 节跑探针 + 哨兵 |
| 有 `EXEC` 但「未匹配路由」带陌生 URL | 接口换了 | 把 URL 发我改正则 |
| `HIT ... 30->1` | 改写生效 | 看下面 |
| `REQ-done 上报 launch_duration=1 ✓` | App 吃了改写 | 等 done 结果 |
| `REQ-done 上报 launch_duration=30 ✗` | App 不用这字段，另有硬编码 | 换 `variants/replay.plugin` |
| `done 成功 amount=1800s` | **成了** | — |
| `done 失败 code≠0` | 服务端按自己时钟校验 30 秒 | 换 `variants/replay.plugin` |
| 倒计时仍 30 秒但全改到 1 了 | 客户端另有本地计时/云控通道 | 抓一份**开着插件**的新包给我 |

诊断完嫌通知吵，换 `variants/quiet.plugin`。

---

## 5. 参数与变体

默认参数固化在 `scripts/soda.js` 第一行 `var __SODA_ARGS__ = {...}`：

| 参数 | 默认 | 说明 |
|---|---|---|
| `duration` | 1 | 目标倒计时秒数 |
| `adsconfig` | 1 | 改 `/luna/ads/config` 的 `reward_duration` |
| `incentcfg` | 1 | 改 `/luna/advert/incentive/config` 的 `advert_duration` |
| `retrieve` | **1** | 改 `/incentive/retrieve` 的 `launch_duration`（**倒计时真正来源**） |
| `alltime` | 1 | 递归扫描时长白名单字段，防服务端换路径 |
| `freq` | 1000 | 把 `freq_per_day` 抬到该值（0=不改） |
| `notify` | 1 | 命中发系统通知 |
| `snapshot` | 1 | 脚本一执行就发「已执行」通知 + `EXEC` 日志 |
| `probe` | 1 | request 阶段观测 done 上报值，只观测不改写 |
| `fake` | 0 | done 失败时本地伪成功（**仅 UI，无真实权益**） |
| `verbose` | 1 | 日志开关 |

| 变体 | 用途 |
|---|---|
| `soda-probe.plugin` | **零脚本链路探针，第一件事先跑这个** |
| `soda-sentinel.plugin` | 链路哨兵，判断脚本引擎/下载 |
| `variants/quiet.plugin` | 诊断通过后关掉通知轰炸 |
| `variants/d5.plugin` | 保守档 5 秒 |
| `variants/original.plugin` | 对照档（retrieve=0），用于 A/B |
| `variants/fake.plugin` | 只看 UI 流程 |
| `variants/replay.plugin` | 服务端硬校验 30s 时用；绑定 **http-request** 规则 |

其他改法：编辑 `soda/scripts/soda.js` 第一行 → 提交 → 各 `.plugin` 里 `?v=5` 递增（破缓存）→ Loon 删插件重加；或 `$persistentStore` 写 key `soda.cfg`，值形如 `duration=5&notify=0`，优先级最高。

---

## 6. 为什么改响应而不是改请求

抓包复盘的核心事实：

```
GET  /luna/advert/incentive/retrieve   →  ad_infos[].launch_duration = 30
POST /luna/advert/incentive/done      →  body {"launch_duration":30, ...}
                                          ↑ 回传给服务端的就是 30
21:51:54 retrieve → 21:51:56 fallback 签 token → 21:52:26 done（精确 +30.2s）
21:52:32 第二次 fallback → 21:53:02 第二次 done（精确 +30.3s）
```

时序是死的，标准本地倒计时，广告素材一次都没下载（走兜底分支）。v2 默认 `retrieve=0` 放过了真正控制倒计时的字段，v3 起已修正。

请求侧不可改：`x-ss-stub = md5(body)` 已实测一致；`x-gorgon`(20B) 含 body/时间，`x-helios`、`x-medusa`、`bd-ticket-guard-static-sign`(DER ECDSA-P256) 均为设备/签名绑定，重算不现实。`time_token` 是服务端密钥加密的 AEAD 密文（约 76 字符），只能原样透传。`conf.qishui.com/service/settings/v3/` 的 177KB 云控已排查，无独立 30 秒开关，故未纳入 MITM。

若服务端用自己下发的时长做时序校验，唯一补法是 `variants/replay.plugin`（截获 done → 本地秒成功 → 原样重放）。

---

## 7. 排错速查

| 现象 | 处理 |
|---|---|
| **订阅加了毫无反应（本轮根因）** | URL 必须是 `http://raw` 开头，或换 jsDelivr / 本地 zip |
| 探针 REJECT 生效但主订阅无日志 | 远程脚本下载失败 → 手机浏览器打开 `.../scripts/soda.js?v=5` 看是否返回 JS；换 jsdelivr 版 |
| 日志有 `EXEC` 没 `HIT` | URL 不在 5 条路由内，脚本会打印真实 URL |
| 通知一条没有但日志有 | iOS 通知权限 / Loon 通知设置，**以日志为准** |
| 插件规则显示 CRON | 版本选错，≤982 换 `-legacy` |
| `Script Type: CRON` / `$request undefined` | 手动运行属正常，脚本已安全跳过 |
| 多个订阅同时超时 | 抓包里 `adrules.top` / `yfamilys.com` / `kelee.one` 同样只有 request 无 response，属本机网络 / DNS / 隧道整体问题 |
| 短时狂刷后失效 | `freq_per_day` 只是**客户端**上限，服务端自己有统计会触发风控。别贪 |

---

## 8. 文件清单（仓库 `soda/` 下）

| 路径 | 说明 |
|---|---|
| `soda-noads.plugin` | **主订阅**，983+ 新语法，6 条规则（5 response + 1 request 观测） |
| `soda-noads-jsdelivr.plugin` | 新语法 + jsDelivr 通道（不受 `http://raw` 限制） |
| `soda-noads-httpraw.plugin` | 订阅与脚本 URL 均 `http://raw`，保守备选 |
| `soda-noads-legacy.plugin` | 旧语法，≤982 |
| `soda-noads.conf` | 「订阅脚本」入口别名 |
| **`soda-probe.plugin`** | **零脚本链路探针，2 条 REJECT 规则，测完删** |
| `soda-sentinel.plugin` | 链路哨兵（极宽匹配，只打日志不改包） |
| `scripts/soda.js` | 主脚本 v5：CRON 守卫、执行快照、命中通知、全字段扫描、request 观测 |
| `scripts/sentinel.js` | 哨兵脚本 |
| `scripts/soda-replay.js` | 方案 C 兜底脚本 |
| `variants/` | 参数变体 / 重放订阅 |
| `local/` | 离线版（相对 script-path），整目录打包 zip 直接导入 |
| `tools/build.py` | 从 `loon/` 源重新生成本目录内容 |

仅供个人设备调试与协议学习使用。
