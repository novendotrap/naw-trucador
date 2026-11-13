const http = require("http");

// A bounded request: restore Windows settings before taskkill forcibly ends Flask.
function stopProxy(baseUrl, timeoutMs = 5000) {
  return new Promise((resolve) => {
    let finished = false;
    let timer;
    const done = (ok) => {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      resolve(ok);
    };
    const req = http.request(new URL("/api/proxy/stop", baseUrl), {
      method: "POST",
      headers: { "Content-Type": "application/json", "Content-Length": "2" },
    }, (res) => {
      let body = "";
      res.setEncoding("utf8");
      res.on("data", chunk => { if (body.length < 16384) body += chunk; });
      res.on("end", () => {
        try { done(res.statusCode === 200 && JSON.parse(body).ok === true); }
        catch { done(false); }
      });
      res.on("error", () => done(false));
    });
    req.on("error", () => done(false));
    timer = setTimeout(() => { done(false); req.destroy(); }, timeoutMs);
    req.end("{}");
  });
}

module.exports = { stopProxy };
