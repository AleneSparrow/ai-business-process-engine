(function () {
  "use strict";

  const script = document.currentScript;
  if (!script) return;
  const businessId = script.dataset.businessId;
  if (!businessId) {
    console.error("AI Process Chat: data-business-id is required");
    return;
  }

  const scriptUrl = new URL(script.src, window.location.href);
  const apiBase = (script.dataset.apiBase || scriptUrl.origin).replace(/\/$/, "");
  const storageKey = `ai-process-chat:${apiBase}:${businessId}`;
  const pendingKey = `${storageKey}:pending-create`;
  const endpoint = `${apiBase}/api/v1/public/businesses/${encodeURIComponent(businessId)}`;
  let conversationToken = window.localStorage.getItem(storageKey);
  let pendingCreate = window.sessionStorage.getItem(pendingKey);
  let config = null;
  let busy = false;

  const stylesheet = document.createElement("link");
  stylesheet.rel = "stylesheet";
  stylesheet.href = `${scriptUrl.origin}/widget/widget.css`;
  document.head.append(stylesheet);

  const root = document.createElement("section");
  root.className = "aibp-chat";
  root.setAttribute("aria-label", "Business chat");

  const launcher = document.createElement("button");
  launcher.type = "button";
  launcher.className = "aibp-chat__launcher";
  launcher.textContent = "Chat";
  launcher.setAttribute("aria-expanded", "false");
  launcher.setAttribute("aria-controls", "aibp-chat-panel");

  const panel = document.createElement("div");
  panel.id = "aibp-chat-panel";
  panel.className = "aibp-chat__panel";
  panel.hidden = true;
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-modal", "false");

  const header = document.createElement("header");
  header.className = "aibp-chat__header";
  const title = document.createElement("h2");
  title.textContent = "Chat";
  const close = document.createElement("button");
  close.type = "button";
  close.className = "aibp-chat__close";
  close.textContent = "Close";
  close.setAttribute("aria-label", "Close chat");
  header.append(title, close);

  const history = document.createElement("div");
  history.className = "aibp-chat__history";
  history.setAttribute("role", "log");
  history.setAttribute("aria-live", "polite");
  history.setAttribute("aria-relevant", "additions");

  const status = document.createElement("p");
  status.className = "aibp-chat__status";
  status.setAttribute("role", "status");

  const form = document.createElement("form");
  form.className = "aibp-chat__form";
  const label = document.createElement("label");
  label.className = "aibp-chat__label";
  label.htmlFor = "aibp-chat-input";
  label.textContent = "Message";
  const input = document.createElement("textarea");
  input.id = "aibp-chat-input";
  input.rows = 2;
  input.maxLength = 2000;
  input.required = true;
  input.placeholder = "Type your message";
  const send = document.createElement("button");
  send.type = "submit";
  send.textContent = "Send";
  form.append(label, input, send);
  panel.append(header, history, status, form);
  root.append(launcher, panel);
  document.body.append(root);

  function setBusy(value) {
    busy = value;
    input.disabled = value;
    send.disabled = value;
    if (value) status.textContent = "Sending…";
    else if (status.textContent === "Sending…") status.textContent = "";
  }

  function showError(message) {
    status.textContent = message;
    status.classList.add("aibp-chat__status--error");
  }

  function appendMessage(role, text) {
    const message = document.createElement("p");
    message.className = `aibp-chat__message aibp-chat__message--${role}`;
    message.textContent = text;
    history.append(message);
    history.scrollTop = history.scrollHeight;
  }

  function renderConversation(data) {
    history.replaceChildren();
    if (!data.messages.length && config) {
      appendMessage("assistant", config.welcome_message);
    }
    data.messages.forEach((message) => appendMessage(message.role, message.text));
    if (data.requires_human) status.textContent = "A team member will review this conversation.";
  }

  function messageId() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return window.crypto.randomUUID();
    }
    return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  }

  function conversationTokenValue() {
    if (!window.crypto || typeof window.crypto.getRandomValues !== "function") {
      throw new Error("This browser cannot create a secure chat session.");
    }
    const bytes = new Uint8Array(32);
    window.crypto.getRandomValues(bytes);
    let binary = "";
    bytes.forEach((value) => { binary += String.fromCharCode(value); });
    return window.btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }

  async function request(path, options) {
    const response = await window.fetch(`${endpoint}${path}`, options);
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      const message = data && data.error && data.error.message;
      throw new Error(message || "Chat request failed. Please try again.");
    }
    return data;
  }

  async function restore() {
    if (!conversationToken) {
      history.replaceChildren();
      if (config) appendMessage("assistant", config.welcome_message);
      return;
    }
    try {
      const data = await request(`/conversations/${encodeURIComponent(conversationToken)}`, {
        method: "GET",
        headers: { Accept: "application/json" }
      });
      renderConversation(data);
      window.sessionStorage.removeItem(pendingKey);
      pendingCreate = null;
    } catch (error) {
      if (pendingCreate) {
        try {
          const payload = JSON.parse(pendingCreate);
          const data = await request("/conversations", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
          });
          renderConversation(data);
          window.sessionStorage.removeItem(pendingKey);
          pendingCreate = null;
          return;
        } catch (retryError) {
          showError(retryError instanceof Error ? retryError.message : "Conversation could not be restored.");
          return;
        }
      }
      window.localStorage.removeItem(storageKey);
      conversationToken = null;
      showError(error instanceof Error ? error.message : "Conversation could not be restored.");
    }
  }

  async function sendMessage(text) {
    if (pendingCreate) {
      const retried = await request("/conversations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: pendingCreate
      });
      window.sessionStorage.removeItem(pendingKey);
      pendingCreate = null;
      renderConversation(retried);
      return;
    }
    const message = { message: text, external_message_id: messageId() };
    let data;
    if (conversationToken) {
      data = await request(`/conversations/${encodeURIComponent(conversationToken)}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(message)
      });
    } else {
      conversationToken = conversationTokenValue();
      window.localStorage.setItem(storageKey, conversationToken);
      const createPayload = { ...message, conversation_token: conversationToken };
      pendingCreate = JSON.stringify(createPayload);
      window.sessionStorage.setItem(pendingKey, pendingCreate);
      data = await request("/conversations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: pendingCreate
      });
      window.sessionStorage.removeItem(pendingKey);
      pendingCreate = null;
    }
    renderConversation(data);
  }

  launcher.addEventListener("click", async function () {
    panel.hidden = !panel.hidden;
    launcher.setAttribute("aria-expanded", String(!panel.hidden));
    if (!panel.hidden) {
      await restore();
      input.focus();
    }
  });
  close.addEventListener("click", function () {
    panel.hidden = true;
    launcher.setAttribute("aria-expanded", "false");
    launcher.focus();
  });
  input.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });
  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    const text = input.value.trim();
    if (!text || busy) return;
    status.classList.remove("aibp-chat__status--error");
    setBusy(true);
    try {
      await sendMessage(text);
      input.value = "";
    } catch (error) {
      showError(error instanceof Error ? error.message : "Message could not be sent.");
    } finally {
      setBusy(false);
      input.focus();
    }
  });

  request("/chat-config", { method: "GET", headers: { Accept: "application/json" } })
    .then(function (value) {
      config = value;
      title.textContent = value.chat_title;
      launcher.hidden = !value.enabled;
    })
    .catch(function () {
      launcher.hidden = true;
    });
}());
