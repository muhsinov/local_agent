const healthStatus = document.getElementById("health-status");
const modelStatus = document.getElementById("model-status");
const chatStatus = document.getElementById("chat-status");
const chatForm = document.getElementById("chat-form");
const messageInput = document.getElementById("message-input");
const chatHistory = document.getElementById("chat-history");
const sendButton = document.getElementById("send-button");
const loadingIndicator = document.getElementById("loading-indicator");

let conversationId = null;

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
    let payload = null;
    try {
      payload = await response.json();
    } catch (error) {
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

    if (payload && payload.ollama === "unreachable") {
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
    let payload = null;
    try {
      payload = await response.json();
    } catch (error) {
      appendMessage("Backend noto‘g‘ri javob qaytardi.", "system");
      return;
    }

    if (!response.ok) {
      const detail = payload?.detail?.message || "Noma’lum xatolik yuz berdi.";
      appendMessage(detail, "system");
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

loadHealthStatus();
loadModelStatus();
