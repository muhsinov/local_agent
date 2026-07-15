const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

function makeResponse(payload, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => payload, clone() { return makeResponse(payload, status); } };
}

function makeContext(fetchImpl) {
  const element = () => ({ appendChild() {}, addEventListener() {}, children: [], disabled: false, hidden: false, textContent: "", value: "", focus() {} });
  const document = { getElementById: element, createElement: element };
  const window = { fetch: fetchImpl, location: { hash: "" }, history: { replaceState() {} }, setInterval() { return 1; }, clearInterval() {} };
  const source = fs.readFileSync(path.join(__dirname, "..", "app", "static", "app.js"), "utf8");
  const marker = source.indexOf("// loadHealthStatus();");
  const context = { console, Date, FormData: class {}, Number, Math, fetch: fetchImpl, document, window };
  vm.createContext(context);
  vm.runInContext(source.slice(0, marker), context);
  return context;
}

test("startup bootstrap and mutation wrapper use memory CSRF only", async () => {
  const calls = [];
  const context = makeContext(async (...args) => {
    calls.push(args);
    return calls.length === 1 ? makeResponse({ csrf_token: "csrf-memory" }) : makeResponse({ ok: true });
  });
  await context.bootstrapLocalSession();
  await context.localFetch("/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  assert.equal(calls[1][1].credentials, "same-origin");
  assert.equal(calls[1][1].headers["X-CSRF-Token"], "csrf-memory");
  assert.doesNotMatch(fs.readFileSync(path.join(__dirname, "..", "app", "static", "app.js"), "utf8"), /localStorage|sessionStorage/);
});

test("401 re-bootstrap retries once and direct controls are hidden", async () => {
  const calls = [];
  const context = makeContext(async (...args) => {
    calls.push(args);
    if (calls.length === 1 || calls.length === 3) return makeResponse({ csrf_token: `csrf-${calls.length}` });
    if (calls.length === 2) return makeResponse({ detail: { code: "LOCAL_SESSION_REQUIRED" } }, 401);
    return makeResponse({ ok: true });
  });
  await context.bootstrapLocalSession();
  await context.localFetch("/chat", { method: "POST" });
  assert.equal(calls.length, 4);
  assert.equal(calls[3][1].headers["X-CSRF-Token"], "csrf-3");
  const source = fs.readFileSync(path.join(__dirname, "..", "app", "static", "index.html"), "utf8");
  assert.match(source, /id="rebuild-index-button"[^>]*hidden/);
  assert.match(fs.readFileSync(path.join(__dirname, "..", "app", "static", "app.js"), "utf8"), /indexButton\.hidden = true/);
});

for (const code of ["CSRF_TOKEN_INVALID", "CSRF_TOKEN_REQUIRED"]) {
  test(`${code} retries once while direct and origin errors do not`, async () => {
    const calls = [];
    const context = makeContext(async (...args) => {
      calls.push(args);
      if (calls.length === 1) return makeResponse({ csrf_token: "csrf-1" });
      if (calls.length === 2) return makeResponse({ detail: { code } }, 403);
      if (calls.length === 3) return makeResponse({ csrf_token: "csrf-2" });
      return makeResponse({ ok: true });
    });
    await context.bootstrapLocalSession();
    const response = await context.localFetch("/chat", { method: "POST", body: "nonce=approval" });
    assert.equal(response.ok, true);
    assert.equal(calls.length, 4);
    assert.equal(calls[3][1].body, "nonce=approval");
  });
}

for (const code of ["DIRECT_ACTION_DISABLED", "LOCAL_ORIGIN_DENIED"]) {
  test(`${code} is not retried`, async () => {
    const calls = [];
    const context = makeContext(async (...args) => {
      calls.push(args);
      if (calls.length === 1) return makeResponse({ csrf_token: "csrf-1" });
      return makeResponse({ detail: { code } }, 403);
    });
    await context.bootstrapLocalSession();
    const response = await context.localFetch("/vector-index/rebuild", { method: "POST" });
    assert.equal(response.status, 403);
    assert.equal(calls.length, 2);
  });
}
