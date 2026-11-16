var __SODA_ARGS__ = {"duration":1,"adsconfig":1,"incentcfg":1,"retrieve":1,"alltime":1,"freq":1000,"notify":1,"probe":1,"video":0,"fake":1,"verbose":1};
/**
 * 汽水音乐（luna / aid=8478）激励广告「跳过」Loon 脚本  v3
 * ---------------------------------------------------------------
 * v3 变更（针对「完全没效果」）：
 *   1) retrieve 默认开：done 请求体里回传 launch_duration:30，与 retrieve 下发值一致，
 *      说明倒计时读的是 retrieve，不是 ads/config。之前默认关 = 白改。
 *   2) 全字段递归扫描：任何层级里命中时长白名单的数字字段一律压到 duration，
 *      防止服务端换了字段路径/新增字段后漏改。
 *   3) 命中即系统通知（notify=1）：不用翻日志，通知栏直接看到脚本有没有跑、
 *      改了哪些字段、原始值多少。这是区分「脚本没跑」和「服务端不认」的关键。
 *   4) request 阶段观测（probe=1）：打印 done 请求体里 App 实际上报的 launch_duration，
 *      用来判定「我们改了响应，App 到底吃没吃」。只观测，绝不改写请求。
 *   5) done 成功/失败都通知，直接看服务端有没有发奖。
 *
 * 铁律：只改「响应」，绝不改「请求」。请求带 x-gorgon / x-helios / x-medusa /
 *       bd-ticket-guard 多重签名，动一个字节即失效。
 *
 * 参数（订阅 JS 头部注入 / 插件 argument / persistentStore key: soda.cfg）
 *   duration=1     目标倒计时秒数
 *   retrieve=1     改 retrieve 的 launch_duration（v3 默认开）
 *   adsconfig=1    改 /luna/ads/config
 *   incentcfg=1    改 /luna/advert/incentive/config
 *   alltime=1      递归扫描所有时长白名单字段
 *   freq=1000      抬升 freq_per_day（0=不改）
 *   notify=1       每条规则命中发系统通知
 *   probe=1        request 阶段观测 done 上报值
 *   video=0        替换广告素材 URL（videourl / videomd5）
 *   fake=0         done 失败时本地伪成功（仅 UI，无真实权益）
 *   verbose=1      打印日志
 */

(function () {
  var TAG = "[汽水]";
  var STORE_CFG = "soda.cfg";
  var STORE_HIT = "soda.hit";

  var hasReq = typeof $request !== "undefined" && !!$request;
  var hasResp = typeof $response !== "undefined" && !!$response &&
                typeof $response.body !== "undefined";

  // CRON / 手动运行：Loon 不注入 $request / $response，安全跳过
  if (!hasReq) {
    try { console.log(TAG + " 无 HTTP 上下文（CRON / 手动运行），本脚本由 HTTP 规则触发，已跳过"); } catch (e) {}
    try { if (typeof $done === "function") $done({}); } catch (e) {}
    return;
  }

  function readCfg() {
    var c = {
      duration: 1, adsconfig: 1, incentcfg: 1, retrieve: 1, alltime: 1,
      freq: 1000, notify: 1, probe: 1, video: 0, videourl: "", videomd5: "",
      fake: 0, verbose: 1
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

  /* 命中通知：一眼判定脚本有没有跑 */
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
    } catch (e) {}
  }

  function safeParse(body) {
    if (!body) return null;
    try { return JSON.parse(body); }
    catch (e) { log("JSON 解析失败: " + e); return null; }
  }
  function finish(obj) { $done({ body: JSON.stringify(obj) }); }
  function short(s, n) {
    s = String(s == null ? "" : s);
    return s.length > n ? s.slice(0, n) + "...(" + s.length + "B)" : s;
  }

  /* 全字段递归：任何层级的时长白名单数字字段压到 C.duration
   * 精确 key 匹配，绝不碰 expire_time / settings_time / *_type / timestamp */
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
    var j = safeParse($response.body);
    if (!j) { hit("ads/config", "响应非 JSON，透传 bodyLen=" + short($response.body, 0).length); return $done({}); }
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
    var j = safeParse($response.body);
    if (!j) { hit("incentive/config", "响应非 JSON，透传"); return $done({}); }
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
    var j = safeParse($response.body);
    if (!j) { hit("retrieve", "响应非 JSON，透传"); return $done({}); }
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
      var map2 = j.ad_infos_map || {};
      Object.keys(map2).forEach(function (bucket) {
        ((map2[bucket] && map2[bucket].ad_infos) || []).forEach(function (ad) {
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
    var j = safeParse($response.body);
    if (!j) { hit("done", "响应非 JSON"); return $done({}); }
    var code = j.status_code;
    var amount = 0;
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
      hit("done 失败", "code=" + code + " msg=" + msg + "（服务端拒绝了，需换 replay 方案）");
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

  /* ---------------- 5. fallback token（只观测 + 通知） ---------------- */
  function handleFallback() {
    var j = safeParse($response.body);
    if (!j) { hit("fallback", "响应非 JSON"); return $done({}); }
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

  /* ---------------- request 阶段：观测，不改写 ---------------- */
  function handleProbe(url) {
    if (!C.probe || !/\/luna\/advert\/incentive\/done(\?|$)/.test(url)) return $done({});
    var b = ($request && $request.body) || "";
    var ld = /"launch_duration"\s*:\s*(\d+)/.exec(b);
    var tk = /"time_token"\s*:\s*"([^"]{0,16})/.exec(b);
    hit("REQ-done 上报", "App 实际 launch_duration=" + (ld ? ld[1] : "?") +
        " token=" + (tk ? "有" : "无") + " bodyLen=" + b.length +
        (ld && ld[1] === String(C.duration) ? " | 改写已被 App 采用 ✓" : " | App 仍上报原值 ✗"));
    return $done({});   // 空对象 = 不修改请求，签名不受影响
  }

  /* ---------------- 路由 ---------------- */
  var url = ($request && $request.url) || "";
  if (!hasResp) return handleProbe(url);   // request 阶段

  if (/\/luna\/ads\/config(\?|$)/.test(url)) return handleAdsConfig();
  if (/\/luna\/advert\/incentive\/config(\?|$)/.test(url)) return handleIncentiveConfig();
  if (/\/luna\/advert\/incentive\/retrieve(\?|$)/.test(url)) return handleRetrieve();
  if (/\/luna\/advert\/incentive\/done(\?|$)/.test(url)) return handleDone();
  if (/\/luna\/advert\/fallback\/done\/info(\?|$)/.test(url)) return handleFallback();

  log("未匹配路由 " + (($request && $request.method) || "") + " " + url);
  $done({});
})();
