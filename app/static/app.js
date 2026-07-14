const healthStatus = document.getElementById("health-status");
const chatForm = document.getElementById("chat-form");
const messageInput = document.getElementById("message-input");
const chatHistory = document.getElementById("chat-history");

async function loadHealthStatus() {
  try {
    const response = await fetch("/health");
    const payload = await response.json();
    healthStatus.textContent = `${payload.status} / db: ${payload.database}`;
  } catch (error) {
    healthStatus.textContent = "unreachable";
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

chatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const content = messageInput.value.trim();

  if (!content) {
    return;
  }

  appendMessage(content, "user");
  appendMessage(
    "Local model hali ulanmagan. Keyingi bosqichda Ollama integratsiyasi qo‘shiladi.",
    "system"
  );
  messageInput.value = "";
});

loadHealthStatus();
