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

  // ── Slash commands (for autocomplete) ────────────────────────────
  var SLASH_COMMANDS = [
    { cmd: "/help", desc: "show available commands" },
    { cmd: "/health", desc: "live service health check" },
    { cmd: "/search", desc: "search the knowledge base" },
    { cmd: "/remember", desc: "save a fact to memory" },
    { cmd: "/postmortem", desc: "incident post-mortem analysis" },
    { cmd: "/audit", desc: "show recent audit log" },
    { cmd: "/kb", desc: "knowledge base stats" },
    { cmd: "/sessions", desc: "list all sessions" },
    { cmd: "/new", desc: "start a new session" },
    { cmd: "/clear", desc: "clear the screen" },
  ];

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
  const $sessionSearch = document.getElementById("session-search");
  const $healthPanel = document.getElementById("health-panel");
  const $healthPanelBody = document.getElementById("health-panel-body");
  const $healthPanelClose = document.getElementById("health-panel-close");
  const $healthPanelOverlay = document.getElementById("health-panel-overlay");
  const $kbBtn            = document.getElementById("kb-btn");
  const $kbPanel          = document.getElementById("kb-panel");
  const $kbPanelBody      = document.getElementById("kb-panel-body");
  const $kbPanelClose     = document.getElementById("kb-panel-close");
  const $kbPanelOverlay   = document.getElementById("kb-panel-overlay");
  const $kbSearchInput    = document.getElementById("kb-search-input");
  const $kbSearchBtn      = document.getElementById("kb-search-btn");
  const $kbActiveFilter   = document.getElementById("kb-active-filter");

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
    // Custom label takes priority
    if (sess.label) return sess.label;
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

    // Filter by search text
    var searchTerm = ($sessionSearch.value || "").toLowerCase().trim();
    var filtered = sessions;
    if (searchTerm) {
      filtered = sessions.filter(function (s, i) {
        return sessionLabel(s, i).toLowerCase().indexOf(searchTerm) !== -1;
      });
    }

    filtered.forEach(function (s) {
      var i = sessions.indexOf(s);  // real index for label fallback
      var el = document.createElement("div");
      el.className = "session-item" + (s.id === activeId ? " active" : "");

      var labelRow = document.createElement("div");
      labelRow.className = "session-label-row";

      var label = document.createElement("span");
      label.className = "session-label-text";
      label.textContent = sessionLabel(s, i);
      label.addEventListener("dblclick", function (e) {
        e.stopPropagation();
        startEditLabel(s, label, labelRow);
      });
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

  function startEditLabel(sess, labelSpan, row) {
    var input = document.createElement("input");
    input.type = "text";
    input.className = "session-label-edit";
    input.value = sess.label || "";
    input.placeholder = "session name…";

    // Replace the label span with the input
    row.replaceChild(input, labelSpan);
    input.focus();
    input.select();

    function commit() {
      var val = input.value.trim();
      if (val) {
        sess.label = val;
      } else {
        delete sess.label;  // revert to auto-generated
      }
      saveSessions();
      renderSessions();
    }

    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") { e.preventDefault(); commit(); }
      if (e.key === "Escape") { e.preventDefault(); renderSessions(); }
    });
    input.addEventListener("blur", commit);
  }

  function renderMessages() {
    $messages.innerHTML = "";
    var sess = getActive();
    if (!sess) return;

    if (sess.messages.length === 0) {
      showWelcome();
    } else {
      sess.messages.forEach(function (msg, i) {
        appendMessage(msg.role, msg.content, msg.intent, false, msg.steps, i);
      });
      // Mark last HAL message for regenerate button visibility
      var halMsgs = $messages.querySelectorAll(".message-hal");
      if (halMsgs.length > 0) {
        halMsgs[halMsgs.length - 1].classList.add("last");
      }
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

  function appendMessage(role, content, intent, animate, steps, msgIndex) {
    var wrapper = document.createElement("div");
    wrapper.className = "message message-" + role;
    if (typeof msgIndex === "number") {
      wrapper.setAttribute("data-msg-index", msgIndex);
    }

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

    // Edit button for user messages
    if (role === "user") {
      var editBtn = document.createElement("button");
      editBtn.className = "msg-action-btn msg-edit-btn";
      editBtn.title = "Edit & resend";
      editBtn.textContent = "\u270E";
      editBtn.addEventListener("click", function () {
        var idx = parseInt(wrapper.getAttribute("data-msg-index"), 10);
        if (!isNaN(idx)) startEditMessage(idx);
      });
      wrapper.appendChild(editBtn);
    }

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

      // Regenerate button (visible only on the last HAL message via CSS .last class)
      var regenBtn = document.createElement("button");
      regenBtn.className = "msg-action-btn msg-regen-btn";
      regenBtn.title = "Regenerate response";
      regenBtn.textContent = "\u21BB";
      regenBtn.addEventListener("click", function () {
        regenerateLastResponse();
      });
      wrapper.appendChild(regenBtn);
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

  // ── Message actions (regenerate, edit) ──────────────────────────
  function _updateLastHalMarker() {
    // Move the .last class to the newest HAL message so only its
    // regenerate button is visible.
    var all = $messages.querySelectorAll(".message-hal");
    all.forEach(function (el) { el.classList.remove("last"); });
    if (all.length > 0) all[all.length - 1].classList.add("last");
  }

  function regenerateLastResponse() {
    if (sending) return;
    var sess = getActive();
    if (!sess || sess.messages.length < 2) return;

    // Find the last HAL message — it should be the last element
    var lastMsg = sess.messages[sess.messages.length - 1];
    if (lastMsg.role !== "hal") return;

    // Pop the HAL response
    sess.messages.pop();
    // The last message should now be the user message that triggered it
    var userMsg = sess.messages[sess.messages.length - 1];
    if (!userMsg || userMsg.role !== "user") return;

    // Pop the user message too — sendMessage will re-add it
    var userText = userMsg.content;
    sess.messages.pop();
    saveSessions();
    renderMessages();

    // Re-send the same user query
    sendMessage(userText);
  }

  function startEditMessage(msgIndex) {
    if (sending) return;
    var sess = getActive();
    if (!sess || msgIndex >= sess.messages.length) return;

    var msg = sess.messages[msgIndex];
    if (msg.role !== "user") return;

    // Find the DOM wrapper for this message
    var wrapper = $messages.querySelector('[data-msg-index="' + msgIndex + '"]');
    if (!wrapper) return;

    // Replace the message body with an editable textarea
    var body = wrapper.querySelector(".message-content");
    if (!body) return;

    var textarea = document.createElement("textarea");
    textarea.className = "msg-edit-textarea";
    textarea.value = msg.content;
    textarea.rows = Math.min(msg.content.split("\n").length + 1, 6);

    var btnRow = document.createElement("div");
    btnRow.className = "msg-edit-actions";

    var saveBtn = document.createElement("button");
    saveBtn.className = "msg-edit-save";
    saveBtn.textContent = "Send";
    btnRow.appendChild(saveBtn);

    var cancelBtn = document.createElement("button");
    cancelBtn.className = "msg-edit-cancel";
    cancelBtn.textContent = "Cancel";
    btnRow.appendChild(cancelBtn);

    body.innerHTML = "";
    body.appendChild(textarea);
    body.appendChild(btnRow);
    textarea.focus();

    // Hide the edit button while editing
    var editBtn = wrapper.querySelector(".msg-edit-btn");
    if (editBtn) editBtn.style.display = "none";

    function commit() {
      var newText = textarea.value.trim();
      if (!newText) { cancel(); return; }

      // Truncate history: remove this message and everything after it
      sess.messages = sess.messages.slice(0, msgIndex);
      saveSessions();
      renderMessages();

      // Send the edited text as a new message
      sendMessage(newText);
    }

    function cancel() {
      renderMessages();
    }

    saveBtn.addEventListener("click", commit);
    cancelBtn.addEventListener("click", cancel);
    textarea.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); commit(); }
      if (e.key === "Escape") { e.preventDefault(); cancel(); }
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
    appendMessage("user", text, null, true, null, sess.messages.length - 1);
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
        appendMessage("hal", "**Error:** " + errText, null, true, null, sess.messages.length);
        sess.messages.push({ role: "hal", content: "**Error:** " + errText, intent: null, steps: [] });
      } else {
        var data = await res.json();
        // Update session ID if server assigned a different one
        if (data.session_id && data.session_id !== sess.id) {
          sess.id = data.session_id;
          activeId = sess.id;
          localStorage.setItem(ACTIVE_KEY, sess.id);
        }
        appendMessage("hal", data.response, data.intent, true, data.steps, sess.messages.length);
        sess.messages.push({ role: "hal", content: data.response, intent: data.intent, steps: data.steps || [] });
      }
    } catch (err) {
      hideThinking();
      var msg = "**Connection error:** " + err.message;
      appendMessage("hal", msg, null, true, null, sess.messages.length);
      sess.messages.push({ role: "hal", content: msg, intent: null, steps: [] });
    }

    saveSessions();
    renderSessions();
    _updateLastHalMarker();
    sending = false;
    $sendBtn.disabled = false;
    $input.focus();
  }

  function _updateMetricBar(barId, valId, pct) {
    var bar = document.getElementById(barId);
    var val = document.getElementById(valId);
    if (!bar || !val) return;
    if (pct === null || pct === undefined) {
      bar.style.width = "0";
      bar.className = "metric-fill";
      val.textContent = "—";
      return;
    }
    bar.style.width = Math.min(pct, 100) + "%";
    bar.className = "metric-fill" + (pct >= 85 ? " crit" : pct >= 60 ? " warn" : "");
    val.textContent = Math.round(pct) + "%";
  }

  async function checkHealth() {
    // Try detailed endpoint first (auth required), fall back to basic /health.
    var detailed = false;
    try {
      var headers = {};
      if (_token) headers["Authorization"] = "Bearer " + _token;
      var res = await fetch(API_BASE + "/health/detail", { headers: headers });
      if (res.ok) {
        var data = await res.json();
        detailed = true;
        // Derive overall status from components
        var statuses = (data.components || []).map(function (c) { return c.status; });
        var status = "ok";
        if (statuses.indexOf("down") !== -1) status = "down";
        else if (statuses.indexOf("degraded") !== -1) status = "degraded";
        $healthDot.className = "health-dot " + status;
        $healthDot.title = "Status: " + status;
        $healthText.textContent = "status: " + status;
        $healthText.style.color =
          status === "ok" ? "var(--green)" :
          status === "degraded" ? "var(--amber)" : "var(--red)";
        // Update metric bars
        var m = data.metrics || {};
        _updateMetricBar("bar-cpu", "val-cpu", m.cpu_pct);
        _updateMetricBar("bar-mem", "val-mem", m.mem_pct);
        _updateMetricBar("bar-gpu", "val-gpu", m.gpu_vram_pct);
        // Stash detail data for the health panel (step 3)
        window._halHealthDetail = data;
      }
    } catch (_) { /* fall through to basic check */ }
    if (!detailed) {
      try {
        var res2 = await fetch(API_BASE + "/health");
        var data2 = await res2.json();
        var s = data2.status || "down";
        $healthDot.className = "health-dot " + s;
        $healthDot.title = "Status: " + s;
        $healthText.textContent = "status: " + s;
        $healthText.style.color =
          s === "ok" ? "var(--green)" :
          s === "degraded" ? "var(--amber)" : "var(--red)";
      } catch (_2) {
        $healthDot.className = "health-dot down";
        $healthDot.title = "Unreachable";
        $healthText.textContent = "status: unreachable";
        $healthText.style.color = "var(--red)";
      }
    }
  }

  // ── Health panel (slide-out) ────────────────────────────────
  var _METRIC_LABELS = {
    cpu_pct: "CPU",
    mem_pct: "Memory",
    disk_root_pct: "Disk /",
    disk_docker_pct: "Disk /docker",
    disk_data_pct: "Disk /data",
    swap_pct: "Swap",
    load1: "Load (1m)",
    gpu_vram_pct: "GPU VRAM",
    gpu_temp_c: "GPU Temp",
  };

  function openHealthPanel() {
    renderHealthPanel();
    $healthPanel.classList.add("open");
    $healthPanelOverlay.classList.add("visible");
  }

  function closeHealthPanel() {
    $healthPanel.classList.remove("open");
    $healthPanelOverlay.classList.remove("visible");
  }

  function renderHealthPanel() {
    var data = window._halHealthDetail;
    if (!data) {
      $healthPanelBody.innerHTML = '<p style="color:var(--text-muted);font-size:13px">No health data yet. Waiting for next poll…</p>';
      return;
    }

    var html = '';

    // Components section
    if (data.components && data.components.length > 0) {
      html += '<div class="hp-section"><div class="hp-section-title">Components</div>';
      data.components.forEach(function (c) {
        html += '<div class="hp-comp">' +
          '<span class="hp-status-dot ' + _escapeHtml(c.status) + '"></span>' +
          '<span class="hp-comp-name">' + _escapeHtml(c.name) + '</span>' +
          '<span class="hp-comp-detail" title="' + _escapeHtml(c.detail) + '">' + _escapeHtml(c.detail) + '</span>' +
          '<span class="hp-comp-latency">' + Math.round(c.latency_ms) + 'ms</span>' +
          '</div>';
      });
      html += '</div>';
    }

    // Metrics section
    var m = data.metrics || {};
    var metricKeys = Object.keys(_METRIC_LABELS);
    var hasMetrics = metricKeys.some(function (k) { return m[k] !== null && m[k] !== undefined; });
    if (hasMetrics) {
      html += '<div class="hp-section"><div class="hp-section-title">Resources</div>';
      metricKeys.forEach(function (key) {
        var val = m[key];
        var label = _METRIC_LABELS[key];
        var isTemp = key === "gpu_temp_c";
        var isLoad = key === "load1";
        var displayVal = "—";
        var pct = 0;
        var colorClass = "";

        if (val !== null && val !== undefined) {
          if (isTemp) {
            displayVal = val + "°C";
            pct = Math.min((val / 90) * 100, 100);  // 90°C = full bar
            colorClass = val >= 80 ? "crit" : val >= 65 ? "warn" : "";
          } else if (isLoad) {
            displayVal = val.toFixed(2);
            // Assume 16 threads; load 16 = 100%
            pct = Math.min((val / 16) * 100, 100);
            colorClass = val >= 12 ? "crit" : val >= 8 ? "warn" : "";
          } else {
            displayVal = Math.round(val) + "%";
            pct = Math.min(val, 100);
            colorClass = val >= 85 ? "crit" : val >= 60 ? "warn" : "";
          }
        }

        html += '<div class="hp-metric">' +
          '<span class="hp-metric-label">' + _escapeHtml(label) + '</span>' +
          '<div class="hp-metric-track"><div class="hp-metric-fill ' + colorClass + '" style="width:' + pct + '%"></div></div>' +
          '<span class="hp-metric-val">' + displayVal + '</span>' +
          '</div>';
      });
      html += '</div>';
    }

    if (!html) {
      html = '<p style="color:var(--text-muted);font-size:13px">Health data unavailable.</p>';
    }
    $healthPanelBody.innerHTML = html;
  }

  $healthDot.addEventListener("click", function () {
    if ($healthPanel.classList.contains("open")) closeHealthPanel();
    else openHealthPanel();
  });
  $healthDot.style.cursor = "pointer";
  $healthPanelClose.addEventListener("click", closeHealthPanel);
  $healthPanelOverlay.addEventListener("click", closeHealthPanel);

  // ── KB Browser panel (slide-out) ────────────────────────────
  var _kbActiveCategory = null;
  var _kbCategoriesLoaded = false;

  function openKbPanel() {
    closeHealthPanel();
    $kbPanel.classList.add("open");
    $kbPanelOverlay.classList.add("visible");
    if (!_kbCategoriesLoaded) loadKbCategories();
    $kbSearchInput.focus();
  }

  function closeKbPanel() {
    $kbPanel.classList.remove("open");
    $kbPanelOverlay.classList.remove("visible");
  }

  function loadKbCategories() {
    $kbPanelBody.innerHTML = '<div class="kb-loading">Loading categories…</div>';
    fetch(API_BASE + "/kb/categories", { headers: _authHeaders() })
      .then(function (res) {
        if (res.status === 401) { showLogin("Session expired"); throw new Error("auth"); }
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then(function (data) {
        _kbCategoriesLoaded = true;
        renderKbCategories(data);
      })
      .catch(function (err) {
        if (err.message === "auth") return;
        $kbPanelBody.innerHTML = '<div class="kb-empty">Failed to load categories.</div>';
      });
  }

  function renderKbCategories(categories) {
    if (!categories || categories.length === 0) {
      $kbPanelBody.innerHTML = '<div class="kb-empty">No categories found.</div>';
      return;
    }
    var html = '';
    categories.forEach(function (cat) {
      html += '<div class="kb-cat" data-category="' + _escapeHtml(cat.category) + '">' +
        '<span class="kb-cat-name">' + _escapeHtml(cat.category) + '</span>' +
        '<span class="kb-cat-count">' + cat.count + '</span>' +
        '</div>';
    });
    $kbPanelBody.innerHTML = html;

    // Attach click handlers for category filtering
    var catEls = $kbPanelBody.querySelectorAll(".kb-cat");
    catEls.forEach(function (el) {
      el.addEventListener("click", function () {
        setKbCategoryFilter(el.getAttribute("data-category"));
      });
    });
  }

  function setKbCategoryFilter(category) {
    _kbActiveCategory = category;
    $kbActiveFilter.style.display = "flex";
    $kbActiveFilter.innerHTML =
      '<span>Category:</span>' +
      '<span class="kb-filter-tag">' + _escapeHtml(category) + '</span>' +
      '<button class="kb-filter-clear" title="Clear filter">&times;</button>';
    $kbActiveFilter.querySelector(".kb-filter-clear").addEventListener("click", clearKbCategoryFilter);

    // If there's already search text, re-run search with filter
    var q = $kbSearchInput.value.trim();
    if (q) searchKb(q);
  }

  function clearKbCategoryFilter() {
    _kbActiveCategory = null;
    $kbActiveFilter.style.display = "none";
    $kbActiveFilter.innerHTML = "";

    // If there's search text, re-run search without filter
    var q = $kbSearchInput.value.trim();
    if (q) {
      searchKb(q);
    } else {
      // Show categories again
      loadKbCategories();
    }
  }

  function searchKb(query) {
    $kbPanelBody.innerHTML = '<div class="kb-loading">Searching…</div>';
    var url = API_BASE + "/kb/search?q=" + encodeURIComponent(query);
    if (_kbActiveCategory) url += "&category=" + encodeURIComponent(_kbActiveCategory);
    fetch(url, { headers: _authHeaders() })
      .then(function (res) {
        if (res.status === 401) { showLogin("Session expired"); throw new Error("auth"); }
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then(function (data) {
        renderKbResults(data, query);
      })
      .catch(function (err) {
        if (err.message === "auth") return;
        $kbPanelBody.innerHTML = '<div class="kb-empty">Search failed.</div>';
      });
  }

  function renderKbResults(results, query) {
    if (!results || results.length === 0) {
      $kbPanelBody.innerHTML = '<div class="kb-empty">No results for "' + _escapeHtml(query) + '"</div>';
      return;
    }
    var html = '';
    results.forEach(function (r) {
      var score = r.score !== null && r.score !== undefined ? r.score.toFixed(3) : "—";
      var scoreClass = r.score >= 0.85 ? "high" : r.score >= 0.75 ? "mid" : "low";
      var content = r.content || "";
      if (content.length > 400) content = content.substring(0, 400) + "…";
      var file = r.file || "";
      var category = r.category || "";
      var tier = r.doc_tier || "";

      html += '<div class="kb-result">' +
        '<div class="kb-result-header">' +
          '<span class="kb-result-score ' + scoreClass + '">' + score + '</span>' +
          (tier ? '<span class="kb-result-tier">' + _escapeHtml(tier) + '</span>' : '') +
          (file ? '<span class="kb-result-file" title="' + _escapeHtml(file) + '">' + _escapeHtml(file) + '</span>' : '') +
        '</div>' +
        '<div class="kb-result-content">' + _escapeHtml(content) + '</div>' +
        (category ? '<span class="kb-result-category" data-category="' + _escapeHtml(category) + '">' + _escapeHtml(category) + '</span>' : '') +
        '</div>';
    });
    $kbPanelBody.innerHTML = html;

    // Clicking a category badge sets the filter
    var catBadges = $kbPanelBody.querySelectorAll(".kb-result-category");
    catBadges.forEach(function (el) {
      el.addEventListener("click", function () {
        setKbCategoryFilter(el.getAttribute("data-category"));
      });
    });
  }

  // KB panel event listeners
  $kbBtn.addEventListener("click", function () {
    if ($kbPanel.classList.contains("open")) closeKbPanel();
    else openKbPanel();
  });
  $kbPanelClose.addEventListener("click", closeKbPanel);
  $kbPanelOverlay.addEventListener("click", closeKbPanel);
  $kbSearchBtn.addEventListener("click", function () {
    var q = $kbSearchInput.value.trim();
    if (q) searchKb(q);
  });
  $kbSearchInput.addEventListener("keydown", function (e) {
    if (e.key === "Enter") {
      e.preventDefault();
      var q = $kbSearchInput.value.trim();
      if (q) searchKb(q);
      else {
        // Empty search → show categories
        clearKbCategoryFilter();
        loadKbCategories();
      }
    }
  });

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

  // ── Slash command autocomplete ──────────────────────────────────
  var $slashMenu = null;
  var _slashIndex = -1;

  function buildSlashMenu() {
    var el = document.createElement("div");
    el.className = "slash-menu";
    el.style.display = "none";
    document.querySelector(".input-wrapper").appendChild(el);
    return el;
  }

  function showSlashMenu(filter) {
    if (!$slashMenu) $slashMenu = buildSlashMenu();
    var q = filter.toLowerCase();
    var matches = SLASH_COMMANDS.filter(function (c) {
      return c.cmd.indexOf(q) === 0;
    });
    if (matches.length === 0) { hideSlashMenu(); return; }
    _slashIndex = 0;
    $slashMenu.innerHTML = "";
    matches.forEach(function (c, i) {
      var row = document.createElement("div");
      row.className = "slash-menu-item" + (i === 0 ? " active" : "");
      row.innerHTML = '<span class="slash-cmd">' + _escapeHtml(c.cmd) + '</span> <span class="slash-desc">' + _escapeHtml(c.desc) + '</span>';
      row.addEventListener("mousedown", function (e) {
        e.preventDefault();
        pickSlash(c);
      });
      $slashMenu.appendChild(row);
    });
    $slashMenu.style.display = "block";
  }

  function hideSlashMenu() {
    if ($slashMenu) { $slashMenu.style.display = "none"; }
    _slashIndex = -1;
  }

  function pickSlash(c) {
    if (c.cmd === "/new") {
      createSession();
      $input.value = "";
    } else if (c.cmd === "/clear") {
      var sess = getActive();
      if (sess) { $messages.innerHTML = ""; }
      $input.value = "";
    } else {
      $input.value = c.cmd + " ";
    }
    hideSlashMenu();
    $input.focus();
    autoResize();
  }

  function navigateSlash(dir) {
    if (!$slashMenu || $slashMenu.style.display === "none") return false;
    var items = $slashMenu.querySelectorAll(".slash-menu-item");
    if (items.length === 0) return false;
    items[_slashIndex].classList.remove("active");
    _slashIndex = (_slashIndex + dir + items.length) % items.length;
    items[_slashIndex].classList.add("active");
    items[_slashIndex].scrollIntoView({ block: "nearest" });
    return true;
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
    // Slash menu navigation
    if ($slashMenu && $slashMenu.style.display !== "none") {
      if (e.key === "ArrowDown") { e.preventDefault(); navigateSlash(1); return; }
      if (e.key === "ArrowUp") { e.preventDefault(); navigateSlash(-1); return; }
      if (e.key === "Tab" || (e.key === "Enter" && !e.shiftKey)) {
        var items = $slashMenu.querySelectorAll(".slash-menu-item");
        if (_slashIndex >= 0 && items.length > 0) {
          e.preventDefault();
          var cmdText = items[_slashIndex].querySelector(".slash-cmd").textContent;
          var match = SLASH_COMMANDS.find(function (c) { return c.cmd === cmdText; });
          if (match) pickSlash(match);
          return;
        }
      }
      if (e.key === "Escape") { e.preventDefault(); hideSlashMenu(); return; }
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      var text = $input.value;
      $input.value = "";
      autoResize();
      hideSlashMenu();
      sendMessage(text);
    }
  });

  $input.addEventListener("input", function () {
    autoResize();
    // Slash autocomplete trigger
    var val = $input.value;
    if (val.indexOf("/") === 0 && val.indexOf("\n") === -1) {
      showSlashMenu(val);
    } else {
      hideSlashMenu();
    }
  });

  $newSession.addEventListener("click", function () {
    createSession();
    closeSidebar();
    $input.focus();
  });

  $sessionSearch.addEventListener("input", function () {
    renderSessions();
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
      closeHealthPanel();
      closeKbPanel();
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
