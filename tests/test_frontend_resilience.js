const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

function response(payload, status = 200, retryAfter = null) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get(name) { return name.toLowerCase() === "retry-after" ? retryAfter : null; } },
    json: async () => payload,
    clone() { return response(payload, status, retryAfter); },
  };
}

function harness(queue) {
  const elements = new Map();
  const makeElement = () => ({ appendChild() {}, addEventListener() {}, children: [], disabled: false, hidden: false, textContent: "", value: "", focus() {} });
  const document = {
    getElementById(id) {
      if (!elements.has(id)) elements.set(id, makeElement());
      return elements.get(id);
    },
    createElement: makeElement,
  };
  const fetch = async () => queue.shift();
  const window = { fetch, location: { hash: "" }, history: { replaceState() {} }, setInterval() { return 1; }, clearInterval() {} };
  const source = fs.readFileSync(path.join(__dirname, "..", "app", "static", "app.js"), "utf8");
  const marker = source.indexOf("// loadHealthStatus();");
  const context = { console, Date, FormData: class {}, Number, Math, fetch, document, window };
  vm.createContext(context);
  vm.runInContext(source.slice(0, marker), context);
  return { context, elements };
}

test("429 displays Retry-After and does not retry automatically", async () => {
  const { context, elements } = harness([response({ csrf_token: "csrf" }), response({ detail: { code: "RATE_LIMIT_EXCEEDED", message: "limited" } }, 429, "7")]);
  elements.get("message-input").value = "hello";
  await context.submitChat();
  assert.match(elements.get("chat-status").textContent, /7/);
});

test("503 draining is surfaced without automatic retry", async () => {
  const { context, elements } = harness([response({ csrf_token: "csrf" }), response({ detail: { code: "SERVER_DRAINING", message: "draining" } }, 503, "5")]);
  elements.get("message-input").value = "hello";
  await context.submitChat();
  assert.match(elements.get("chat-status").textContent, /shutdown/);
});

test("request IDs are not persisted in browser storage", () => {
  const source = fs.readFileSync(path.join(__dirname, "..", "app", "static", "app.js"), "utf8");
  assert.doesNotMatch(source, /localStorage|sessionStorage/);
});
