const test = require("node:test");
const assert = require("node:assert/strict");
const http = require("node:http");
const { stopProxy } = require("../desktop/proxy_shutdown.cjs");

async function fixture(handler, run) {
  const server = http.createServer(handler);
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  try { await run(`http://127.0.0.1:${server.address().port}`); }
  finally { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
}

test("requests proxy stop before desktop termination", async () => {
  let request;
  await fixture((req, res) => {
    let body = "";
    req.on("data", chunk => body += chunk);
    req.on("end", () => { request = [req.method, req.url, body]; res.end('{"ok":true}'); });
  }, async url => assert.equal(await stopProxy(url), true));
  assert.deepEqual(request, ["POST", "/api/proxy/stop", "{}"]);
});

test("network failure does not prevent desktop exit", async () => {
  await fixture((req, res) => res.destroy(), async url => {
    assert.equal(await stopProxy(url), false);
  });
});

test("backend cleanup failure is not reported as success", async () => {
  await fixture((req, res) => res.end('{"ok":false}'), async url => {
    assert.equal(await stopProxy(url), false);
  });
});

test("unresponsive backend has bounded cleanup", async () => {
  await fixture(() => {}, async url => {
    assert.equal(await stopProxy(url, 60), false);
  });
});
