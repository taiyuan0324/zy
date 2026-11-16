# 汽水音乐 · 激励广告配置改写（Loon 订阅）

仓库：`taiyuan0324/zy`，本目录 `soda/`。不覆盖仓库根目录已有的 `qishui_vip.plugin` / `qishui_vip.js`（那两个只清开屏与信息流广告，不碰激励时长，可与本插件同时开）。

GitHub 静态托管的 Loon 插件订阅。不含代理节点、不含规则分流，只有 `[Script]` + `[MITM]` 两个基础模块，**全版本 Loon 可用**（不依赖 Build 733+ 的 `[Argument]`）。

原理：只改写服务端**响应**里的倒计时字段，让 App 自己走完流程并发出**它自己签名**的领奖请求；请求体一个字节都不碰（请求带 `x-ss-stub`=md5(body)、`x-gorgon`、`x-helios`、`x-medusa`、`bd-ticket-guard` 多重签名，改了必被拒）。

---

## 1. 订阅地址

**主地址（GitHub raw）**

```
https://raw.githubusercontent.com/taiyuan0324/zy/main/soda/soda-noads.plugin
```

Loon 官方手册对 GitHub 文件的订阅地址有个格式要求：**必须以 `http://raw` 开头**。若上面这条报格式错误，改用：

```
http://raw.githubusercontent.com/taiyuan0324/zy/main/soda/soda-noads.plugin
```

备用通道（jsDelivr，仅作冗余）：

```
https://cdn.jsdelivr.net/gh/taiyuan0324/zy@main/soda/soda-noads-jsdelivr.plugin
```

「订阅脚本」入口（不是「插件」入口）用 `https://raw.githubusercontent.com/taiyuan0324/zy/main/soda/soda-noads.conf`，内容与主 plugin 一致。

---

## 2. 导入步骤

1. Loon → 配置 → 插件 → `+` → **添加插件 URL** → 粘贴订阅地址
2. 打开插件开关（会提示添加 MITM 域名，确认）
3. 确认 MITM 含 `api.qishui.com`、`beta-luna.douyin.com`；iOS 需安装并**信任** CA 证书（设置 → 通用 → 关于本机 → 证书信任设置）
4. 打开汽水音乐，触发一次「看广告领 VIP」，观察是否 1 秒左右结束
5. Loon → 脚本 → 日志，看 `[汽水]` 前缀输出

---

## 3. 参数与变体

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

**换参数最省事的办法：换订阅 URL**

| 变体 | 订阅 URL | 用途 |
|---|---|---|
| `retrieve` | `https://raw.githubusercontent.com/taiyuan0324/zy/main/soda/variants/retrieve.plugin` | 改完仍等 30 秒时用这档 |
| `d5` | `https://raw.githubusercontent.com/taiyuan0324/zy/main/soda/variants/d5.plugin` | 保守档，5 秒，降低服务端时钟校验风险 |
| `fake` | `https://raw.githubusercontent.com/taiyuan0324/zy/main/soda/variants/fake.plugin` | 只看 UI 流程，调试用 |

其他改法：

- **直接编辑 GitHub 上的 `soda/scripts/soda.js` 第一行** → 提交 → 把各 `.plugin` 里 script-path 的 `?v=1` 改成 `?v=2`（破缓存）→ Loon 刷新订阅
- **Loon 插件 `[Argument]`**（Build 733+）：脚本对 `$argument` 的 String / Object 两种形态都做了兼容
- **`$persistentStore`**：写 key `soda.cfg`，值形如 `duration=5&verbose=1`，优先级最高

---

## 4. 缓存与更新

| 通道 | 缓存 | 破缓存 |
|---|---|---|
| GitHub raw | 约 5 分钟 | script-path 后加 `?t=<时间戳>` 或把 `?v=N` 递增 |
| jsDelivr `@main` | 约 12 小时 | 改用 commit sha：`...@<40位sha>/soda/scripts/soda.js` |

改完记得在 Loon 里**刷新订阅 + 重启插件**，否则还是旧脚本。

---

## 5. 排错

| 现象 | 处理 |
|---|---|
| 订阅加载失败 / 报格式错误 | 按第 1 节把 `https://raw` 换成 `http://raw` 开头 |
| 订阅成功但脚本下载超时 | 手机浏览器打开 plugin 里那条 `script-path` URL，确认能返回 JS 文本 |
| 完全无 `[汽水]` 日志 | MITM 没生效：CA 未信任 / 域名未加 / App 走了 QUIC(HTTP/3)，Loon 里关掉该 App 的 UDP 或开「强制 HTTPS 解密」 |
| 还是等 30 秒 | 换 `variants/retrieve.plugin`；再看日志里哪个字段没被改到 |
| `status_code≠0` | 服务端按自己时钟校验了 30 秒，改配置这条路走不通，改走 `scripts/soda-replay.js`（先本地秒成功、30 秒后原样重放真实 done） |
| 短时狂刷后失效 | `freq_per_day` 只是**客户端**上限，服务端自己有统计，会触发风控。别贪 |

---

## 6. 校验面提醒

- 请求侧不可改：`x-ss-stub = md5(body)` 已实测一致；`x-gorgon`(20B) 含 body/时间，`x-helios`、`x-medusa`、`bd-ticket-guard-static-sign`(DER ECDSA-P256) 均为设备/签名绑定，重算不现实
- `time_token` 是服务端密钥加密的 AEAD 密文（约 76 字符），客户端无法伪造，只能原样透传
- 因此本方案**只改响应**；若服务端用自己下发的时长做时序校验，唯一补法是重放（见上）
- 仅供个人设备调试与协议学习使用

---

## 7. 文件清单（均位于仓库 `soda/` 下）

| 路径 | 说明 |
|---|---|
| `soda-noads.plugin` | 主订阅（GitHub raw 绝对 script-path） |
| `soda-noads-jsdelivr.plugin` | 备用通道（jsDelivr 绝对 script-path） |
| `soda-noads.conf` | 「订阅脚本」入口别名 |
| `scripts/soda.js` | 主脚本，5 条路由统一分发 |
| `scripts/soda-replay.js` | 方案 C 兜底：截获 done → 本地秒成功 → 原样重放 |
| `variants/*.plugin` + `variants/soda-*.js` | 参数变体 |
| `local/` | 离线版（相对 `script-path`），整目录打包成 zip 可直接导入 Loon |
| `tools/build.py` | 从 `loon/` 源重新生成本目录内容 |
