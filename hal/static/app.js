/* HAL Web UI — vanilla JS, no build step */
(function () {
  "use strict";

  // ── Config ──────────────────────────────────────────────────────
  const API_BASE = "";  // same origin
  const HEALTH_POLL_MS = 60000;
  const SESSION_KEY = "hal_sessions";
  const ACTIVE_KEY = "hal_active_session";
  const TOKEN_KEY = "hal_web_token";
  const MAX_SESSIONS = 50;  // prune oldest beyond this limit

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
  const $loginOverlay = document.getElementById("login-overlay");
  const $tokenInput  = document.getElementById("token-input");
  const $loginBtn    = document.getElementById("login-btn");
  const $loginError  = document.getElementById("login-error");
  const $signOutBtn  = document.getElementById("sign-out-btn");

  // ── State ───────────────────────────────────────────────────────
  let sessions = loadSessions();     // { id, created, messages[] }
  let activeId = localStorage.getItem(ACTIVE_KEY);
  let sending  = false;
  let _token   = localStorage.getItem(TOKEN_KEY) || "";

  // ── Marked config ───────────────────────────────────────────────
  // CDN libraries are optional — UI degrades to plain text if unavailable.
  var _marked = typeof marked !== "undefined" ? marked : null;
  var _hljs = typeof hljs !== "undefined" ? hljs : null;
  if (_marked) { _marked.setOptions({ breaks: true, gfm: true }); }

  // ── Session persistence ─────────────────────────────────────────
  function loadSessions() {
    try {
      return JSON.parse(localStorage.getItem(SESSION_KEY)) || [];
    } catch (e) { return []; }
  }

  function saveSessions() {
    try {
      localStorage.setItem(SESSION_KEY, JSON.stringify(sessions));
    } catch (e) {
      // Quota exceeded — drop oldest sessions until it fits
      while (sessions.length > 1) {
        sessions.pop();
        try {
          localStorage.setItem(SESSION_KEY, JSON.stringify(sessions));
          return;
        } catch (_) { /* keep trimming */ }
      }
    }
  }

  function pruneSessions() {
    if (sessions.length > MAX_SESSIONS) {
      sessions = sessions.slice(0, MAX_SESSIONS);
    }
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
    pruneSessions();
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

  function deleteSession(id) {
    sessions = sessions.filter(function (s) { return s.id !== id; });
    if (activeId === id) {
      activeId = sessions.length ? sessions[0].id : null;
      if (!activeId) {
        createSession();
        return;
      }
      localStorage.setItem(ACTIVE_KEY, activeId);
    }
    saveSessions();
    renderSessions();
    renderMessages();
  }

  // ── Rendering ───────────────────────────────────────────────────
  function sessionLabel(sess, index) {
    // Show first user message as preview, or fall back to "Session N"
    var firstMsg = sess.messages.find(function (m) { return m.role === "user"; });
    if (firstMsg && firstMsg.content) {
      var preview = firstMsg.content.slice(0, 32);
      return preview + (firstMsg.content.length > 32 ? "…" : "");
    }
    return "Session " + (sessions.length - index);
  }

  function renderSessions() {
    $sessionList.innerHTML = "";
    sessions.forEach(function (s, i) {
      var el = document.createElement("div");
      el.className = "session-item" + (s.id === activeId ? " active" : "");

      var labelRow = document.createElement("div");
      labelRow.className = "session-label-row";

      var label = document.createElement("span");
      label.textContent = sessionLabel(s, i);
      labelRow.appendChild(label);

      var exportBtn = document.createElement("button");
      exportBtn.className = "session-export";
      exportBtn.title = "Export session";
      exportBtn.textContent = "\u21E9";
      exportBtn.addEventListener("click", function (e) {
        e.stopPropagation();
        exportSession(s.id);
      });
      labelRow.appendChild(exportBtn);

      var delBtn = document.createElement("button");
      delBtn.className = "session-delete";
      delBtn.title = "Delete session";
      delBtn.textContent = "\u00d7";
      delBtn.addEventListener("click", function (e) {
        e.stopPropagation();
        deleteSession(s.id);
      });
      labelRow.appendChild(delBtn);
      el.appendChild(labelRow);

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

    if (sess.messages.length === 0) {
      showWelcome();
    } else {
      sess.messages.forEach(function (msg) {
        appendMessage(msg.role, msg.content, msg.intent, false, msg.steps);
      });
    }
    scrollToBottom();
  }

  var WELCOME_PROMPTS = [
    { icon: "\uD83D\uDCCA", text: "how\u2019s the lab?" },
    { icon: "\uD83D\uDD12", text: "check security events" },
    { icon: "\uD83D\uDCBE", text: "show disk and memory usage" },
    { icon: "\uD83D\uDD0D", text: "what services are running?" },
  ];

  function showWelcome() {
    var card = document.createElement("div");
    card.className = "welcome-card";
    card.innerHTML =
      '<div class="welcome-logo">HAL</div>' +
      '<p class="welcome-hint">Homelab AI assistant. Ask anything about your infrastructure.</p>' +
      '<div class="welcome-prompts"></div>';
    var grid = card.querySelector(".welcome-prompts");
    WELCOME_PROMPTS.forEach(function (p) {
      var btn = document.createElement("button");
      btn.className = "welcome-prompt-btn";
      btn.innerHTML = '<span class="welcome-prompt-icon">' + p.icon + '</span> ' + _escapeHtml(p.text);
      btn.addEventListener("click", function () {
        $input.value = p.text;
        $input.focus();
        sendMessage(p.text);
        $input.value = "";
      });
      grid.appendChild(btn);
    });
    $messages.appendChild(card);
  }

  function appendMessage(role, content, intent, animate, steps) {
    var wrapper = document.createElement("div");
    wrapper.className = "message message-" + role;

    // ── Step cards (tool calls, KB/metrics seeds) ─────────────────
    if (role === "hal" && steps && steps.length > 0) {
      var stepsContainer = document.createElement("div");
      stepsContainer.className = "steps-container";

      steps.forEach(function (step) {
        if (step.type === "kb_seed") {
          var tag = document.createElement("div");
          tag.className = "step-seed";
          tag.innerHTML = '<span class="step-seed-icon">&#x1F4DA;</span> searched knowledge base <span class="step-seed-detail">' + step.chunks + ' chunks</span>';
          stepsContainer.appendChild(tag);
        } else if (step.type === "metrics_seed") {
          var tag2 = document.createElement("div");
          tag2.className = "step-seed";
          tag2.innerHTML = '<span class="step-seed-icon">&#x1F4CA;</span> pulled live metrics';
          stepsContainer.appendChild(tag2);
        } else if (step.type === "tool_call") {
          var card = document.createElement("details");
          card.className = "step-tool-card";

          var summary = document.createElement("summary");
          summary.className = "step-tool-summary";
          var argsPreview = "";
          if (step.args) {
            var keys = Object.keys(step.args);
            if (keys.length > 0) {
              var firstVal = String(step.args[keys[0]]);
              if (firstVal.length > 50) firstVal = firstVal.slice(0, 50) + "…";
              argsPreview = ' <span class="step-tool-arg">' + _escapeHtml(keys[0]) + '=' + _escapeHtml(firstVal) + '</span>';
            }
          }
          summary.innerHTML = '<span class="step-tool-icon">&#x26A1;</span> <span class="step-tool-name">' + _escapeHtml(step.name) + '</span>' + argsPreview;
          card.appendChild(summary);

          var detail = document.createElement("div");
          detail.className = "step-tool-detail";
          if (step.args) {
            var argsBlock = document.createElement("pre");
            argsBlock.className = "step-tool-args";
            argsBlock.textContent = JSON.stringify(step.args, null, 2);
            detail.appendChild(argsBlock);
          }
          if (step.result) {
            var resultBlock = document.createElement("pre");
            resultBlock.className = "step-tool-result";
            resultBlock.textContent = step.result;
            detail.appendChild(resultBlock);
          }
          card.appendChild(detail);
          stepsContainer.appendChild(card);
        }
      });

      wrapper.appendChild(stepsContainer);
    }

    var body = document.createElement("div");
    body.className = "message-content";

    if (role === "hal") {
      if (_marked) {
        body.innerHTML = _marked.parse(content);
        // Apply syntax highlighting and copy buttons to code blocks
        body.querySelectorAll("pre").forEach(function (pre) {
          var codeEl = pre.querySelector("code");
          if (_hljs && codeEl) _hljs.highlightElement(codeEl);

          // Copy button
          pre.style.position = "relative";
          var copyBtn = document.createElement("button");
          copyBtn.className = "copy-btn";
          copyBtn.textContent = "copy";
          copyBtn.addEventListener("click", function () {
            var text = (codeEl || pre).textContent;
            navigator.clipboard.writeText(text).then(function () {
              copyBtn.textContent = "copied!";
              setTimeout(function () { copyBtn.textContent = "copy"; }, 1500);
            });
          });
          pre.appendChild(copyBtn);
        });
      } else {
        body.textContent = content;
      }
    } else {
      body.textContent = content;
    }

    wrapper.appendChild(body);

    // Badge row: intent + step count
    if (role === "hal") {
      var badgeRow = document.createElement("div");
      badgeRow.className = "badge-row";

      if (intent) {
        var badge = document.createElement("span");
        badge.className = "intent-badge";
        badge.textContent = intent;
        badgeRow.appendChild(badge);
      }

      var toolSteps = (steps || []).filter(function (s) { return s.type === "tool_call"; });
      if (toolSteps.length > 0) {
        var stepBadge = document.createElement("span");
        stepBadge.className = "intent-badge step-count-badge";
        stepBadge.textContent = toolSteps.length + " tool call" + (toolSteps.length > 1 ? "s" : "");
        badgeRow.appendChild(stepBadge);
      }

      if (badgeRow.children.length > 0) {
        wrapper.appendChild(badgeRow);
      }
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
      var fetchHeaders = { "Content-Type": "application/json" };
      if (_token) { fetchHeaders["Authorization"] = "Bearer " + _token; }
      var res = await fetch(API_BASE + "/chat", {
        method: "POST",
        headers: fetchHeaders,
        body: JSON.stringify({ message: text, session_id: sess.id }),
      });

      hideThinking();

      if (!res.ok) {
        if (res.status === 401) {
          hideThinking();
          // Remove the optimistic user message
          sess.messages.pop();
          saveSessions();
          showLogin("Token rejected — please re-authenticate.");
          sending = false;
          $sendBtn.disabled = false;
          return;
        }
        var errText = "";
        try {
          var errBody = await res.json();
          errText = errBody.detail || res.statusText;
        } catch (_) {
          errText = res.statusText;
        }
        appendMessage("hal", "**Error:** " + errText, null, true, null);
        sess.messages.push({ role: "hal", content: "**Error:** " + errText, intent: null, steps: [] });
      } else {
        var data = await res.json();
        // Update session ID if server assigned a different one
        if (data.session_id && data.session_id !== sess.id) {
          sess.id = data.session_id;
          activeId = sess.id;
          localStorage.setItem(ACTIVE_KEY, sess.id);
        }
        appendMessage("hal", data.response, data.intent, true, data.steps);
        sess.messages.push({ role: "hal", content: data.response, intent: data.intent, steps: data.steps || [] });
      }
    } catch (err) {
      hideThinking();
      var msg = "**Connection error:** " + err.message;
      appendMessage("hal", msg, null, true, null);
      sess.messages.push({ role: "hal", content: msg, intent: null, steps: [] });
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
  function _escapeHtml(str) {
    var div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  function shortId(id) {
    if (!id) return "";
    // "web-1709654321000" -> "web-...1000"
    if (id.length > 16) return id.slice(0, 4) + "..." + id.slice(-4);
    return id;
  }

  function exportSession(id) {
    var sess = sessions.find(function (s) { return s.id === id; });
    if (!sess) return;
    var lines = [];
    lines.push("# HAL Session — " + new Date(sess.created).toLocaleString());
    lines.push("");
    sess.messages.forEach(function (msg) {
      if (msg.role === "user") {
        lines.push("> " + msg.content.replace(/\n/g, "\n> "));
      } else {
        lines.push(msg.content);
      }
      lines.push("");
    });
    var blob = new Blob([lines.join("\n")], { type: "text/markdown" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "hal-session-" + id + ".md";
    a.click();
    URL.revokeObjectURL(a.href);
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

  // Keyboard shortcuts
  document.addEventListener("keydown", function (e) {
    var mod = e.ctrlKey || e.metaKey;
    if (mod && e.key.toLowerCase() === "n") {
      e.preventDefault();
      createSession();
      closeSidebar();
      $input.focus();
    } else if (mod && e.key.toLowerCase() === "k") {
      e.preventDefault();
      $input.focus();
    } else if (e.key === "Escape") {
      closeSidebar();
    }
  });

  // ── Login / auth ────────────────────────────────────────────────
  function showLogin(msg) {
    $loginOverlay.style.display = "flex";
    $loginError.textContent = msg || "";
    $tokenInput.value = "";
    $tokenInput.focus();
  }

  function hideLogin() {
    $loginOverlay.style.display = "none";
    $loginError.textContent = "";
  }

  function handleLogin() {
    var val = $tokenInput.value.trim();
    if (!val) { $loginError.textContent = "Token cannot be empty."; return; }
    _token = val;
    localStorage.setItem(TOKEN_KEY, _token);
    hideLogin();
    $input.focus();
  }

  $loginBtn.addEventListener("click", handleLogin);
  $tokenInput.addEventListener("keydown", function (e) {
    if (e.key === "Enter") { e.preventDefault(); handleLogin(); }
  });

  function signOut() {
    _token = "";
    localStorage.removeItem(TOKEN_KEY);
    showLogin("");
  }

  $signOutBtn.addEventListener("click", signOut);

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

    // Probe auth requirement — if /chat returns 401 without a token, show login
    if (!_token) {
      fetch(API_BASE + "/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: "ping", session_id: "auth-probe" }),
      }).then(function (res) {
        if (res.status === 401) showLogin("");
        else $input.focus();
      }).catch(function () {
        $input.focus();
      });
    } else {
      $input.focus();
    }
  })();

})();
