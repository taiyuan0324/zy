"use strict";
(function () {
  var req = typeof $request === "object" && $request ? $request : {};
  var url = typeof req.url === "string" ? req.url : "";
  var method = typeof req.method === "string" ? req.method : "REQ";
  var tag = "[g1-wide] ";
  if (!url) { $done({}); return; }
  var lower = url.toLowerCase();
  // 只记录可能与 Google One 方案/订阅/价格相关的请求
  if (!/(sku|offer|plan|billing|subscribe|price|iap|gemini|one\.google|batchexecute|payments|checkout|acq)/.test(lower)) {
    $done({});
    return;
  }
  var resp = typeof $response === "object" && $response ? $response : {};
  console.log(tag + method + " " + url.slice(0, 400) + " status=" + (resp.status || "?"));
  $done({});
})();
