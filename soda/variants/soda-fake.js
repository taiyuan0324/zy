var __SODA_ARGS__ = {"duration":1,"adsconfig":1,"incentcfg":1,"retrieve":1,"alltime":1,"freq":1000,"notify":1,"snapshot":1,"probe":1,"video":0,"fake":1,"verbose":1};
/**
 * 汽水音乐（luna / aid=8478）激励广告「跳过」Loon 脚本  v4
 * ---------------------------------------------------------------
 * v4 变更（针对「通知栏没反应」）：
 *   1) 修阶段判断：v3 要求 $response.body !== undefined 才算响应阶段，
 *      一旦 Loon 没给 body，所有响应都被当成 request 静默透传 → 零改写零通知。
 *      现在只要 $response 对象存在就是响应阶段；body 缺失也能发命中通知。
 *   2) snapshot=1：脚本「一旦被执行」就先发一条通知 + 日志，把阶段 / URL /
 *      respBody 长度 / reqBody 长度打出来。用来区分「规则没匹配」和「逻辑没生效」。
 *   3) 通知失败降级：try 吞掉后改为写日志，不再静默；提示去 Loon 日志看 HIT/EXEC 行
 *      （iOS 通知权限 / Loon 通知设置可能吞掉通知，不能只靠通知栏判断）。
 *   4) 未命中路由也发通知：若服务端换了域名/路径，能直接从通知里看到真实 URL。
 *
 * 核心逻辑（v3 保留）：
 *   - retrieve 默认开：done 请求体回传 launch_duration:30 = retrieve 下发值，
 *     倒计时读的是 retrieve，不是 ads/config。
 *   - alltime=1 递归扫描时长白名单字段，防服务端换字段路径。
 *   - probe=1 request 阶段观测 done 上报值，只观测不改写。
 *
 * 铁律：只改响应，绝不改请求。请求带 x-gorgon / x-helios / x-medusa /
 *       bd-ticket-guard / x-ss-stub 多重签名，动一个字节即失效。
 */

