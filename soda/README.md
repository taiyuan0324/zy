# 汽水音乐 · 激励广告配置改写（Loon 订阅）· v3

仓库：`taiyuan0324/zy`，本目录 `soda/`。

只改写服务端**响应**里的倒计时字段，让 App 自己走完流程并发出**它自己签名**的领奖请求；请求体一个字节都不碰（请求带 `x-ss-stub`=md5(body)、`x-gorgon`、`x-helios`、`x-medusa`、`bd-ticket-guard` 多重签名，改了必被拒）。

---

## 0. v3 为什么改（针对「完全没效果」）

抓包复盘发现 v2 有个硬伤：

```
GET  /luna/advert/incentive/retrieve   →  ad_infos[].launch_duration = 30
POST /luna/advert/incentive/done      →  body {"launch_duration":30, ...}
                                        ↑ 回传给服务端的就是 30
```

**倒计时读的是 `retrieve.launch_duration`**，而 v2 默认 `retrieve=0` 根本没改它；改的 `ads/config.reward_duration` / `incentive/config.advert_duration` 对倒计时可能不起作用。

另外时序是死的，两次领奖都精确 30 秒：

```
21:51:54  retrieve（下发 30）
21:51:56  fallback/done/info（签发 time_token）
21:52:26  done（+30.2s） → amount=1800s
21:52:32  第二次 fallback
21:53:02  第二次 done（+30.3s）
```

v3 改动：

| 改动 | 作用 |
|---|---|
| `retrieve` 默认 **1** | 直改真正控制倒计时的字段 |
| `alltime=1` 递归扫描 | 任何层级命中时长白名单的数字字段一律压到 `duration`，防服务端换字段路径 |
| `notify=1` **命中即系统通知** | 不用翻日志，通知栏直接看出脚本跑没跑、改了哪些字段 |
| `probe=1` request 阶段观测 | 打印 done 请求里 App **实际上报**的 `launch_duration`，判定「改了响应 App 吃没吃」 |
| done 成功/失败都通知 | 直接看服务端有没有发奖 |

---

## 1. 先选对版本

Loon **3.5.1(983)** 起换了全新 Script 语法：旧写法 `http-response ... script-path=...` 换成 `response if ${url} ~= /.../ then script(...) with ...`。版本选错会出现脚本被挂成 `CRON`、类型识别异常。

| 你的 Loon | 订阅文件 |
|---|---|
| **3.5.1(983) 及以上**（含 3.5.3 / 1014） | `soda-noads.plugin` ← **主推** |
| 3.5.1(982) 及以下 | `soda-noads-legacy.plugin` |

**主地址**

```
https://raw.githubusercontent.com/taiyuan0324/zy/main/soda/soda-noads.plugin
```

Loon 手册对 GitHub 文件订阅要求以 `http://raw` 开头；若报格式错误改用：

```
http://raw.githubusercontent.com/taiyuan0324/zy/main/soda/soda-noads.plugin
```

| 备用地址 | URL |
|---|---|
| jsDelivr | `https://cdn.jsdelivr.net/gh/taiyuan0324/zy@main/soda/soda-noads-jsdelivr.plugin` |
| 旧语法（≤982） | `https://raw.githubusercontent.com/taiyuan0324/zy/main/soda/soda-noads-legacy.plugin` |
| 订阅脚本入口 | `https://raw.githubusercontent.com/taiyuan0324/zy/main/soda/soda-noads.conf` |

> **换版务必删除旧插件再重新添加**，别只刷新。残留旧规则会和新规则抢匹配（新版 Response Script 只选第一条命中）。

---

## 2. 三步判定（v3 核心，看通知栏就够）

导入主订阅 → 打开汽水音乐 → 触发一次「看广告领 VIP」，看系统通知：

| 通知栏现象 | 结论 | 下一步 |
|---|---|---|
| **一条通知都没有** | 脚本压根没跑 → MITM / CA / 订阅加载 / 规则被抢 | 见第 4 节排查表 |
| 有 `汽水·ads/config`、`汽水·retrieve` 等通知，且写了 `30->1` | 改写生效了 | 看最后两条通知 |
| `汽水·REQ-done 上报` 显示 `launch_duration=1 ✓` | App 吃了改写 | 等 `done` 通知 |
| `汽水·REQ-done 上报` 显示 `launch_duration=30 ✗` | App 不用这个字段，另有硬编码 | 换 `variants/replay.plugin` |
| `汽水·done 成功` + `amount=1800s` | **成了** | — |
| `汽水·done 失败` + `code≠0` | 服务端按自己时钟校验了 30 秒 | 换 `variants/replay.plugin` |
| 倒计时仍 30 秒，但通知显示全改到 1 了 | 客户端另有本地计时/云控通道 | 抓一份**开着插件**的新包给我 |

通知里的「第 N 次命中」是持久计数，可用来确认规则被反复触发。

---

## 3. 导入步骤

1. Loon → 配置 → 插件 → `+` → **添加插件 URL** → 粘贴主地址
2. 打开插件开关（会提示添加 MITM 域名，确认）
3. 确认 MITM 含 `api.qishui.com`、`beta-luna.douyin.com`；iOS 需**安装并信任 CA 证书**（设置 → 通用 → 关于本机 → 证书信任设置）
4. 按第 2 节用真实请求验证

**不要**用「脚本 → 运行」判断生效：那是 CRON / Generic 上下文，Loon 不注入 `$request` / `$response`。脚本已加守卫，此时只打印一行提示并安全退出（历史上的 `ReferenceError: Can't find variable: $request` 就是这个原因，不是订阅失败）。

---

## 4. 参数与变体

默认参数固化在 `scripts/soda.js` 第一行 `var __SODA_ARGS__ = {...}`：

