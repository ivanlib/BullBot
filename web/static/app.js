// BullBot chat UI logic: send messages, render Markdown answers with citations,
// show a loading indicator, handle errors, and manage a per-tab session.

const messagesEl = document.getElementById("messages");
const form = document.getElementById("composer");
const input = document.getElementById("input");
const sendBtn = document.getElementById("send");
const newChatBtn = document.getElementById("new-chat");

const demoBadge = document.getElementById("demo-badge");

// One session id per browser tab; the server threads Bedrock context from it.
let sessionId = crypto.randomUUID();
let busy = false;

// Check mode on load and reveal the Demo Mode badge if offline mode is active.
async function checkMode() {
  try {
    const resp = await fetch("/api/health");
    const data = await resp.json();
    if (data.demo_mode) {
      demoBadge.hidden = false;
      const welcome = messagesEl.querySelector(".welcome p");
      if (welcome) {
        welcome.innerHTML +=
          "<br><em>Running in offline Demo Mode: answers come from prepared examples, " +
          "not live Amazon Bedrock. Safety checks here are simplified and not equivalent " +
          "to Bedrock Guardrails.</em>";
      }
    }
  } catch (_) {
    /* health check is best-effort; ignore failures */
  }
}

// Configure Markdown rendering (GitHub-style line breaks, tables on by default).
marked.setOptions({ breaks: true, gfm: true });

// Append a message row and return its bubble element.
function addRow(role, { html, text, cssClass } = {}) {
  // Clear the welcome panel on first real message.
  const welcome = messagesEl.querySelector(".welcome");
  if (welcome) welcome.remove();

  const row = document.createElement("div");
  row.className = `row ${role}`;

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = role === "user" ? "🧑" : "🐂";

  const bubble = document.createElement("div");
  bubble.className = "bubble" + (cssClass ? ` ${cssClass}` : "");
  if (html !== undefined) bubble.innerHTML = html;
  else bubble.textContent = text;

  row.append(avatar, bubble);
  messagesEl.appendChild(row);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return bubble;
}

// Render model Markdown safely: Markdown -> HTML -> sanitize before insertion.
function renderMarkdown(mdText) {
  const rawHtml = marked.parse(mdText);
  return DOMPurify.sanitize(rawHtml);
}

// Show an animated typing indicator; returns the row to replace later.
function addTyping() {
  const bubble = addRow("bot");
  bubble.innerHTML =
    '<span class="typing"><span></span><span></span><span></span></span>';
  return bubble.parentElement; // the row
}

// Send the user's message to the backend and render the response.
async function sendMessage(text) {
  if (busy || !text.trim()) return;
  busy = true;
  sendBtn.disabled = true;

  addRow("user", { text });
  input.value = "";
  autoGrow();
  const typingRow = addTyping();

  try {
    const resp = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, session_id: sessionId }),
    });

    const data = await resp.json().catch(() => ({}));
    typingRow.remove();

    if (!resp.ok) {
      const detail = data.detail || "Something went wrong. Please try again.";
      addRow("bot", { text: detail, cssClass: "error" });
      return;
    }

    sessionId = data.session_id || sessionId;
    if (data.blocked) {
      addRow("bot", { text: data.answer, cssClass: "blocked" });
    } else {
      addRow("bot", { html: renderMarkdown(data.answer) });
    }
  } catch (err) {
    typingRow.remove();
    addRow("bot", {
      text: "Could not reach BullBot. Check that the server is running and try again.",
      cssClass: "error",
    });
  } finally {
    busy = false;
    sendBtn.disabled = false;
    input.focus();
  }
}

// Start a fresh conversation: new session, clear transcript, tell the server.
async function newChat() {
  const old = sessionId;
  sessionId = crypto.randomUUID();
  messagesEl.innerHTML = `
    <div class="welcome">
      <h2>How can I help with your Sac State questions?</h2>
      <p>Ask about transfer credits, financial aid, or degree planning. Answers are
         grounded in official campus documents with citations.</p>
      <div class="suggestions">
        <button class="chip">Do my community college credits transfer to the CS major?</button>
        <button class="chip">What are the Cal Grant B renewal requirements?</button>
        <button class="chip">How can I add a Data Science minor without delaying graduation?</button>
      </div>
    </div>`;
  wireChips();
  fetch("/api/reset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: "reset", session_id: old }),
  }).catch(() => {});
}

// Grow the textarea with content, up to the CSS max-height.
function autoGrow() {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 160) + "px";
}

// Make suggestion chips fill and send.
function wireChips() {
  document.querySelectorAll(".chip").forEach((chip) => {
    chip.addEventListener("click", () => sendMessage(chip.textContent.trim()));
  });
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  sendMessage(input.value);
});

// Enter sends; Shift+Enter inserts a newline.
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage(input.value);
  }
});
input.addEventListener("input", autoGrow);
newChatBtn.addEventListener("click", newChat);

wireChips();
checkMode();
input.focus();
