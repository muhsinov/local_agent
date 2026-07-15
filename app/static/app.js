const healthStatus = document.getElementById("health-status");
const modelStatus = document.getElementById("model-status");
const vectorStatusSummary = document.getElementById("vector-status-summary");
const vectorStatusMeta = document.getElementById("vector-status-meta");
const vectorStatusDetail = document.getElementById("vector-status-detail");
const chatStatus = document.getElementById("chat-status");
const ragMeta = document.getElementById("rag-meta");
const ragWarning = document.getElementById("rag-warning");
const ragSources = document.getElementById("rag-sources");
const useRagCheckbox = document.getElementById("use-rag-checkbox");
const useToolsCheckbox = document.getElementById("use-tools-checkbox");
const chatDocumentIds = document.getElementById("chat-document-ids");
const toolMeta = document.getElementById("tool-meta");
const toolWarning = document.getElementById("tool-warning");
const toolResults = document.getElementById("tool-results");
const approvalPanel = document.getElementById("approval-panel");
const approvalBadge = document.getElementById("approval-badge");
const approvalSummary = document.getElementById("approval-summary");
const approvalMeta = document.getElementById("approval-meta");
const approveButton = document.getElementById("approve-button");
const rejectButton = document.getElementById("reject-button");
const chatForm = document.getElementById("chat-form");
const messageInput = document.getElementById("message-input");
const chatHistory = document.getElementById("chat-history");
const sendButton = document.getElementById("send-button");
const loadingIndicator = document.getElementById("loading-indicator");
const documentForm = document.getElementById("document-form");
const documentInput = document.getElementById("document-input");
const uploadButton = document.getElementById("upload-button");
const rebuildIndexButton = document.getElementById("rebuild-index-button");
const documentStatus = document.getElementById("document-status");
const documentList = document.getElementById("document-list");
const documentPreview = document.getElementById("document-preview");
const previewMeta = document.getElementById("preview-meta");

let conversationId = null;
let pendingApproval = null;
let approvalCountdownTimer = null;
let approvalPollTimer = null;
let approvalPollInFlight = false;
let approvalPollNextDelay = null;
let approvalResultDelivered = false;
let approvalResultRequestInFlight = false;
let localCsrfToken = null;
let localBootstrapPromise = null;

const MUTATION_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const SESSION_AUTH_ERROR_CODES = new Set(["LOCAL_SESSION_REQUIRED", "CSRF_TOKEN_REQUIRED", "CSRF_TOKEN_INVALID"]);

async function bootstrapLocalSession() {
  if (localBootstrapPromise) {
    return localBootstrapPromise;
  }
  localBootstrapPromise = (async () => {
    const response = await fetch("/session/bootstrap", { method: "POST", credentials: "same-origin" });
    const payload = await safeJson(response);
    if (!response.ok || !payload?.csrf_token) {
      throw new Error("Local session bootstrap failed");
    }
    localCsrfToken = payload.csrf_token;
    return payload;
  })();
  try {
    return await localBootstrapPromise;
  } finally {
    localBootstrapPromise = null;
  }
}

async function localFetch(url, options = {}, retry = true) {
  const requestOptions = { ...options, headers: { ...(options.headers || {}) }, credentials: "same-origin" };
  const method = String(requestOptions.method || "GET").toUpperCase();
  if (MUTATION_METHODS.has(method)) {
    if (!localCsrfToken && typeof window.fetch === "function") {
      await bootstrapLocalSession();
    }
    requestOptions.headers["X-CSRF-Token"] = localCsrfToken;
  }
  const response = await fetch(url, requestOptions);
  let authErrorCode = null;
  if (typeof response.clone === "function") {
    const payload = await safeJson(response.clone());
    authErrorCode = payload?.detail?.code || null;
  }
  if (retry && (response.status === 401 || SESSION_AUTH_ERROR_CODES.has(authErrorCode))) {
    localCsrfToken = null;
    await bootstrapLocalSession();
    return localFetch(url, options, false);
  }
  return response;
}

async function safeJson(response) {
  try {
    return await response.json();
  } catch (error) {
    return null;
  }
}

function apiMessage(payload, fallback) {
  return payload?.detail?.message || fallback;
}

