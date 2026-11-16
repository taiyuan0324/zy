/**
 * 汽水 · 链路哨兵（纯诊断，不改任何请求/响应）
 * ---------------------------------------------------------------
 * 用途：判断「Loon 有没有真的执行插件脚本」这条链路是否通。
 * 规则用极宽 URL 正则，只要 App 有任何 qishui / douyin / luna /
 * bytedance / snssdk / bytegecko 相关请求经过 Loon，就会命中。
 *
 * 命中后做三件事：
 *   1) console.log 打 [哨兵]（Loon → 脚本 → 日志里看，不依赖 iOS 通知权限）
 *   2) $notification.post 发系统通知（若被权限吞掉，日志仍在）
 *   3) $persistentStore 写 soda.sentinel，累计命中次数与最后 URL
 *
 * 诊断时请临时【只启用本插件】，关掉其它所有插件，避免新版 Loon
 * 「Response Script 只选第一条命中」把哨兵挤掉。
 */
(function () {
  var u = (typeof $request !== "undefined" && $request && $request.url) || "(无 $request：CRON / 手动运行)";
  var hasResp = typeof $response !== "undefined" && !!$response;
  var stage = hasResp ? "RESP" : "REQ";
  var bl = -1;
  try {
    bl = (hasResp && $response.body != null) ? String($response.body).length : -1;
  } catch (e) { bl = -2; }

  var msg = stage + " body=" + bl + "B | " + u.slice(0, 160);
  try { console.log("[哨兵] " + msg); } catch (e) {}
  try {
    $notification.post("汽水·哨兵 " + stage, "Loon 脚本引擎已执行", msg);
  } catch (e) {
    try { console.log("[哨兵] 通知失败（查 iOS 通知权限 / Loon 通知设置）：" + e); } catch (e2) {}
  }
  try {
    var n = parseInt($persistentStore.read("soda.sentinel"), 10) || 0;
    $persistentStore.write(String(n + 1), "soda.sentinel");
    $persistentStore.write(msg, "soda.sentinel.last");
  } catch (e) {}
  try { $done({}); } catch (e) {}
})();
