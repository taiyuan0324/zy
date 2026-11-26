"use strict";
(function () {
  var url = typeof $request === "object" && $request ? $request.url : "";
  var body = typeof $response === "object" && $response ? $response.body : "";
  var tag = "[g1-diag] ";
  if (typeof url !== "string" || !/^https:\/\/one\.google\.com\//.test(url)) {
    $done({});
    return;
  }
  console.log(tag + "URL " + url.slice(0, 300));
  console.log(tag + "bodyType " + typeof body + " len " + (body && body.length ? body.length : 0));
  if (typeof body === "string") {
    var tokens = body.match(/(?:g1\.|com\.google\.(?:one|gemini)\.)[A-Za-z0-9._-]+/g);
    console.log(tag + "g1tokens " + (tokens ? tokens.slice(0, 60).join(",") : "none"));
    var lower = body.toLowerCase();
    ["g1", "sku", "20tb", "30tb", "7499", "4,749", "price", "offer", "product", "subscription", "iap", "3month"].forEach(function (kw) {
      var idx = lower.indexOf(kw);
      if (idx >= 0) {
        console.log(tag + kw + " @" + idx + " " + body.slice(Math.max(0, idx - 60), Math.min(body.length, idx + 160)).replace(/\s+/g, " "));
      }
    });
    console.log(tag + "head " + body.slice(0, 400).replace(/\s+/g, " "));
  }
  $done({});
})();
