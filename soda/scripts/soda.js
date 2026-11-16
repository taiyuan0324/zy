var __SODA_ARGS__ = {"duration":1,"adsconfig":1,"incentcfg":1,"retrieve":0,"freq":1000,"video":0,"fake":0,"verbose":1};
/**
 * 汽水音乐（luna / aid=8478）激励广告「跳过」Loon 脚本
 * ---------------------------------------------------------------
 * 设计原则：只改写服务端「响应」，绝不改写「请求」。
 * 原因：请求带 x-gorgon / x-helios / x-medusa / bd-ticket-guard 多重签名，
 *       body 或 query 一变签名即失效（服务端 400/拒绝发奖）。
 *       响应体是服务端产物，客户端不做签名校验，改它最安全。
 *
 * 覆盖 4 个接口：
 *   1) POST api.qishui.com/luna/ads/config              -> feed_ads_config.reward_duration / 频次
 *   2) GET  beta-luna.douyin.com/luna/advert/incentive/config -> feed_advert_config.advert_duration
 *   3) GET  beta-luna.douyin.com/luna/advert/incentive/retrieve -> ad_infos[].launch_duration (+素材可选替换)
 *   4) POST api.qishui.com/luna/advert/incentive/done   -> 只记录奖励，不篡改（可选假成功开关）
 *
 * 参数（Loon 插件 argument 或 persistentStore key: soda.cfg）
 *   duration=1        目标倒计时秒数
 *   adsconfig=1       改写 /luna/ads/config
 *   incentcfg=1       改写 /luna/advert/incentive/config
 *   retrieve=0        改写 /luna/advert/incentive/retrieve 的 launch_duration（激进，默认关）
 *   freq=1000         把 freq_per_day 抬到该值（0=不改）
 *   video=0           是否替换广告素材 URL
 *   videourl=         1 秒素材地址（video=1 时必填）
 *   videomd5=         该素材 md5（客户端会校验 md5_check）
 *   fake=0            是否把 done 的失败响应改成成功（仅 UI，无真实权益）
 *   verbose=1         打印日志
 */

