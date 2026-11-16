/**
 * soda-replay.js —— 方案 C：截获 done → 本地秒成功 → 原样重放
 * ---------------------------------------------------------------
 * 仅用于「方案 A/B 被服务端时长校验卡死」时兜底。
 *
 * 机制：
 *   1. App 发 POST /luna/advert/incentive/done（App 自己签的名，全头合法）
 *   2. 本脚本把 {url, headers, body} 原样存入 $persistentStore
 *   3. 立刻返回本地假成功，App UI 秒变「+30 分钟」
 *   4. delay 秒后用 $httpClient.post 原样重放（签名字节不变，服务端照常发奖）
 *
 * 硬性要求：
 *   - 一个字节都不能改 URL/query/headers/body，否则 x-ss-stub=MD5(body)、
 *     x-gorgon 立即对不上，服务端 400 且不发奖。
 *   - 过滤 `:` 开头的 HTTP/2 pseudo header，$httpClient 不接受。
 *   - 防递归：重放期间写 soda.replaying=1，脚本入口见到就放行。
 *
 * 参数：delay=30（秒，0=立即重放）
 *
 * 已知限制：
 *   - 部分 Loon 版本脚本 $done 后不保留 setTimeout，此时等价于「立即重放」，
 *     服务端若校验 30s 会失败 —— 看日志里 replay 的返回码即可判定。
 *   - 多值 cookie 会被合并成 "a; b"，服务端通常兼容；400 则放弃本方案。
 */

(function () {
  var TAG = "[汽水·replay]";
  var delay = 0;
  var arg = (typeof $argument !== "undefined" && $argument) ? $argument : "";
  arg.split("&").forEach(function (kv) {
    var p = kv.split("=");
    if (p[0] === "delay") {
      var n = parseInt(p[1], 10);
      if (!isNaN(n)) delay = n;
    }
  });

  function log(s) {
    console.log(TAG + " " + s);
  }

  // 防重入：重放请求被同一条规则再次命中时直接放行
  if ($persistentStore.read("soda.replaying") === "1") {
    log("replaying 中，放行");
    return $done({});
  }

  // 1) 存原始请求
  var saved = null;
  try {
    saved = {
      url: $request.url,
      headers: $request.headers || {},
      body: $request.body || ""
    };
    $persistentStore.write(JSON.stringify(saved), "soda.pending");
    log("已暂存 done 请求: " + $request.url.slice(0, 140));
    log("body 长度=" + saved.body.length + " 头数量=" + Object.keys(saved.headers).length);
  } catch (e) {
    log("暂存失败: " + e);
  }

  // 2) 过滤伪头
  function cleanHeaders(h) {
    var out = {};
    Object.keys(h).forEach(function (k) {
      if (k.charAt(0) === ":") return;          // :authority / :path / :method ...
      if (/^(host|content-length|connection)$/i.test(k)) return;
      out[k] = h[k];
    });
    return out;
  }

  // 3) 重放
  function replay() {
    if (!saved) return;
    $persistentStore.write("1", "soda.replaying");
    var opts = {
      url: saved.url,
      headers: cleanHeaders(saved.headers),
      body: saved.body,
      timeout: 30
    };
    $httpClient.post(opts, function (err, resp, data) {
      $persistentStore.write("", "soda.replaying");
      if (err) {
        log("重放失败: " + err);
        return;
      }
      var code = resp && resp.status;
      var snippet = String(data || "").slice(0, 300);
      log("重放返回 " + code + " " + snippet);
      try {
        var j = JSON.parse(data);
        var rd = (j.reward_details && j.reward_details["0"]) || null;
        if (j.status_code === 0 && rd) {
          log("✅ 服务端已发奖 amount=" + rd.amount + "s");
          $notification.post("汽水音乐", "重放成功", "到账 " + Math.round(rd.amount / 60) + " 分钟");
        } else {
          log("❌ 服务端拒绝 code=" + j.status_code + " msg=" + (j.status_info && j.status_info.status_msg));
        }
      } catch (e) {
        log("响应非 JSON");
      }
    });
  }

  if (delay > 0) {
    log("将在 " + delay + "s 后重放");
    setTimeout(replay, delay * 1000);
  } else {
    replay();
  }

  // 4) 立刻给 App 假成功（仅本机 UI）
  var now = Math.floor(Date.now() / 1000);
  var fake = {
    reward_details: {
      "0": { reward_type: 0, amount: 1800, expire_time: now + 1800, claim_status: 1 }
    },
    status_code: 0,
    status_info: { now: now, status_msg: "success", log_id: "local-fake" }
  };
  $done({
    response: {
      status: 200,
      headers: { "Content-Type": "application/json; charset=utf-8" },
      body: JSON.stringify(fake)
    }
  });
})();