| 参数 | 默认 | 说明 |
|---|---|---|
| `duration` | 1 | 目标倒计时秒数 |
| `adsconfig` | 1 | 改 `/luna/ads/config` 的 `reward_duration` |
| `incentcfg` | 1 | 改 `/luna/advert/incentive/config` 的 `advert_duration` |
| `retrieve` | **1** | 改 `/incentive/retrieve` 的 `launch_duration`（v3 默认开） |
| `alltime` | 1 | 递归扫描时长白名单字段 |
| `freq` | 1000 | 把 `freq_per_day` 抬到该值（0=不改） |
| `notify` | 1 | 命中发系统通知（诊断完可关） |
| `probe` | 1 | request 阶段观测 done 上报值，**只观测不改写** |
| `video` | 0 | 替换广告素材 URL（需 `videourl` + `videomd5`） |
| `fake` | 0 | done 失败时本地伪成功（**仅 UI，无真实权益**） |
| `verbose` | 1 | 日志开关 |

| 变体 | 订阅 URL | 用途 |
|---|---|---|
| `quiet` | `.../soda/variants/quiet.plugin` | 诊断通过后关掉通知轰炸 |
| `d5` | `.../soda/variants/d5.plugin` | 保守档 5 秒，降低服务端时钟校验风险 |
| `original` | `.../soda/variants/original.plugin` | 对照档：恢复 v2 行为（retrieve=0），用于 A/B |
| `fake` | `.../soda/variants/fake.plugin` | 只看 UI 流程 |
| **方案 C 重放** | `.../soda/variants/replay.plugin` | 服务端硬校验 30s 时用；绑定 **http-request** 规则 |

（前缀均为 `https://raw.githubusercontent.com/taiyuan0324/zy/main/soda/`）

其他改法：

- 编辑 `soda/scripts/soda.js` 第一行 → 提交 → 各 `.plugin` 里 `?v=3` 递增（破缓存）→ Loon 刷新订阅
- `$persistentStore` 写 key `soda.cfg`，值形如 `duration=5&notify=0`，优先级最高

---

## 5. 缓存与更新

| 项 | 说明 |
|---|---|
| GitHub raw | 约 5 分钟缓存；script-path 后 `?v=3` 递增即可破 |
| jsDelivr `@main` | 约 12 小时；可用 commit sha |
| Loon 侧 | 订阅请求带 `If-None-Match`；改文件后 ETag 会变，必要时删插件重加 |

改完在 Loon 里**刷新订阅 + 重启插件**。

---

## 6. 排错

| 现象 | 处理 |
|---|---|
| 一条通知都没有 | ① CA 未信任 ② MITM 域名没加 ③ App 走 QUIC/HTTP3，关该 App 的 UDP 或强制 HTTPS 解密 ④ 别的插件有更早的 Response Script 抢匹配，先只留这一个插件 ⑤ 订阅没加载成功 |
| 插件里规则显示为 CRON | 版本选错，换 `-legacy`（≤982）或确认主订阅是新语法 |
| 订阅报格式错误 | 按第 1 节把 `https://raw` 换成 `http://raw` |
| 订阅成功但脚本下载超时 | 手机浏览器打开 plugin 里 `script-path` URL，确认返回 JS 文本 |
| `Script Type: CRON` / `$request undefined` | 手动运行属正常现象，脚本已安全跳过；用真实请求验证 |
| 倒计时仍 30 秒 | 看 `REQ-done 上报` 通知：值为 1 → 客户端另有时钟；值为 30 → 改写没被采用 |
| `status_code≠0` | 服务端按自己时钟校验 30 秒，改走 `variants/replay.plugin` |
| 多个订阅同时超时 | 抓包里 `adrules.top` / `yfamilys.com` / `kelee.one` 等请求同样只有 request 无 response，属本机网络 / DNS / 隧道整体问题 |
| 短时狂刷后失效 | `freq_per_day` 只是**客户端**上限，服务端自己有统计会触发风控。别贪 |

---

## 7. 校验面提醒

- 请求侧不可改：`x-ss-stub = md5(body)` 已实测一致；`x-gorgon`(20B) 含 body/时间，`x-helios`、`x-medusa`、`bd-ticket-guard-static-sign`(DER ECDSA-P256) 均为设备/签名绑定，重算不现实
- `time_token` 是服务端密钥加密的 AEAD 密文（约 76 字符），客户端无法伪造，只能原样透传
- `conf.qishui.com/service/settings/v3/` 有 177KB 云控配置，已排查过，未发现独立的 30 秒激励时长开关（只有 `reward_count_down_preload_second=-1` 等预加载项），故未纳入 MITM
- 因此本方案**只改响应**；若服务端用自己下发的时长做时序校验，唯一补法是重放
- 仅供个人设备调试与协议学习使用

---

## 8. 文件清单（仓库 `soda/` 下）

| 路径 | 说明 |
|---|---|
| `soda-noads.plugin` | **主订阅**，Loon 983+ 新语法，6 条规则（5 response + 1 request 观测） |
| `soda-noads-jsdelivr.plugin` | 新语法 + jsDelivr 通道 |
| `soda-noads-legacy.plugin` | 旧语法，Loon ≤982 |
| `soda-noads.conf` | 「订阅脚本」入口别名 |
| `scripts/soda.js` | 主脚本 v3，含 CRON 守卫、命中通知、全字段扫描、request 观测 |
| `scripts/soda-replay.js` | 方案 C 兜底脚本 |
| `variants/*.plugin` + `variants/soda-*.js` | 参数变体 / 重放订阅 |
| `local/` | 离线版（相对 script-path），整目录打包 zip 可直接导入 |
| `tools/build.py` | 从 `loon/` 源重新生成本目录内容 |
