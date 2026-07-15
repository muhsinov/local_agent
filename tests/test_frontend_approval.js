const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

function makeResponse(payload, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => payload };
}

function makeHarness(fetchImpl, hash = "") {
  const elements = new Map();
  const makeElement = () => ({
    appendChild(child) {
      this.children.push(child);
    },
    addEventListener() {},
    children: [],
    disabled: false,
    hidden: false,
    textContent: "",
    value: "",
    focus() {},
  });
  const document = {
    getElementById(id) {
      if (!elements.has(id)) {
        elements.set(id, makeElement());
      }
      return elements.get(id);
    },
    createElement() {
      return makeElement();
    },
  };
  let nextTimer = 1;
  const timers = new Map();
  const calls = [];
  const window = {
    location: { hash },
    history: {
      replaceState(_state, _title, url) {
        window.location.hash = url.includes("#") ? url.slice(url.indexOf("#")) : "";
      },
    },
    setInterval(callback) {
      const id = nextTimer++;
      timers.set(id, callback);
      return id;
    },
    clearInterval(id) {
      timers.delete(id);
    },
    setTimeout(callback) {
      const id = nextTimer++;
      timers.set(id, callback);
      return id;
    },
    clearTimeout(id) {
      timers.delete(id);
    },
  };
  const fetch = async (...args) => {
    calls.push(args[0]);
    return fetchImpl(...args);
  };
  const source = fs.readFileSync(path.join(__dirname, "..", "app", "static", "app.js"), "utf8");
  const initialization = source.indexOf("loadHealthStatus();");
  const context = { console, Date, FormData: class {}, Number, Math, fetch, document, window };
  vm.createContext(context);
  vm.runInContext(initialization >= 0 ? source.slice(0, initialization) : source, context);
  return { context, elements, timers, calls };
}

function approval() {
  return {
    approval_id: "approval-1",
    nonce: "nonce-1",
    tool_name: "rename_conversation",
    safe_summary: "Rename",
    expires_at: "2099-01-01T00:00:00Z",
  };
}

function resultPayload() {
  return {
    approval_id: "approval-1",
    status: "executed",
    conversation_id: 7,
    answer: "Final answer",
    sources: [{ citation: "[1]", chunk_id: 12, document_id: 3, file_name: "note.txt", chunk_index: 0, score: 0.8, start_char: 0, end_char: 20, excerpt: "excerpt" }],
    rag: { enabled: true, used: true, fallback: false, generation_id: "gen", retrieved_count: 1, context_chars: 10, citations_present: true, invalid_citations_removed: 1 },
    usage: { prompt_tokens: 10, completion_tokens: 4 },
  };
}

test("202 keeps polling and nonce, retries result, and renders once", async () => {
  const queue = [
    makeResponse({ status: "executing", expires_at: approval().expires_at }),
    makeResponse({ status: "executed", expires_at: approval().expires_at }),
    new Error("temporary network failure"),
    makeResponse({ status: "executed", expires_at: approval().expires_at }),
    makeResponse(resultPayload()),
  ];
  const harness = makeHarness(async () => {
    const next = queue.shift();
    if (next instanceof Error) throw next;
    return next;
  });
  const context = harness.context;
  context.renderApprovalCard(approval());
  await context.submitApprovalDecision("approve");
  assert.equal(harness.elements.get("approval-badge").textContent, "executing");
  assert.equal(harness.timers.size, 1);
  await context.pollApprovalStatus();
  assert.equal(harness.timers.size, 1);
  await context.pollApprovalStatus();
  assert.equal(harness.elements.get("chat-history").children.length, 1);
  assert.equal(harness.elements.get("rag-sources").children.length, 1);
  assert.match(harness.elements.get("rag-meta").textContent, /tokens=10\/4/);
  assert.equal(harness.timers.size, 0);
  assert.equal(harness.calls.filter((url) => String(url).endsWith("/result")).length, 2);
});

test("result requests are not parallel", async () => {
  let release;
  const deferred = new Promise((resolve) => { release = resolve; });
  let resultCalls = 0;
  const harness = makeHarness(async (url) => {
    if (String(url).endsWith("/approve")) return makeResponse({ status: "executing", expires_at: approval().expires_at });
    if (String(url).endsWith("/result")) {
      resultCalls += 1;
      await deferred;
      return makeResponse(resultPayload());
    }
    return makeResponse({ status: "executed", expires_at: approval().expires_at });
  });
  harness.context.renderApprovalCard(approval());
  await harness.context.submitApprovalDecision("approve");
  const first = harness.context.pollApprovalStatus();
  await new Promise((resolve) => setImmediate(resolve));
  const second = harness.context.pollApprovalStatus();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(resultCalls, 1);
  release();
  await Promise.all([first, second]);
  assert.equal(harness.elements.get("chat-history").children.length, 1);
});

test("terminal status clears nonce and refresh never calls result", async () => {
  const harness = makeHarness(async (url) => {
    if (String(url).includes("/approvals/approval-1")) return makeResponse({ status: "failed", error_code: "X", expires_at: approval().expires_at });
    return makeResponse({});
  });
  harness.context.renderApprovalCard(approval());
  await harness.context.pollApprovalStatus();
  assert.equal(harness.timers.size, 0);
  assert.equal(harness.elements.get("approve-button").disabled, true);
  assert.equal(harness.calls.some((url) => String(url).includes("/result")), false);

  const refresh = makeHarness(async () => makeResponse({ status: "executed", expires_at: approval().expires_at }), "#approval=approval-1");
  await refresh.context.restoreApprovalStatusFromUrl();
  assert.equal(refresh.calls.some((url) => String(url).includes("/result")), false);
  assert.match(refresh.elements.get("approval-meta").textContent, /Action completed/);
});