function resilienceMessage(response, payload, fallback) {
  const code = payload?.detail?.code;
  if (response?.status === 429 || code === "RATE_LIMIT_EXCEEDED") {
    const retryAfter = response.headers?.get?.("Retry-After") || "keyinroq";
    return `So'rovlar limiti oshdi. ${retryAfter} soniyadan keyin qayta urinib ko'ring.`;
  }
  if (response?.status === 503 && code === "SERVER_DRAINING") {
    return "Server xavfsiz shutdown jarayonida. Keyinroq qayta urinib ko'ring.";
  }
  return apiMessage(payload, fallback);
}

function parseDocumentIds(rawValue) {
  const raw = rawValue.trim();
  if (!raw) {
    return null;
  }
  const ids = raw
    .split(",")
    .map((part) => Number.parseInt(part.trim(), 10))
    .filter((value) => Number.isInteger(value) && value > 0);
  return Array.from(new Set(ids));
}

function shortGeneration(value) {
  if (!value) {
    return "none";
  }
  return value.length > 24 ? `${value.slice(0, 24)}...` : value;
}

async function loadHealthStatus() {
  try {
    const response = await localFetch("/health");
    const payload = await response.json();
    healthStatus.textContent = `${payload.status} / db: ${payload.database}`;
  } catch (error) {
    healthStatus.textContent = "unreachable";
  }
}

async function loadModelStatus() {
  try {
    const response = await localFetch("/model/status");
    const payload = await safeJson(response);
    if (!payload) {
      modelStatus.textContent = "backend error";
      return;
    }
    if (response.ok && payload.installed) {
      modelStatus.textContent = `${payload.model} ready`;
      return;
    }
    if (!response.ok) {
      modelStatus.textContent = "backend error";
      return;
    }
    if (payload.ollama === "unreachable") {
      modelStatus.textContent = "Ollama unreachable";
      return;
    }
    modelStatus.textContent = `${payload?.model || "configured model"} missing`;
  } catch (error) {
    modelStatus.textContent = "status error";
  }
}

function appendMessage(content, role) {
  const article = document.createElement("article");
  article.className = `message ${role}`;
  const paragraph = document.createElement("p");
  paragraph.textContent = content;
  article.appendChild(paragraph);
  chatHistory.appendChild(article);
  chatHistory.scrollTop = chatHistory.scrollHeight;
}

function setLoadingState(isLoading) {
  sendButton.disabled = isLoading;
  messageInput.disabled = isLoading;
  useRagCheckbox.disabled = isLoading;
  useToolsCheckbox.disabled = isLoading;
  chatDocumentIds.disabled = isLoading;
  loadingIndicator.hidden = !isLoading;
}

function renderToolSummaries(items) {
  toolResults.textContent = "";
  if (!items.length) {
    toolMeta.textContent = useToolsCheckbox.checked ? "No tool call" : "Tools off";
    toolWarning.textContent = useToolsCheckbox.checked
      ? "Bu javobda tool bajarilmadi."
      : "Tool calling faqat explicit local intent bilan ishlaydi.";
    return;
  }
  const maxIteration = Math.max(...items.map((item) => item.iteration || 0));
  toolMeta.textContent = `iterations=${maxIteration} calls=${items.length}`;
  toolWarning.textContent = items.some((item) => item.ok === false)
    ? "Ba'zi tool call muvaffaqiyatsiz tugadi."
    : "Executed tool summary.";
  items.forEach((item) => {
    const card = document.createElement("article");
    card.className = "search-result";
    const title = document.createElement("strong");
    title.textContent = item.requires_approval
      ? `${item.name} - Approval required`
      : `${item.name} - ${item.ok ? "ok" : item.error_code || "error"}`;
    const meta = document.createElement("p");
    meta.className = "muted-line";
    meta.textContent = item.requires_approval
      ? item.safe_summary || "Approval required"
      : `id=${item.id} - iteration=${item.iteration} - ${item.execution_time_ms}ms`;
    card.appendChild(title);
    card.appendChild(meta);
    toolResults.appendChild(card);
  });
}

function clearApprovalCountdown() {
  if (approvalCountdownTimer !== null) {
    window.clearInterval(approvalCountdownTimer);
    approvalCountdownTimer = null;
  }
}

function clearApprovalPolling() {
  if (approvalPollTimer !== null) {
    window.clearTimeout(approvalPollTimer);
    approvalPollTimer = null;
  }
  approvalPollNextDelay = null;
}

