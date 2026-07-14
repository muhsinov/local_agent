const healthStatus = document.getElementById("health-status");
const modelStatus = document.getElementById("model-status");
const chatStatus = document.getElementById("chat-status");
const chatForm = document.getElementById("chat-form");
const messageInput = document.getElementById("message-input");
const chatHistory = document.getElementById("chat-history");
const sendButton = document.getElementById("send-button");
const loadingIndicator = document.getElementById("loading-indicator");
const documentForm = document.getElementById("document-form");
const documentInput = document.getElementById("document-input");
const uploadButton = document.getElementById("upload-button");
const documentStatus = document.getElementById("document-status");
const documentList = document.getElementById("document-list");
const documentPreview = document.getElementById("document-preview");
const previewMeta = document.getElementById("preview-meta");

let conversationId = null;

async function safeJson(response) {
  try {
    return await response.json();
  } catch (error) {
    return null;
  }
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
      chatStatus.textContent = "Model status javobi noto‘g‘ri formatda keldi.";
      return;
    }
    if (response.ok && payload.installed) {
      modelStatus.textContent = `${payload.model} ready`;
      chatStatus.textContent = "Local model tayyor.";
      return;
    }
    if (!response.ok) {
      modelStatus.textContent = "backend error";
      chatStatus.textContent = payload?.detail?.message || "Model statusni yuklab bo‘lmadi.";
      return;
    }
    if (payload.ollama === "unreachable") {
      modelStatus.textContent = "Ollama unreachable";
      chatStatus.textContent = "Ollama server ishlamayapti yoki ulanib bo‘lmadi.";
      return;
    }
    const modelName = payload?.model || "configured model";
    modelStatus.textContent = `${modelName} missing`;
    chatStatus.textContent = "Model o‘rnatilmagan. scripts/prepare_ollama.ps1 orqali tayyorlang.";
  } catch (error) {
    modelStatus.textContent = "status error";
    chatStatus.textContent = "Model statusni yuklab bo‘lmadi.";
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
  loadingIndicator.hidden = !isLoading;
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
    const response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: content,
        conversation_id: conversationId,
      }),
    });
    const payload = await safeJson(response);
    if (!payload) {
      appendMessage("Backend noto‘g‘ri javob qaytardi.", "system");
      return;
    }
    if (!response.ok) {
      appendMessage(payload?.detail?.message || "Noma’lum xatolik yuz berdi.", "system");
      return;
    }
    conversationId = payload.conversation_id;
    appendMessage(payload.answer, "system");
  } catch (error) {
    appendMessage("Backend bilan bog‘lanib bo‘lmadi.", "system");
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

async function refreshDocuments() {
  try {
    const response = await fetch("/documents?limit=50&offset=0");
    const payload = await safeJson(response);
    if (!payload || !response.ok) {
      setDocumentStatus(payload?.detail?.message || "Document listni yuklab bo‘lmadi.");
      return;
    }
    documentList.textContent = "";
    if (!payload.items.length) {
      const empty = document.createElement("p");
      empty.textContent = "Hozircha hujjatlar yo‘q.";
      documentList.appendChild(empty);
      return;
    }
    payload.items.forEach((item) => {
      const card = document.createElement("article");
      card.className = "document-card";

      const title = document.createElement("strong");
      title.textContent = item.file_name;

      const meta = document.createElement("p");
      meta.textContent = `${item.file_type.toUpperCase()} • ${formatBytes(item.size_bytes)} • status=${item.status} • chars=${item.char_count}`;

      const extra = document.createElement("p");
      extra.textContent = `pages=${item.page_count ?? "-"} • warning=${item.warning_code ?? "none"}`;

      const actions = document.createElement("div");
      actions.className = "document-actions";

      const previewButton = document.createElement("button");
      previewButton.type = "button";
      previewButton.textContent = "Preview";
      previewButton.addEventListener("click", async () => {
        await previewDocument(item.id);
      });

      const deleteButton = document.createElement("button");
      deleteButton.type = "button";
      deleteButton.textContent = "Delete";
      deleteButton.addEventListener("click", async () => {
        await deleteDocument(item.id, item.file_name);
      });

      actions.appendChild(previewButton);
      actions.appendChild(deleteButton);
      card.appendChild(title);
      card.appendChild(meta);
      card.appendChild(extra);
      card.appendChild(actions);
      documentList.appendChild(card);
    });
  } catch (error) {
    setDocumentStatus("Document listni yuklab bo‘lmadi.");
  }
}

async function previewDocument(documentId) {
  const response = await fetch(`/documents/${documentId}/text?limit=5000`);
  const payload = await safeJson(response);
  if (!payload || !response.ok) {
    documentPreview.textContent = payload?.detail?.message || "Previewni yuklab bo‘lmadi.";
    previewMeta.textContent = "";
    return;
  }
  documentPreview.textContent = payload.text || "(matn topilmadi)";
  previewMeta.textContent = `returned=${payload.returned_chars}, total=${payload.total_chars}, truncated=${payload.truncated}`;
}

async function deleteDocument(documentId, fileName) {
  if (!window.confirm(`${fileName} hujjatini o‘chirishni tasdiqlaysizmi?`)) {
    return;
  }
  const response = await fetch(`/documents/${documentId}?confirm=true`, { method: "DELETE" });
  const payload = await safeJson(response);
  if (!response.ok) {
    setDocumentStatus(payload?.detail?.message || "Delete bajarilmadi.");
    return;
  }
  documentPreview.textContent = "Preview hali tanlanmagan.";
  previewMeta.textContent = "";
  setDocumentStatus("Delete bajarildi.");
  await refreshDocuments();
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
    const response = await fetch("/documents/upload", {
      method: "POST",
      body: formData,
    });
    const payload = await safeJson(response);
    if (!payload || !response.ok) {
      setDocumentStatus(payload?.detail?.message || "Upload bajarilmadi.");
      return;
    }
    setDocumentStatus(`Yuklandi: ${payload.file_name}`);
    documentInput.value = "";
    await refreshDocuments();
  } catch (error) {
    setDocumentStatus("Upload vaqtida backend bilan bog‘lanib bo‘lmadi.");
  } finally {
    uploadButton.disabled = false;
    documentInput.disabled = false;
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

loadHealthStatus();
loadModelStatus();
refreshDocuments();