(function () {
  var TAG = "[汽水]";
  var STORE_CFG = "soda.cfg";
  var STORE_HIT = "soda.hit";

  var hasReq = typeof $request !== "undefined" && !!$request;
  var hasResp = typeof $response !== "undefined" && !!$response;

  // CRON / 手动运行：不注入 $request / $response，安全跳过
  if (!hasReq) {
    try { console.log(TAG + " 无 HTTP 上下文（CRON / 手动运行），本脚本由 HTTP 规则触发，已跳过"); } catch (e) {}
    try { if (typeof $done === "function") $done({}); } catch (e) {}
    return;
  }

  var url = ($request && $request.url) || "";

  function readCfg() {
    var c = {
      duration: 1, adsconfig: 1, incentcfg: 1, retrieve: 1, alltime: 1,
      freq: 1000, notify: 1, snapshot: 1, probe: 1, video: 0,
      videourl: "", videomd5: "", fake: 0, verbose: 1
    };
    function set(k, v) {
      if (!(k in c)) return;
      if (typeof v === "boolean") v = v ? 1 : 0;
      if (typeof c[k] === "number") {
        var n = parseInt(v, 10);
        if (!isNaN(n)) c[k] = n;
      } else c[k] = String(v);
    }
    function applyKV(s) {
      if (!s) return;
      String(s).split("&").forEach(function (kv) {
        var i = kv.indexOf("=");
        if (i < 0) return;
        set(kv.slice(0, i).trim(), kv.slice(i + 1).trim());
      });
    }
    function applyObj(o) {
      if (!o || typeof o !== "object") return;
      Object.keys(o).forEach(function (k) { set(k, o[k]); });
    }
    try { if (typeof __SODA_ARGS__ !== "undefined" && __SODA_ARGS__) applyObj(__SODA_ARGS__); } catch (e) {}
    try {
      if (typeof $argument === "string") applyKV($argument);
      else if ($argument && typeof $argument === "object") applyObj($argument);
    } catch (e) {}
    try { applyKV($persistentStore.read(STORE_CFG)); } catch (e) {}
    return c;
  }

  var C = readCfg();

  function log(s) {
    if (C.verbose) { try { console.log(TAG + " " + s); } catch (e) {} }
  }

  /* 命中留痕：通知 + 日志 + 持久计数。
   * 通知可能被 iOS 权限吞掉，所以日志一定打，catch 里明确提示去看日志。 */
  function hit(route, detail) {
    log("HIT " + route + " | " + detail);
    var n = 0;
    try {
      var raw = $persistentStore.read(STORE_HIT);
      n = raw ? (parseInt(raw, 10) || 0) : 0;
      $persistentStore.write(String(n + 1), STORE_HIT);
    } catch (e) {}
    if (!C.notify) return;
    try {
      $notification.post("汽水·" + route, "第 " + (n + 1) + " 次命中", String(detail).slice(0, 140));
    } catch (e) {
      log("通知发送失败（iOS 通知权限 / Loon 通知设置）：" + e + " → 请看 Loon 日志里的 HIT 行");
    }
  }

  /* 执行快照：只要 Loon 真的跑了这个脚本，必然留下这一行 */
  function snapshot() {
    var stage = hasResp ? "RESP" : "REQ";
    var rb = -1, qb = -1;
    try { rb = (hasResp && $response.body != null) ? String($response.body).length : -1; } catch (e) { rb = -2; }
    try { qb = ($request && $request.body != null) ? String($request.body).length : -1; } catch (e) { qb = -2; }
    var info = stage + " respBody=" + rb + "B reqBody=" + qb + "B url=" + short(url, 110);
    log("EXEC " + info);
    if (C.snapshot) hit("脚本已执行", info);
  }

  function safeParse(body) {
    if (!body) return null;
    try { return JSON.parse(body); }
    catch (e) { log("JSON 解析失败: " + e + " bodyHead=" + short(body, 60)); return null; }
  }
  function finish(obj) { $done({ body: JSON.stringify(obj) }); }
  function short(s, n) {
    s = String(s == null ? "" : s);
    return s.length > n ? s.slice(0, n) + "...(" + s.length + "B)" : s;
  }

  /* 递归时长扫描：精确 key 白名单，不碰 expire_time / *_type / 时间戳 */
  var DUR_KEYS = /^(duration|reward_duration|advert_duration|launch_duration|ad_duration|video_duration|play_duration|show_duration|min_duration|max_duration|watch_duration|watch_time|reward_time|need_watch_time|countdown|countdown_sec|reward_countdown|play_time|ad_show_time)$/i;
  function scanDurations(o, path, changed) {
    if (!o || typeof o !== "object") return;
    if (Object.prototype.toString.call(o) === "[object Array]") {
      o.forEach(function (v, i) { scanDurations(v, path + "[" + i + "]", changed); });
      return;
    }
    Object.keys(o).forEach(function (k) {
      var v = o[k], np = path ? path + "." + k : k;
      if (v && typeof v === "object") { scanDurations(v, np, changed); return; }
      if (DUR_KEYS.test(k) && typeof v === "number" && v !== C.duration) {
        changed.push(np + " " + v + "->" + C.duration);
        o[k] = C.duration;
      }
    });
  }

  /* ---------------- 1. /luna/ads/config ---------------- */
  function handleAdsConfig() {
    var j = safeParse($response && $response.body);
    if (!j) {
      hit("ads/config", "响应无 body / 非 JSON（respBody=" +
          ((($response && $response.body) != null) ? String($response.body).length : -1) +
          "B，可能是 gzip 或 requires_body 未生效）");
      return $done({});
    }
    var changed = [];
    if (C.adsconfig) {
      if (j.feed_ads_config && typeof j.feed_ads_config.reward_duration === "number") {
        var old = j.feed_ads_config.reward_duration;
        j.feed_ads_config.reward_duration = C.duration;
        changed.push("feed_ads_config.reward_duration " + old + "->" + C.duration);
      }
      if (C.freq > 0 && j.ad_unit_configs && j.ad_unit_configs.length) {
        j.ad_unit_configs.forEach(function (u, idx) {
          var isRewarded = u.ad_supported_scene && u.ad_supported_scene.rewarded_scene_detail;
          if (isRewarded && typeof u.freq_per_day === "number" && u.freq_per_day < C.freq) {
            changed.push("ad_unit_configs[" + idx + "].freq_per_day " + u.freq_per_day + "->" + C.freq);
            u.freq_per_day = C.freq;
          }
        });
      }
    }
    if (C.alltime) scanDurations(j, "", changed);
    log("ads/config 改写: " + (changed.length ? changed.join(" | ") : "无匹配字段"));
    hit("ads/config", changed.length ? changed.join(" | ").slice(0, 140) : "无匹配字段（检查字段名是否变更）");
    return finish(j);
  }

  /* ---------------- 2. /luna/advert/incentive/config ---------------- */
  function handleIncentiveConfig() {
    var j = safeParse($response && $response.body);
    if (!j) { hit("incentive/config", "响应无 body / 非 JSON"); return $done({}); }
    var changed = [];
    if (C.incentcfg && j.feed_advert_config && typeof j.feed_advert_config.advert_duration === "number") {
      var old = j.feed_advert_config.advert_duration;
      j.feed_advert_config.advert_duration = C.duration;
      changed.push("feed_advert_config.advert_duration " + old + "->" + C.duration);
    }
    if (C.alltime) scanDurations(j, "", changed);
    log("incentive/config 改写: " + (changed.length ? changed.join(" | ") : "无匹配字段"));
    hit("incentive/config", changed.length ? changed.join(" | ").slice(0, 140) : "无匹配字段");
    return finish(j);
  }

  /* ---------------- 3. /luna/advert/incentive/retrieve ---------------- */
  function handleRetrieve() {
    var j = safeParse($response && $response.body);
    if (!j) { hit("retrieve", "响应无 body / 非 JSON"); return $done({}); }
    var changed = [], cnt = 0;
    if (C.retrieve) {
      var map = j.ad_infos_map || {};
      Object.keys(map).forEach(function (bucket) {
        var list = (map[bucket] && map[bucket].ad_infos) || [];
        list.forEach(function (ad) {
          if (typeof ad.launch_duration === "number") {
            if (ad.launch_duration !== C.duration) changed.push(bucket + ".launch_duration " + ad.launch_duration + "->" + C.duration);
            ad.launch_duration = C.duration; cnt++;
          }
        });
      });
    }
    if (C.video && C.videourl) {
      Object.keys(j.ad_infos_map || {}).forEach(function (bucket) {
        ((j.ad_infos_map[bucket] && j.ad_infos_map[bucket].ad_infos) || []).forEach(function (ad) {
          ((ad.creative_info && ad.creative_info.video_list) || []).forEach(function (v) {
            v.url = C.videourl;
            if (C.videomd5) v.md5_check = C.videomd5;
          });
        });
      });
      changed.push("素材URL已替换");
    }
    if (C.alltime) scanDurations(j, "", changed);
    log("retrieve 改写: launch_duration 命中 " + cnt + " 条");
    hit("retrieve", "launch_duration 命中 " + cnt + " 条" + (changed.length ? " | " + changed[0] : "") + (cnt === 0 ? " | 响应结构可能已变" : ""));
    return finish(j);
  }

  /* ---------------- 4. /luna/advert/incentive/done ---------------- */
  function handleDone() {
    var j = safeParse($response && $response.body);
    if (!j) { hit("done", "响应无 body / 非 JSON"); return $done({}); }
    var code = j.status_code, amount = 0;
    try {
      var rd = j.reward_details || {}, keys = Object.keys(rd);
      if (keys.length) amount = rd[keys[0]].amount || 0;
    } catch (e) {}
    var msg = (j.status_info && j.status_info.status_msg) || "";
    if (code === 0) {
      log("done 成功: amount=" + amount + "s (" + Math.round(amount / 60) + " 分钟)");
      hit("done 成功", "amount=" + amount + "s / " + Math.round(amount / 60) + "分钟");
      try {
        var day = new Date().toISOString().slice(0, 10);
        var stat = $persistentStore.read("soda.stat") || "";
        var rec = day + "|" + amount + "|" + Date.now();
        $persistentStore.write(stat ? stat + ";" + rec : rec, "soda.stat");
      } catch (e) {}
    } else {
      log("done 失败: code=" + code + " msg=" + msg);
      hit("done 失败", "code=" + code + " msg=" + msg + "（服务端拒绝，需换 replay 方案）");
      if (C.fake) {
        var fakeBody = {
          reward_details: { "0": { reward_type: 0, amount: 1800, expire_time: Math.floor(Date.now() / 1000) + 1800, claim_status: 1 } },
          status_code: 0,
          status_info: { now: Math.floor(Date.now() / 1000), status_msg: "success", log_id: "local-fake" }
        };
        log("done 已伪造成成功（仅本地显示，无真实权益）");
        return $done({ body: JSON.stringify(fakeBody) });
      }
    }
    return $done({});
  }

  /* ---------------- 5. fallback token ---------------- */
  function handleFallback() {
    var j = safeParse($response && $response.body);
    if (!j) { hit("fallback", "响应无 body / 非 JSON"); return $done({}); }
    var detail = "status_code=" + j.status_code;
    if (j.post_done_extra) {
      try {
        var extra = JSON.parse(j.post_done_extra);
        detail += " req_id=" + String(extra.req_id || "").slice(0, 24) +
                  " tokenLen=" + String(extra.time_token || "").length;
        $persistentStore.write(j.post_done_extra, "soda.lastExtra");
      } catch (e) {}
    }
    hit("fallback token", detail + "（MITM 解密已通）");
    return $done({});
  }

  /* ---------------- request 阶段：只观测 ---------------- */
  function handleProbe(u) {
    if (!C.probe || !/\/luna\/advert\/incentive\/done(\?|$)/.test(u)) return $done({});
    var b = ($request && $request.body) || "";
    var ld = /"launch_duration"\s*:\s*(\d+)/.exec(b);
    var tk = /"time_token"\s*:\s*"([^"]{0,16})/.exec(b);
    hit("REQ-done 上报", "App 实际 launch_duration=" + (ld ? ld[1] : "?") +
        " token=" + (tk ? "有" : "无") + " bodyLen=" + b.length +
        (ld && ld[1] === String(C.duration) ? " | 改写已被采用 ✓" : " | App 仍上报原值 ✗"));
    return $done({});
  }

  /* ---------------- 路由 ---------------- */
  snapshot();
  if (!hasResp) return handleProbe(url);

  if (/\/luna\/ads\/config(\?|$)/.test(url)) return handleAdsConfig();
  if (/\/luna\/advert\/incentive\/config(\?|$)/.test(url)) return handleIncentiveConfig();
  if (/\/luna\/advert\/incentive\/retrieve(\?|$)/.test(url)) return handleRetrieve();
  if (/\/luna\/advert\/incentive\/done(\?|$)/.test(url)) return handleDone();
  if (/\/luna\/advert\/fallback\/done\/info(\?|$)/.test(url)) return handleFallback();

  // 规则命中了但 URL 不在预期内 → 服务端可能换了域名/路径，直接报出真实 URL
  hit("未匹配路由", (($request && $request.method) || "") + " " + short(url, 130));
  $done({});
})();