function clearApprovalHash() {
  if (window.location.hash.startsWith("#approval=")) {
    window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
  }
}

function retryAfterMilliseconds(response, fallbackMs = 1000) {
  const raw = response?.headers?.get?.("Retry-After")?.trim();
  let milliseconds = Number(fallbackMs);
  if (raw && /^\d+$/.test(raw)) {
    milliseconds = Number(raw) * 1000;
  } else if (raw) {
    const timestamp = Date.parse(raw);
    if (!Number.isNaN(timestamp)) milliseconds = timestamp - Date.now();
  }
  return Math.min(60000, Math.max(1000, Number.isFinite(milliseconds) ? milliseconds : 1000));
}

function scheduleApprovalPoll(delayMs = 1000) {
  if (approvalPollInFlight) {
    approvalPollNextDelay = delayMs;
    return;
  }
  if (approvalPollTimer !== null || !pendingApproval) return;
  approvalPollTimer = window.setTimeout(async () => {
    approvalPollTimer = null;
    await pollApprovalStatus();
  }, Math.min(60000, Math.max(0, delayMs)));
}

function startApprovalCountdown(expiresAt) {
  if (approvalCountdownTimer !== null) {
    return;
  }
  const refreshMeta = () => {
    const expiresMs = Date.parse(expiresAt);
    const seconds = Number.isNaN(expiresMs) ? null : Math.max(0, Math.floor((expiresMs - Date.now()) / 1000));
    approvalMeta.textContent = seconds === null ? `expires=${expiresAt}` : `expires in ${seconds}s`;
    if (seconds === 0) {
      approvalBadge.textContent = "expired";
      approveButton.disabled = true;
      rejectButton.disabled = true;
      if (pendingApproval) {
        pendingApproval.nonce = null;
      }
      clearApprovalCountdown();
    }
  };
  refreshMeta();
  approvalCountdownTimer = window.setInterval(refreshMeta, 1000);
}

function clearApprovalState() {
  clearApprovalCountdown();
  clearApprovalPolling();
  pendingApproval = null;
  approvalResultDelivered = false;
  approvalResultRequestInFlight = false;
  clearApprovalHash();
  approvalPanel.hidden = true;
  approveButton.disabled = false;
  rejectButton.disabled = false;
}

async function pollApprovalStatus() {
  if (!pendingApproval || approvalPollInFlight) {
    return;
  }
  approvalPollInFlight = true;
  try {
    const response = await localFetch(`/approvals/${pendingApproval.approvalId}`);
    const payload = await safeJson(response);
    if (!response.ok || !payload) {
      if (response.status === 429) {
        approvalMeta.textContent = resilienceMessage(response, payload, "Approval statusi vaqtincha mavjud emas.");
        scheduleApprovalPoll(retryAfterMilliseconds(response));
      } else if (response.status === 503 && payload?.detail?.code === "SERVER_DRAINING") {
        approvalMeta.textContent = resilienceMessage(response, payload, "Approval statusi vaqtincha mavjud emas.");
      }
      return;
    }
    if (pendingApproval) {
      pendingApproval.toolName = payload.tool_name;
      pendingApproval.expiresAt = payload.expires_at;
    }
    approvalBadge.textContent = payload.status;
    approvalMeta.textContent = payload.error_code || `expires=${payload.expires_at}`;
    if (payload.status === "pending") {
      startApprovalCountdown(payload.expires_at);
      scheduleApprovalPoll();
    }
    if (payload.status === "executing") {
      clearApprovalCountdown();
      scheduleApprovalPoll();
    }
    if (payload.status === "executed") {
      clearApprovalCountdown();
      if (pendingApproval?.nonce && !approvalResultDelivered) {
        if (approvalResultRequestInFlight) {
          return;
        }
        approvalResultRequestInFlight = true;
        try {
          const resultResponse = await localFetch(`/approvals/${pendingApproval.approvalId}/result`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ nonce: pendingApproval.nonce }),
          });
          const result = await safeJson(resultResponse);
          if (resultResponse.ok && result?.answer) {
            renderApprovalResult(result);
            pendingApproval.nonce = null;
            clearApprovalPolling();
            clearApprovalHash();
            return;
          }
          if (resultResponse.status === 429) {
            approvalMeta.textContent = resilienceMessage(resultResponse, result, "Final result vaqtincha mavjud emas; qayta uriniladi.");
            scheduleApprovalPoll(retryAfterMilliseconds(resultResponse));
            return;
          }
          if (resultResponse.status === 503 && result?.detail?.code === "SERVER_DRAINING") {
            approvalMeta.textContent = resilienceMessage(resultResponse, result, "Server draining; persisted result keyingi startupdan keyin conversation'da mavjud bo'lishi mumkin.");
            return;
          }
          if (resultResponse.status >= 400 && resultResponse.status < 500 && resultResponse.status !== 429) {
            approvalMeta.textContent = resilienceMessage(resultResponse, result, "Approval resultini olish rad etildi.");
            pendingApproval.nonce = null;
            clearApprovalPolling();
            return;
          }
          approvalMeta.textContent = resilienceMessage(resultResponse, result, "Final result vaqtincha mavjud emas; qayta uriniladi.");
          scheduleApprovalPoll();
          return;
        } catch (error) {
          approvalMeta.textContent = "Final resultga ulanish vaqtincha imkonsiz; qayta uriniladi.";
          scheduleApprovalPoll();
          return;
        } finally {
          approvalResultRequestInFlight = false;
        }
      }
      clearApprovalCountdown();
      clearApprovalPolling();
      if (pendingApproval) {
        pendingApproval.nonce = null;
      }
      approveButton.disabled = true;
      rejectButton.disabled = true;
      if (!approvalResultDelivered) {
        approvalMeta.textContent = "Action completed; final response conversation'da saqlandi.";
      }
      return;
    }
    if (["failed", "rejected", "expired"].includes(payload.status)) {
      clearApprovalCountdown();
      clearApprovalPolling();
      pendingApproval.nonce = null;
      approveButton.disabled = true;
      rejectButton.disabled = true;
    }
  } catch (error) {
    approvalMeta.textContent = "Approval statusini olish vaqtincha imkonsiz.";
    scheduleApprovalPoll();
  } finally {
    approvalPollInFlight = false;
    if (approvalPollNextDelay !== null) {
      const delay = approvalPollNextDelay;
      approvalPollNextDelay = null;
      scheduleApprovalPoll(delay);
    }
  }
}