(function () {
  var TAG = "[汽水]";
  var STORE_CFG = "soda.cfg";

  function log(s) {
    if (C.verbose) console.log(TAG + " " + s);
  }

  /* ---------------- 配置 ----------------
   * 优先级：脚本内置 CFG < 订阅服务器注入(__SODA_ARGS__) < 插件 $argument < persistentStore
   * $argument 在 Loon 新版是 Object、旧版/其他工具是 String，这里两种都吃。
   */
  function readCfg() {
    var c = {
      duration: 1,
      adsconfig: 1,
      incentcfg: 1,
      retrieve: 0,
      freq: 1000,
      video: 0,
      videourl: "",
      videomd5: "",
      fake: 0,
      verbose: 1
    };

    function set(k, v) {
      if (!(k in c)) return;
      if (typeof v === "boolean") v = v ? 1 : 0;
      if (typeof c[k] === "number") {
        var n = parseInt(v, 10);
        if (!isNaN(n)) c[k] = n;
      } else {
        c[k] = String(v);
      }
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
      Object.keys(o).forEach(function (k) {
        set(k, o[k]);
      });
    }

    // 1) 订阅服务器在 JS 头部注入的参数（URL query 转发而来）
    try {
      if (typeof __SODA_ARGS__ !== "undefined" && __SODA_ARGS__) {
        applyObj(__SODA_ARGS__);
      }
    } catch (e) {}

    // 2) Loon 插件参数：Object（新版 [Argument]）/ String（旧版）
    try {
      if (typeof $argument === "string") applyKV($argument);
      else if ($argument && typeof $argument === "object") applyObj($argument);
    } catch (e) {}

    // 3) persistentStore key "soda.cfg"，最终覆盖
    try {
      applyKV($persistentStore.read(STORE_CFG));
    } catch (e) {}

    return c;
  }

  var C = readCfg();

  /* ---------------- 工具 ---------------- */
  function safeParse(body) {
    if (!body) return null;
    try {
      return JSON.parse(body);
    } catch (e) {
      log("JSON 解析失败: " + e);
      return null;
    }
  }

  function finish(obj) {
    $done({ body: JSON.stringify(obj) });
  }

  function short(s, n) {
    s = String(s == null ? "" : s);
    return s.length > n ? s.slice(0, n) + "...(" + s.length + "B)" : s;
  }

  /* ---------------- 1. /luna/ads/config ---------------- */
  function handleAdsConfig(url) {
    var j = safeParse($response.body);
    if (!j) return $done({});

    var changed = [];

    if (j.feed_ads_config && typeof j.feed_ads_config.reward_duration === "number") {
      var old = j.feed_ads_config.reward_duration;
      j.feed_ads_config.reward_duration = C.duration;
      changed.push("feed_ads_config.reward_duration " + old + "->" + C.duration);
    }

    if (C.freq > 0 && j.ad_unit_configs && j.ad_unit_configs.length) {
      j.ad_unit_configs.forEach(function (u, idx) {
        // 只抬升「激励视频」档位（带 rewarded_scene_detail 的那一组），别乱改开屏
        var isRewarded =
          u.ad_supported_scene &&
          u.ad_supported_scene.rewarded_scene_detail;
        if (isRewarded && typeof u.freq_per_day === "number" && u.freq_per_day < C.freq) {
          changed.push("ad_unit_configs[" + idx + "].freq_per_day " + u.freq_per_day + "->" + C.freq);
          u.freq_per_day = C.freq;
        }
      });
    }

    log("ads/config 改写: " + (changed.length ? changed.join(" | ") : "无匹配字段"));
    if (C.verbose) log("ads/config 原始片段: " + short($response.body, 400));
    return finish(j);
  }

  /* ---------------- 2. /luna/advert/incentive/config ---------------- */
  function handleIncentiveConfig(url) {
    var j = safeParse($response.body);
    if (!j) return $done({});

    var changed = [];
    if (j.feed_advert_config && typeof j.feed_advert_config.advert_duration === "number") {
      var old = j.feed_advert_config.advert_duration;
      j.feed_advert_config.advert_duration = C.duration;
      changed.push("feed_advert_config.advert_duration " + old + "->" + C.duration);
    }
    // 广告源列表：保留自建源(type=3)与兜底源(type=5)，清空会导致无广告可选
    if (C.verbose && j.advert_sources) {
      changed.push("advert_sources=" + JSON.stringify(j.advert_sources));
    }
    log("incentive/config 改写: " + (changed.length ? changed.join(" | ") : "无匹配字段"));
    return finish(j);
  }

  /* ---------------- 3. /luna/advert/incentive/retrieve ---------------- */
  function handleRetrieve(url) {
    var j = safeParse($response.body);
    if (!j) return $done({});

    var cnt = 0;
    var map = j.ad_infos_map || {};
    Object.keys(map).forEach(function (bucket) {
      var list = (map[bucket] && map[bucket].ad_infos) || [];
      list.forEach(function (ad) {
        if (typeof ad.launch_duration === "number") {
          ad.launch_duration = C.duration;
          cnt++;
        }
        if (C.video && C.videourl) {
          var vl = (ad.creative_info && ad.creative_info.video_list) || [];
          vl.forEach(function (v) {
            v.url = C.videourl;
            if (C.videomd5) v.md5_check = C.videomd5;
          });
        }
      });
    });

    log(
      "retrieve 改写: launch_duration 命中 " + cnt + " 条, 素材替换=" + (C.video ? "on" : "off")
    );
    if (C.verbose) log("retrieve 原始片段: " + short($response.body, 400));
    return finish(j);
  }

  /* ---------------- 4. /luna/advert/incentive/done ---------------- */
  function handleDone(url) {
    var j = safeParse($response.body);
    if (!j) return $done({});

    var ok = j.status_code === 0;
    var amount = 0;
    var expire = 0;
    try {
      var rd = j.reward_details || {};
      var keys = Object.keys(rd);
      if (keys.length) {
        amount = rd[keys[0]].amount || 0;
        expire = rd[keys[0]].expire_time || 0;
      }
    } catch (e) {}

    if (ok) {
      var mins = Math.round(amount / 60);
      log("done 成功: amount=" + amount + "s (" + mins + " 分钟) expire=" + expire);
      try {
        var day = new Date().toISOString().slice(0, 10);
        var stat = $persistentStore.read("soda.stat") || "";
        var rec = day + "|" + amount + "|" + Date.now();
        $persistentStore.write(stat ? stat + ";" + rec : rec, "soda.stat");
      } catch (e) {}
      if (C.verbose) {
        $notification.post("汽水音乐", "领到 " + mins + " 分钟", "今日累计见日志 soda.stat");
      }
    } else {
      log(
        "done 失败: code=" +
          j.status_code +
          " msg=" +
          (j.status_info && j.status_info.status_msg)
      );
      if (C.fake) {
        // 仅改 UI，服务端不会发权益，别当真
        var fakeBody = {
          reward_details: { "0": { reward_type: 0, amount: 1800, expire_time: Math.floor(Date.now() / 1000) + 1800, claim_status: 1 } },
          status_code: 0,
          status_info: { now: Math.floor(Date.now() / 1000), status_msg: "success", log_id: "local-fake" }
        };
        log("done 已伪造成成功（仅本地显示）");
        return $done({ body: JSON.stringify(fakeBody) });
      }
    }
    return $done({});
  }

  /* ---------------- 5. fallback token（只观测） ---------------- */
  function handleFallback(url) {
    var j = safeParse($response.body);
    if (!j) return $done({});
    if (j.post_done_extra) {
      try {
        var extra = JSON.parse(j.post_done_extra);
        log(
          "fallback token 签发: req_id=" +
            extra.req_id +
            " rit=" +
            extra.rit +
            " nonce=" +
            extra.nonce +
            " tokenLen=" +
            String(extra.time_token || "").length
        );
        $persistentStore.write(j.post_done_extra, "soda.lastExtra");
      } catch (e) {}
    }
    return $done({});
  }

  /* ---------------- 路由 ---------------- */
  var url = ($request && $request.url) || "";
  var m = ($request && $request.method) || "";

  if (/\/luna\/ads\/config(\?|$)/.test(url)) return handleAdsConfig(url);
  if (/\/luna\/advert\/incentive\/config(\?|$)/.test(url)) return handleIncentiveConfig(url);
  if (/\/luna\/advert\/incentive\/retrieve(\?|$)/.test(url)) return handleRetrieve(url);
  if (/\/luna\/advert\/incentive\/done(\?|$)/.test(url)) return handleDone(url);
  if (/\/luna\/advert\/fallback\/done\/info(\?|$)/.test(url)) return handleFallback(url);

  log("未匹配路由 " + m + " " + url);
  $done({});
})();
