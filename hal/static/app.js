/* HAL Web UI — vanilla JS, no build step */
(function () {
  "use strict";

  // ── Config ──────────────────────────────────────────────────────
  const API_BASE = "";  // same origin
  const HEALTH_POLL_MS = 60_000;
  const SESSION_KEY = "hal_sessions";
  const ACTIVE_KEY = "hal_active_session";

  // ── DOM refs ────────────────────────────────────────────────────
  const $messages    = document.getElementById("messages");
  const $input       = document.getElementById("message-input");
  const $sendBtn     = document.getElementById("send-btn");
  const $chatArea    = document.getElementById("chat-area");
  const $sessionList = document.getElementById("session-list");
  const $newSession  = document.getElementById("new-session-btn");
  const $healthDot   = document.getElementById("health-dot");
  const $healthText  = document.getElementById("health-text");
  const $sidebar     = document.getElementById("sidebar");
  const $overlay     = document.getElementById("sidebar-overlay");
  const $hamburger   = document.getElementById("hamburger");
  const $mobileSess  = document.getElementById("mobile-session");

  // ── State ───────────────────────────────────────────────────────
  let sessions = loadSessions();     // { id, created, messages[] }
  let activeId = localStorage.getItem(ACTIVE_KEY);
  let sending  = false;

  // ── Marked config ───────────────────────────────────────────────
  // NOTE: highlight callback was removed in marked v5+. Syntax highlighting
  // is handled post-render via hljs.highlightElement() in appendMessage().
  marked.setOptions({ breaks: true, gfm: true });

  // ── Session persistence ─────────────────────────────────────────
  function loadSessions() {
    try {
      return JSON.parse(localStorage.getItem(SESSION_KEY)) || [];
    } catch { return []; }
  }

  function saveSessions() {
    localStorage.setItem(SESSION_KEY, JSON.stringify(sessions));
  }

  function getActive() {
    return sessions.find(function (s) { return s.id === activeId; });
  }

  function makeSessionId() {
    return "web-" + Date.now();
  }

  function createSession() {
    var id = makeSessionId();
    var sess = { id: id, created: Date.now(), messages: [] };
    sessions.unshift(sess);
    activeId = id;
    localStorage.setItem(ACTIVE_KEY, id);
    saveSessions();
    renderSessions();
    renderMessages();
    return sess;
  }

  function switchSession(id) {
    activeId = id;
    localStorage.setItem(ACTIVE_KEY, id);
    renderSessions();
    renderMessages();
    closeSidebar();
  }

  // ── Rendering ───────────────────────────────────────────────────
  function renderSessions() {
    $sessionList.innerHTML = "";
    sessions.forEach(function (s) {
      var el = document.createElement("div");
      el.className = "session-item" + (s.id === activeId ? " active" : "");

      var label = document.createElement("span");
      label.textContent = s.id;
      el.appendChild(label);

      var time = document.createElement("span");
      time.className = "session-time";
      time.textContent = relativeTime(s.created);
      el.appendChild(time);

      el.addEventListener("click", function () { switchSession(s.id); });
      $sessionList.appendChild(el);
    });

    // Update mobile session indicator
    $mobileSess.textContent = activeId ? shortId(activeId) : "";
  }

  function renderMessages() {
    $messages.innerHTML = "";
    var sess = getActive();
    if (!sess) return;

    sess.messages.forEach(function (msg) {
      appendMessage(msg.role, msg.content, msg.intent, false);
    });
    scrollToBottom();
  }

  function appendMessage(role, content, intent, animate) {
    var wrapper = document.createElement("div");
    wrapper.className = "message message-" + role;

    var body = document.createElement("div");
    body.className = "message-content";

    if (role === "hal") {
      body.innerHTML = marked.parse(content);
      // Apply syntax highlighting to any code blocks
      body.querySelectorAll("pre code").forEach(function (block) {
        hljs.highlightElement(block);
      });
    } else {
      body.textContent = content;
    }

    wrapper.appendChild(body);

    if (intent && role === "hal") {
      var badge = document.createElement("span");
      badge.className = "intent-badge";
      badge.textContent = intent;
      wrapper.appendChild(badge);
    }

    $messages.appendChild(wrapper);
    if (animate !== false) scrollToBottom();
  }

  function showThinking() {
    var el = document.createElement("div");
    el.id = "thinking";
    el.className = "thinking";
    el.innerHTML =
      '<div class="thinking-dots"><span></span><span></span><span></span></div>' +
      '<span>thinking\u2026</span>';
    $messages.appendChild(el);
    scrollToBottom();
  }

  function hideThinking() {
    var el = document.getElementById("thinking");
    if (el) el.remove();
  }

  function scrollToBottom() {
    requestAnimationFrame(function () {
      $chatArea.scrollTop = $chatArea.scrollHeight;
    });
  }

  // ── API calls ───────────────────────────────────────────────────
  async function sendMessage(text) {
    if (sending || !text.trim()) return;
    sending = true;
    $sendBtn.disabled = true;

    var sess = getActive() || createSession();

    // Add user message
    sess.messages.push({ role: "user", content: text });
    saveSessions();
    appendMessage("user", text, null, true);
    showThinking();

    try {
      var res = await fetch(API_BASE + "/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, session_id: sess.id }),
      });

      hideThinking();

      if (!res.ok) {
        var errText = "";
        try {
          var errBody = await res.json();
          errText = errBody.detail || res.statusText;
        } catch (_) {
          errText = res.statusText;
        }
        appendMessage("hal", "**Error:** " + errText, null, true);
        sess.messages.push({ role: "hal", content: "**Error:** " + errText, intent: null });
      } else {
        var data = await res.json();
        // Update session ID if server assigned a different one
        if (data.session_id && data.session_id !== sess.id) {
          sess.id = data.session_id;
          activeId = sess.id;
          localStorage.setItem(ACTIVE_KEY, sess.id);
        }
        appendMessage("hal", data.response, data.intent, true);
        sess.messages.push({ role: "hal", content: data.response, intent: data.intent });
      }
    } catch (err) {
      hideThinking();
      var msg = "**Connection error:** " + err.message;
      appendMessage("hal", msg, null, true);
      sess.messages.push({ role: "hal", content: msg, intent: null });
    }

    saveSessions();
    renderSessions();
    sending = false;
    $sendBtn.disabled = false;
    $input.focus();
  }

  async function checkHealth() {
    try {
      var res = await fetch(API_BASE + "/health");
      var data = await res.json();
      var status = data.status || "down";
      $healthDot.className = "health-dot " + status;
      $healthDot.title = "Status: " + status;
      $healthText.textContent = "status: " + status;
      $healthText.style.color =
        status === "ok" ? "var(--green)" :
        status === "degraded" ? "var(--amber)" : "var(--red)";
    } catch (_) {
      $healthDot.className = "health-dot down";
      $healthDot.title = "Unreachable";
      $healthText.textContent = "status: unreachable";
      $healthText.style.color = "var(--red)";
    }
  }

  // ── Sidebar (mobile) ───────────────────────────────────────────
  function openSidebar() {
    $sidebar.classList.add("open");
    $overlay.classList.add("visible");
  }

  function closeSidebar() {
    $sidebar.classList.remove("open");
    $overlay.classList.remove("visible");
  }

  // ── Utilities ───────────────────────────────────────────────────
  function shortId(id) {
    if (!id) return "";
    // "web-1709654321000" -> "web-...1000"
    if (id.length > 16) return id.slice(0, 4) + "..." + id.slice(-4);
    return id;
  }

  function relativeTime(ts) {
    var diff = Date.now() - ts;
    var sec = Math.floor(diff / 1000);
    if (sec < 60) return "just now";
    var min = Math.floor(sec / 60);
    if (min < 60) return min + "m ago";
    var hr = Math.floor(min / 60);
    if (hr < 24) return hr + "h ago";
    var d = Math.floor(hr / 24);
    if (d === 1) return "yesterday";
    return d + "d ago";
  }

  // ── Auto-resize textarea ───────────────────────────────────────
  function autoResize() {
    $input.style.height = "auto";
    var maxH = 150;  // matches CSS max-height
    $input.style.height = Math.min($input.scrollHeight, maxH) + "px";
  }

  // ── Event listeners ─────────────────────────────────────────────
  $sendBtn.addEventListener("click", function () {
    var text = $input.value;
    $input.value = "";
    autoResize();
    sendMessage(text);
  });

  $input.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      var text = $input.value;
      $input.value = "";
      autoResize();
      sendMessage(text);
    }
  });

  $input.addEventListener("input", autoResize);

  $newSession.addEventListener("click", function () {
    createSession();
    closeSidebar();
    $input.focus();
  });

  $hamburger.addEventListener("click", function () {
    if ($sidebar.classList.contains("open")) closeSidebar();
    else openSidebar();
  });

  $overlay.addEventListener("click", closeSidebar);

  // ── Init ────────────────────────────────────────────────────────
  (function init() {
    // Ensure at least one session exists
    if (sessions.length === 0 || !getActive()) {
      createSession();
    }
    renderSessions();
    renderMessages();
    checkHealth();
    setInterval(checkHealth, HEALTH_POLL_MS);
    $input.focus();
  })();

})();