function renderApprovalCard(approval) {
  clearApprovalCountdown();
  clearApprovalPolling();
  approvalResultDelivered = false;
  pendingApproval = {
    approvalId: approval.approval_id,
    nonce: approval.nonce,
    toolName: approval.tool_name,
    expiresAt: approval.expires_at,
  };
  window.history.replaceState(null, "", `#approval=${encodeURIComponent(approval.approval_id)}`);
  approvalPanel.hidden = false;
  approvalBadge.textContent = "pending";
  approvalSummary.textContent = approval.safe_summary;

  startApprovalCountdown(approval.expires_at);
}

async function restoreApprovalStatusFromUrl() {
  const match = window.location.hash.match(/^#approval=([^&]+)$/);
  if (!match) {
    return;
  }
  pendingApproval = { approvalId: decodeURIComponent(match[1]), nonce: null };
  approvalPanel.hidden = false;
  approvalBadge.textContent = "loading";
  approvalSummary.textContent = "Approval statusi yuklanmoqda...";
  approveButton.disabled = true;
  rejectButton.disabled = true;
  await pollApprovalStatus();
  if (pendingApproval && approvalBadge.textContent === "executing") {
    scheduleApprovalPoll();
  }
}

async function submitApprovalDecision(kind) {
  if (!pendingApproval || !pendingApproval.nonce) {
    return;
  }
  approveButton.disabled = true;
  rejectButton.disabled = true;
  clearApprovalCountdown();
  approvalBadge.textContent = kind === "approve" ? "executing" : "rejecting";
  try {
    const response = await localFetch(`/approvals/${pendingApproval.approvalId}/${kind}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nonce: pendingApproval.nonce }),
    });
    const payload = await safeJson(response);
    if (!payload) {
      appendMessage("Approval javobi noto'g'ri.", "system");
      clearApprovalState();
      return;
    }
    if (!response.ok) {
      approvalBadge.textContent = payload?.detail?.code || "failed";
      approvalMeta.textContent = apiMessage(payload, "Approval bajarilmadi.");
      approveButton.disabled = false;
      rejectButton.disabled = false;
      return;
    }
    if (payload.status === "executing") {
      scheduleApprovalPoll();
      return;
    }
    pendingApproval.nonce = null;
    approvalBadge.textContent = payload.status;
    approvalMeta.textContent = payload.error_code || `expires=${payload.expires_at}`;
    if (kind === "approve" && payload.answer) {
      renderApprovalResult(payload);
      pendingApproval.nonce = null;
      clearApprovalHash();
    }
    if (kind === "reject") {
      appendMessage("Action rad etildi.", "system");
    }
  } catch (error) {
    approvalBadge.textContent = "failed";
    approvalMeta.textContent = "Approval so'rovini yuborib bo'lmadi.";
  } finally {
    if (!pendingApproval || pendingApproval.nonce === null) {
      clearApprovalCountdown();
      if (approvalBadge.textContent !== "executing") {
        clearApprovalPolling();
      }
    }
  }
}

function renderRagSources(sources) {
  ragSources.textContent = "";
  if (!sources.length) {
    const empty = document.createElement("p");
    empty.textContent = "Source topilmadi.";
    ragSources.appendChild(empty);
    return;
  }
  sources.forEach((source) => {
    const card = document.createElement("article");
    card.className = "search-result";
    const header = document.createElement("div");
    header.className = "result-header";
    const title = document.createElement("strong");
    title.textContent = `${source.citation} ${source.file_name} - chunk #${source.chunk_index}`;
    const score = document.createElement("span");
    score.className = "result-score";
    score.textContent = `score=${source.score.toFixed(3)} - ${source.start_char}-${source.end_char}`;
    const text = document.createElement("pre");
    text.className = "result-text";
    text.textContent = source.excerpt;
    const trust = document.createElement("p");
    trust.className = "muted-line";
    trust.textContent = "Untrusted document content";
    header.appendChild(title);
    header.appendChild(score);
    card.appendChild(header);
    card.appendChild(text);
    card.appendChild(trust);
    ragSources.appendChild(card);
  });
}

function renderApprovalResult(payload) {
  if (!payload?.answer || approvalResultDelivered) {
    return false;
  }
  conversationId = payload.conversation_id || conversationId;
  appendMessage(payload.answer, "system");
  renderRagSources(payload.sources || []);
  const rag = payload.rag || {};
  const usage = payload.usage || {};
  ragMeta.textContent = `gen=${shortGeneration(rag.generation_id)} • chars=${rag.context_chars || 0}`
    + (usage.prompt_tokens !== null && usage.prompt_tokens !== undefined
      ? ` • tokens=${usage.prompt_tokens}/${usage.completion_tokens ?? "?"}`
      : "");
  ragWarning.textContent = rag.invalid_citations_removed
    ? `${rag.invalid_citations_removed} invalid citation olib tashlandi.`
    : rag.fallback
      ? "Fallback ishladi. Source ishlatilmagan."
      : rag.used
        ? "Approval resume RAG source'lari bilan grounded qilindi."
        : "Approval resume'da RAG ishlatilmadi.";
  chatStatus.textContent = rag.used
    ? "Approval resume hujjatlar bilan grounded qilindi."
    : rag.fallback
      ? "Approval resume hujjatlarsiz yaratildi."
      : "Approval resume RAG'siz yaratildi.";
  approvalResultDelivered = true;
  return true;
}

async function submitChat() {
  const content = messageInput.value.trim();
  if (!content) {
    return;
  }
  appendMessage(content, "user");
  messageInput.value = "";
  setLoadingState(true);
  try {
    clearApprovalState();
    const response = await localFetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: content,
        conversation_id: conversationId,
        use_rag: useRagCheckbox.checked,
        use_tools: useToolsCheckbox.checked,
        document_ids: parseDocumentIds(chatDocumentIds.value),
      }),
    });
    const payload = await safeJson(response);
    if (!payload) {
      appendMessage("Backend noto'g'ri javob qaytardi.", "system");
      return;
    }
    if (!response.ok) {
      appendMessage(resilienceMessage(response, payload, "Noma'lum xatolik yuz berdi."), "system");
      if (response.status === 429 || payload?.detail?.code === "SERVER_DRAINING") {
        chatStatus.textContent = resilienceMessage(response, payload, "Request vaqtincha bajarilmadi.");
      }
      return;
    }
    conversationId = payload.conversation_id;
    appendMessage(payload.answer, "system");
    if (payload.approval?.required) {
      renderApprovalCard(payload.approval);
    }
    chatStatus.textContent = payload.rag.used
      ? "Javob hujjatlar bilan grounded qilindi."
      : payload.rag.fallback
        ? "Javob hujjatlarsiz yaratildi."
        : "RAG o'chirilgan yoki ishlatilmadi.";
    ragMeta.textContent = `gen=${shortGeneration(payload.rag.generation_id)} • chars=${payload.rag.context_chars}`;
    ragWarning.textContent = payload.rag.fallback
      ? "Fallback ishladi. Dirty index bo'lsa rebuild qiling."
      : payload.rag.used
        ? "Citation markerlari answer ichida bo'lishi mumkin."
        : "Source ishlatilmagan.";
    renderRagSources(payload.sources || []);
    renderToolSummaries(payload.tool_calls || []);
  } catch (error) {
    appendMessage("Backend bilan bog'lanib bo'lmadi.", "system");
  } finally {
    setLoadingState(false);
    messageInput.focus();
  }
}

