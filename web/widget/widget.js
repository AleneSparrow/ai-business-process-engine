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
  const titleRow = document.createElement("div");
  titleRow.className = "aibp-chat__title-row";
  const title = document.createElement("h2");
  title.textContent = "Chat";
  const close = document.createElement("button");
  close.type = "button";
  close.className = "aibp-chat__close";
  close.textContent = "Close";
  close.setAttribute("aria-label", "Close chat");
  titleRow.append(title, close);
  // Persistent AI-disclosure badge -- stays visible in the header for the
  // entire session, not just a one-time greeting line that scrolls away.
  // Populated from Business DNA (chat_widget.ai_disclosure_text); hidden
  // entirely when a business hasn't configured one.
  const disclosureBadge = document.createElement("p");
  disclosureBadge.className = "aibp-chat__disclosure";
  disclosureBadge.hidden = true;
  header.append(titleRow, disclosureBadge);

  const history = document.createElement("div");
  history.className = "aibp-chat__history";
  history.setAttribute("role", "log");
  history.setAttribute("aria-live", "polite");
  history.setAttribute("aria-relevant", "additions");

  // Clickable slot-picker: rendered whenever the backend has an active,
  // unexpired slot proposal for this conversation (see /commercial's
  // proposed_slots). Clicking a button sends its 1-based option number as
  // an ordinary chat message -- DeterministicSlotPreferenceInterpreter
  // already accepts a bare "1"/"2"/"3" reply, so no new backend contract is
  // needed beyond exposing the slot list itself.
  const slotOptions = document.createElement("div");
  slotOptions.className = "aibp-chat__slots";
  slotOptions.hidden = true;
  slotOptions.setAttribute("aria-label", "Available times");

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
  panel.append(header, history, slotOptions, status, form);
  root.append(launcher, panel);
  document.body.append(root);

  function setBusy(value) {
    busy = value;
    input.disabled = value;
    send.disabled = value;
    slotOptions.querySelectorAll("button").forEach((button) => { button.disabled = value; });
    history.querySelectorAll(".aibp-chat__service-button").forEach((button) => { button.disabled = value; });
  }

  // Animated "typing" bubble instead of a text status line -- shown in the
  // message history itself (where a reply is about to appear) rather than a
  // caption easy to miss below the input. Only one instance ever exists;
  // renderConversation()'s history.replaceChildren() removes it implicitly
  // whenever a real response lands, so hideTyping() just needs to null out
  // the stale reference rather than guarantee removal itself.
  let typingBubble = null;
  function showTyping() {
    if (typingBubble) return;
    typingBubble = document.createElement("div");
    typingBubble.className = "aibp-chat__message aibp-chat__message--assistant aibp-chat__typing";
    typingBubble.setAttribute("aria-label", "Assistant is typing");
    typingBubble.innerHTML = "<span></span><span></span><span></span>";
    history.append(typingBubble);
    history.scrollTop = history.scrollHeight;
  }
  function hideTyping() {
    if (typingBubble) {
      typingBubble.remove();
      typingBubble = null;
    }
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
    return message;
  }

  // Quick-reply service chips: shown once, right under the opening welcome
  // message, so a first-time visitor can tap what they need instead of
  // typing it out. A tap just sends the service's own name as an ordinary
  // chat message (same trick as the slot-picker buttons) -- the AI intent
  // extractor already resolves free text against these same catalog
  // id/name/aliases, so this needs zero new interpretation logic. They
  // live inside `history` (not a persistent bar like slotOptions) because
  // they're a one-time opening move, not a recurring prompt: once any
  // message exists, renderConversation()'s replaceChildren() drops them
  // for good, the same way the welcome message itself scrolls away.
  function appendServiceOptions(services) {
    if (!services || !services.length) return;
    const row = document.createElement("div");
    row.className = "aibp-chat__services";
    row.setAttribute("aria-label", "Quick options");
    services.forEach(function (service) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "aibp-chat__service-button";
      button.textContent = service.name;
      button.addEventListener("click", function () {
        submitMessage(service.name);
      });
      row.append(button);
    });
    history.append(row);
    history.scrollTop = history.scrollHeight;
  }

  function renderConversation(data) {
    history.replaceChildren();
    if (!data.messages.length && config) {
      appendMessage("assistant", config.welcome_message);
      appendServiceOptions(config.services);
    }
    data.messages.forEach((message) => appendMessage(message.role, message.text));
    if (data.requires_human) status.textContent = "A team member will review this conversation.";
  }

  function formatSlotLabel(slot) {
    try {
      return new Intl.DateTimeFormat(undefined, {
        timeZone: slot.timezone,
        weekday: "short",
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit"
      }).format(new Date(slot.start_at));
    } catch (error) {
      return slot.start_at;
    }
  }

  function renderSlotOptions(slots) {
    slotOptions.replaceChildren();
    if (!slots || !slots.length) {
      slotOptions.hidden = true;
      return;
    }
    slots.forEach(function (slot) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "aibp-chat__slot-button";
      button.textContent = formatSlotLabel(slot);
      button.addEventListener("click", function () {
        submitMessage(String(slot.option), { focusInput: false });
      });
      slotOptions.append(button);
    });
    slotOptions.hidden = false;
  }

  async function refreshCommercial() {
    if (!conversationToken) {
      renderSlotOptions([]);
      return;
    }
    try {
      const data = await request(`/conversations/${encodeURIComponent(conversationToken)}/commercial`, {
        method: "GET",
        headers: { Accept: "application/json" }
      });
      renderSlotOptions(data.proposed_slots);
    } catch (error) {
      // Non-fatal -- the conversation itself already rendered successfully;
      // losing the slot buttons just means the customer types "1"/"2"/"3"
      // instead of clicking, same as before this feature existed.
      renderSlotOptions([]);
    }
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
      if (config) {
        appendMessage("assistant", config.welcome_message);
        appendServiceOptions(config.services);
      }
      renderSlotOptions([]);
      return;
    }
    try {
      const data = await request(`/conversations/${encodeURIComponent(conversationToken)}`, {
        method: "GET",
        headers: { Accept: "application/json" }
      });
      renderConversation(data);
      await refreshCommercial();
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
          await refreshCommercial();
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
  async function submitMessage(text, options) {
    const focusInput = !options || options.focusInput !== false;
    if (!text || busy) return;
    status.classList.remove("aibp-chat__status--error");
    setBusy(true);
    // Optimistic echo + typing bubble: a real reply overwrites both via
    // renderConversation()'s history.replaceChildren(), so nothing needs
    // reconciling on the success path. On failure the echo is retracted
    // (it may not have actually reached the business) while the typed text
    // stays in the input for a retry.
    const optimistic = appendMessage("customer", text);
    showTyping();
    try {
      await sendMessage(text);
      input.value = "";
      await refreshCommercial();
    } catch (error) {
      optimistic.remove();
      showError(error instanceof Error ? error.message : "Message could not be sent.");
    } finally {
      hideTyping();
      setBusy(false);
      if (focusInput) input.focus();
    }
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    submitMessage(input.value.trim());
  });

  request("/chat-config", { method: "GET", headers: { Accept: "application/json" } })
    .then(function (value) {
      config = value;
      title.textContent = value.chat_title;
      launcher.hidden = !value.enabled;
      if (value.ai_disclosure_text) {
        disclosureBadge.textContent = value.ai_disclosure_text;
        disclosureBadge.hidden = false;
      }
    })
    .catch(function () {
      launcher.hidden = true;
    });
}());
