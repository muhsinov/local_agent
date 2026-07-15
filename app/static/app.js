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
    const response = await fetch("/health");
    const payload = await response.json();
    healthStatus.textContent = `${payload.status} / db: ${payload.database}`;
  } catch (error) {
    healthStatus.textContent = "unreachable";
  }
}

async function loadModelStatus() {
  try {
    const response = await fetch("/model/status");
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

function clearApprovalTimer() {
  if (approvalCountdownTimer !== null) {
    window.clearInterval(approvalCountdownTimer);
    approvalCountdownTimer = null;
  }
}

function clearApprovalState() {
  clearApprovalTimer();
  pendingApproval = null;
  approvalPanel.hidden = true;
  approveButton.disabled = false;
  rejectButton.disabled = false;
}

function renderApprovalCard(approval) {
  clearApprovalTimer();
  pendingApproval = {
    approvalId: approval.approval_id,
    nonce: approval.nonce,
    toolName: approval.tool_name,
    expiresAt: approval.expires_at,
  };
  approvalPanel.hidden = false;
  approvalBadge.textContent = "pending";
  approvalSummary.textContent = approval.safe_summary;

  const refreshMeta = () => {
    const expiresMs = Date.parse(approval.expires_at);
    const seconds = Number.isNaN(expiresMs) ? null : Math.max(0, Math.floor((expiresMs - Date.now()) / 1000));
    approvalMeta.textContent = seconds === null ? `expires=${approval.expires_at}` : `expires in ${seconds}s`;
    if (seconds === 0) {
      approvalBadge.textContent = "expired";
      approveButton.disabled = true;
      rejectButton.disabled = true;
      if (pendingApproval) {
        pendingApproval.nonce = null;
      }
      clearApprovalTimer();
    }
  };

  refreshMeta();
  approvalCountdownTimer = window.setInterval(refreshMeta, 1000);
}

async function submitApprovalDecision(kind) {
  if (!pendingApproval || !pendingApproval.nonce) {
    return;
  }
  approveButton.disabled = true;
  rejectButton.disabled = true;
  approvalBadge.textContent = kind === "approve" ? "executing" : "rejecting";
  try {
    const response = await fetch(`/approvals/${pendingApproval.approvalId}/${kind}`, {
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
    pendingApproval.nonce = null;
    approvalBadge.textContent = payload.status;
    approvalMeta.textContent = payload.error_code || `expires=${payload.expires_at}`;
    if (kind === "approve" && payload.answer) {
      conversationId = payload.conversation_id_result || conversationId;
      appendMessage(payload.answer, "system");
    }
    if (kind === "reject") {
      appendMessage("Action rad etildi.", "system");
    }
  } catch (error) {
    approvalBadge.textContent = "failed";
    approvalMeta.textContent = "Approval so'rovini yuborib bo'lmadi.";
  } finally {
    clearApprovalTimer();
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
    const response = await fetch("/chat", {
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
      appendMessage(apiMessage(payload, "Noma'lum xatolik yuz berdi."), "system");
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
    const response = await fetch("/vector-index/status");
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
    const response = await fetch("/documents?limit=50&offset=0");
    const payload = await safeJson(response);
    if (!payload || !response.ok) {
      setDocumentStatus(apiMessage(payload, "Document listni yuklab bo'lmadi."));
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
      indexButton.disabled = item.status !== "ready" || item.char_count <= 0;
      indexButton.addEventListener("click", async () => indexDocument(item.id, item.file_name));
      const deleteButton = document.createElement("button");
      deleteButton.type = "button";
      deleteButton.textContent = "Delete";
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
  const response = await fetch(`/documents/${documentId}/text?limit=5000`);
  const payload = await safeJson(response);
  if (!payload || !response.ok) {
    documentPreview.textContent = apiMessage(payload, "Previewni yuklab bo'lmadi.");
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
  const response = await fetch(`/documents/${documentId}?confirm=true`, { method: "DELETE" });
  const payload = await safeJson(response);
  if (!response.ok) {
    setDocumentStatus(apiMessage(payload, "Delete bajarilmadi."));
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
    const response = await fetch("/documents/upload", { method: "POST", body: formData });
    const payload = await safeJson(response);
    if (!payload || !response.ok) {
      setDocumentStatus(apiMessage(payload, "Upload bajarilmadi."));
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
    const response = await fetch("/vector-index/rebuild", { method: "POST" });
    const payload = await safeJson(response);
    if (!payload || !response.ok) {
      setDocumentStatus(apiMessage(payload, "Vector indexni qayta qurib bo'lmadi."));
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
    const response = await fetch(`/documents/${documentId}/index`, { method: "POST" });
    const payload = await safeJson(response);
    if (!payload || !response.ok) {
      setDocumentStatus(apiMessage(payload, "Document index bajarilmadi."));
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

loadHealthStatus();
loadModelStatus();
refreshVectorStatus();
refreshDocuments();
renderToolSummaries([]);