function formatBytes(value) {
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function setDocumentStatus(message) {
  documentStatus.textContent = message;
}

async function refreshVectorStatus() {
  try {
    const response = await localFetch("/vector-index/status");
    const payload = await safeJson(response);
    if (!payload || !response.ok) {
      vectorStatusSummary.textContent = "error";
      vectorStatusMeta.textContent = "";
      vectorStatusDetail.textContent = apiMessage(payload, "Vector index statusni yuklab bo'lmadi.");
      return;
    }
    vectorStatusSummary.textContent = `${payload.status}${payload.dirty ? " (dirty)" : ""}`;
    vectorStatusMeta.textContent = `gen=${shortGeneration(payload.active_generation)}`;
    vectorStatusDetail.textContent = `docs=${payload.document_count} chunks=${payload.chunk_count} model=${payload.embedding_model || "-"} dim=${payload.embedding_dimension || "-"}`;
  } catch (error) {
    vectorStatusSummary.textContent = "error";
    vectorStatusDetail.textContent = "Vector index statusni yuklab bo'lmadi.";
  }
}

async function refreshDocuments() {
  try {
    const response = await localFetch("/documents?limit=50&offset=0");
    const payload = await safeJson(response);
    if (!payload || !response.ok) {
      setDocumentStatus(resilienceMessage(response, payload, "Document listni yuklab bo'lmadi."));
      return;
    }
    documentList.textContent = "";
    if (!payload.items.length) {
      const empty = document.createElement("p");
      empty.textContent = "Hozircha hujjatlar yo'q.";
      documentList.appendChild(empty);
      return;
    }
    payload.items.forEach((item) => {
      const card = document.createElement("article");
      card.className = "document-card";
      const title = document.createElement("strong");
      title.textContent = item.file_name;
      const meta = document.createElement("p");
      meta.textContent = `${item.file_type.toUpperCase()} - ${formatBytes(item.size_bytes)} - status=${item.status} - chars=${item.char_count}`;
      const extra = document.createElement("p");
      extra.textContent = `pages=${item.page_count ?? "-"} - indexed=${item.indexed} - warning=${item.warning_code ?? "none"}`;
      const actions = document.createElement("div");
      actions.className = "document-actions";
      const previewButton = document.createElement("button");
      previewButton.type = "button";
      previewButton.textContent = "Preview";
      previewButton.addEventListener("click", async () => previewDocument(item.id));
      const indexButton = document.createElement("button");
      indexButton.type = "button";
      indexButton.textContent = "Index";
      indexButton.hidden = true;
      indexButton.disabled = item.status !== "ready" || item.char_count <= 0;
      indexButton.addEventListener("click", async () => indexDocument(item.id, item.file_name));
      const deleteButton = document.createElement("button");
      deleteButton.type = "button";
      deleteButton.textContent = "Delete";
      deleteButton.hidden = true;
      deleteButton.addEventListener("click", async () => deleteDocument(item.id, item.file_name));
      actions.appendChild(previewButton);
      actions.appendChild(indexButton);
      actions.appendChild(deleteButton);
      card.appendChild(title);
      card.appendChild(meta);
      card.appendChild(extra);
      card.appendChild(actions);
      documentList.appendChild(card);
    });
  } catch (error) {
    setDocumentStatus("Document listni yuklab bo'lmadi.");
  }
}

async function previewDocument(documentId) {
  const response = await localFetch(`/documents/${documentId}/text?limit=5000`);
  const payload = await safeJson(response);
  if (!payload || !response.ok) {
    documentPreview.textContent = resilienceMessage(response, payload, "Previewni yuklab bo'lmadi.");
    previewMeta.textContent = "";
    return;
  }
  documentPreview.textContent = payload.text || "(matn topilmadi)";
  previewMeta.textContent = `returned=${payload.returned_chars}, total=${payload.total_chars}, truncated=${payload.truncated}`;
}

async function deleteDocument(documentId, fileName) {
  if (!window.confirm(`${fileName} hujjatini o'chirishni tasdiqlaysizmi?`)) {
    return;
  }
  const response = await localFetch(`/documents/${documentId}?confirm=true`, { method: "DELETE" });
  const payload = await safeJson(response);
  if (!response.ok) {
    setDocumentStatus(resilienceMessage(response, payload, "Delete bajarilmadi."));
    return;
  }
  documentPreview.textContent = "Preview hali tanlanmagan.";
  previewMeta.textContent = "";
  setDocumentStatus("Delete bajarildi.");
  await refreshDocuments();
  await refreshVectorStatus();
}

async function uploadDocument(event) {
  event.preventDefault();
  const file = documentInput.files?.[0];
  if (!file) {
    setDocumentStatus("Avval fayl tanlang.");
    return;
  }
  const formData = new FormData();
  formData.append("file", file);
  uploadButton.disabled = true;
  documentInput.disabled = true;
  setDocumentStatus("Upload qilinmoqda...");
  try {
    const response = await localFetch("/documents/upload", { method: "POST", body: formData });
    const payload = await safeJson(response);
    if (!payload || !response.ok) {
      setDocumentStatus(resilienceMessage(response, payload, "Upload bajarilmadi."));
      return;
    }
    setDocumentStatus(`Yuklandi: ${payload.file_name}`);
    documentInput.value = "";
    await refreshDocuments();
    await refreshVectorStatus();
  } catch (error) {
    setDocumentStatus("Upload vaqtida backend bilan bog'lanib bo'lmadi.");
  } finally {
    uploadButton.disabled = false;
    documentInput.disabled = false;
  }
}

async function rebuildIndex() {
  rebuildIndexButton.disabled = true;
  setDocumentStatus("Vector index qayta qurilmoqda...");
  try {
    const response = await localFetch("/vector-index/rebuild", { method: "POST" });
    const payload = await safeJson(response);
    if (!payload || !response.ok) {
      setDocumentStatus(resilienceMessage(response, payload, "Vector indexni qayta qurib bo'lmadi."));
      return;
    }
    setDocumentStatus(`Index ready: ${shortGeneration(payload.generation_id)}`);
    await refreshDocuments();
    await refreshVectorStatus();
  } finally {
    rebuildIndexButton.disabled = false;
  }
}

async function indexDocument(documentId, fileName) {
  setDocumentStatus(`${fileName} uchun index rebuild boshlandi...`);
  try {
    const response = await localFetch(`/documents/${documentId}/index`, { method: "POST" });
    const payload = await safeJson(response);
    if (!payload || !response.ok) {
      setDocumentStatus(resilienceMessage(response, payload, "Document index bajarilmadi."));
      return;
    }
    setDocumentStatus(`Index ready: ${shortGeneration(payload.generation_id)}`);
    await refreshDocuments();
    await refreshVectorStatus();
  } catch (error) {
    setDocumentStatus("Index so'rovini bajarib bo'lmadi.");
  }
}

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await submitChat();
});

messageInput.addEventListener("keydown", async (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    await submitChat();
  }
});

documentForm.addEventListener("submit", uploadDocument);
rebuildIndexButton.addEventListener("click", rebuildIndex);
approveButton.addEventListener("click", async () => submitApprovalDecision("approve"));
rejectButton.addEventListener("click", async () => submitApprovalDecision("reject"));

async function initializeApp() {
  try {
    await bootstrapLocalSession();
  } catch (error) {
    documentStatus.textContent = "Local session bootstrap muvaffaqiyatsiz.";
  }
  loadHealthStatus.call(null);
  loadModelStatus.call(null);
  refreshVectorStatus.call(null);
  refreshDocuments.call(null);
  renderToolSummaries([]);
  restoreApprovalStatusFromUrl.call(null);
}

// loadHealthStatus();
initializeApp();
