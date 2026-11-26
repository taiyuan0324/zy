"use strict";
(function () {
  var req = typeof $request === "object" && $request ? $request : {};
  var url = typeof req.url === "string" ? req.url : "";
  var method = typeof req.method === "string" ? req.method : "REQ";
  var tag = "[g1-wide] ";
  if (!url) { $done({}); return; }
  console.log(tag + method + " " + url.slice(0, 500));
  var rb = req.body;
  if (typeof rb === "string" && rb.length) {
    console.log(tag + "reqBody(" + rb.length + ") " + rb.slice(0, 1200).replace(/\s+/g, " "));
  } else if (rb && typeof rb === "object") {
    console.log(tag + "reqBodyObj " + JSON.stringify(rb).slice(0, 1200));
  }
  $done({});
})();
