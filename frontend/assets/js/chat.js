/* ============================================================
   DINING CONCIERGE — chat.js
   Handles: session, API calls, message rendering, UI state
============================================================ */

/* ----------------------------------------------------------
   SDK INITIALIZATION
   apigClient.js defines apigClientFactory but does NOT create
   the sdk instance — the original project did this inline in
   index.html. We do it here so chat.js is self-contained.
   Pass {} to use the API endpoint already set in apigClient.js.
---------------------------------------------------------- */
var sdk = apigClientFactory.newClient({});

(function () {
  'use strict';

  /* ----------------------------------------------------------
     SESSION ID
     Persisted in localStorage so Lex keeps conversation state
     across page refreshes.
  ---------------------------------------------------------- */
  var SESSION_KEY = 'dc_session_id';

  function getSessionId() {
    var id = localStorage.getItem(SESSION_KEY);
    if (!id) {
      id = 'sess-' + Date.now() + '-' + Math.random().toString(36).slice(2);
      localStorage.setItem(SESSION_KEY, id);
    }
    return id;
  }

  function newSessionId() {
    var id = 'sess-' + Date.now() + '-' + Math.random().toString(36).slice(2);
    localStorage.setItem(SESSION_KEY, id);
    return id;
  }

  var sessionId = getSessionId();

  /* ----------------------------------------------------------
     DOM REFERENCES
  ---------------------------------------------------------- */
  var $area   = document.getElementById('messagesArea');
  var $input  = document.getElementById('msgInput');
  var $send   = document.getElementById('sendBtn');
  var $clear  = document.getElementById('clearBtn');
  var $chips  = document.getElementById('chipsRail');

  /* tracked separately so we can re-assign after clear */
  var $empty  = document.getElementById('emptyState');
  var hasMessages = false;

  /* ----------------------------------------------------------
     AUTO-RESIZE TEXTAREA
  ---------------------------------------------------------- */
  $input.addEventListener('input', function () {
    this.style.height = 'auto';
    this.style.height = Math.min(this.scrollHeight, 130) + 'px';
  });

  /* ----------------------------------------------------------
     API — calls API Gateway → LF0 → Lex
  ---------------------------------------------------------- */
  function callChatbotApi(message) {
    return sdk.chatbotPost(
      {},                          /* params   */
      {
        messages: [{
          type: 'unstructured',
          unstructured: {
            id: sessionId,         /* Lex session identifier */
            text: message,
            timestamp: new Date().toISOString()
          }
        }]
      },
      {}                           /* additionalParams */
    );
  }

  /* ----------------------------------------------------------
     UTILITIES
  ---------------------------------------------------------- */
  function escapeHtml(str) {
    return String(str)
      .replace(/&/g,  '&amp;')
      .replace(/</g,  '&lt;')
      .replace(/>/g,  '&gt;')
      .replace(/"/g,  '&quot;')
      .replace(/\n/g, '<br>');
  }

  function formatTime(date) {
    var h  = date.getHours();
    var m  = date.getMinutes();
    var ap = h >= 12 ? 'PM' : 'AM';
    h = h % 12 || 12;
    return h + ':' + (m < 10 ? '0' : '') + m + ' ' + ap;
  }

  function scrollBottom() {
    $area.scrollTop = $area.scrollHeight;
  }

  /* ----------------------------------------------------------
     EMPTY STATE MANAGEMENT
  ---------------------------------------------------------- */
  function hideEmptyState() {
    if (!hasMessages) {
      hasMessages = true;
      if ($empty) { $empty.style.display = 'none'; }
    }
  }

  function buildEmptyState() {
    var el = document.createElement('div');
    el.className = 'empty-state';
    el.id = 'emptyState';
    el.innerHTML = [
      '<div class="empty-glyph">&#10022;</div>',
      '<div class="empty-ornament">&middot; &middot; &middot; &middot; &middot;</div>',
      '<div class="empty-heading">Where would you like to dine tonight?</div>',
      '<div class="empty-body">',
        'Tell me a cuisine, neighbourhood, or occasion<br>',
        'and I\'ll find the perfect table',
      '</div>',
      '<div class="empty-prompts">',
        '<button class="empty-btn" data-msg="I need restaurant suggestions in Manhattan">Find a restaurant</button>',
        '<button class="empty-btn" data-msg="Hello! What can you do?">What can you do?</button>',
        '<button class="empty-btn" data-msg="Best sushi spots in Manhattan">Sushi in Manhattan</button>',
      '</div>'
    ].join('');
    return el;
  }

  /* ----------------------------------------------------------
     RENDER — user message
  ---------------------------------------------------------- */
  function addUserMessage(text) {
    hideEmptyState();

    var el = document.createElement('div');
    el.className = 'msg-row user';
    el.innerHTML = [
      '<div class="msg-avatar">&#128100;</div>',
      '<div class="msg-content">',
        '<div class="bubble bubble-user">', escapeHtml(text), '</div>',
        '<div class="msg-time">', formatTime(new Date()), '</div>',
      '</div>'
    ].join('');

    $area.appendChild(el);
    scrollBottom();
  }

  /* ----------------------------------------------------------
     RENDER — typing indicator
  ---------------------------------------------------------- */
  function showTyping() {
    hideEmptyState();

    var el = document.createElement('div');
    el.className = 'typing-row';
    el.id = 'typingRow';
    el.innerHTML = [
      '<div class="msg-avatar">&#127869;</div>',
      '<div>',
        '<div class="msg-sender">Concierge</div>',
        '<div class="typing-bubble">',
          '<div class="td"></div>',
          '<div class="td"></div>',
          '<div class="td"></div>',
        '</div>',
      '</div>'
    ].join('');

    $area.appendChild(el);
    scrollBottom();
  }

  function removeTyping() {
    var el = document.getElementById('typingRow');
    if (el) { el.remove(); }
  }

  /* ----------------------------------------------------------
     RENDER — bot message
     Detects confirmation replies and appends a styled card.
  ---------------------------------------------------------- */
  var CONFIRM_PHRASES = [
    "you're all set",
    "all set",
    "expect my suggestions",
    "will notify",
    "suggestions shortly",
    "sent to your email"
  ];

  function isConfirmation(text) {
    var lower = text.toLowerCase();
    return CONFIRM_PHRASES.some(function (p) { return lower.indexOf(p) !== -1; });
  }

  function buildConfirmCard() {
    return [
      '<div class="confirm-card">',
        '<div class="confirm-card-title">&#10022;&nbsp; Request Received</div>',
        'Restaurant recommendations will be sent to your email shortly. ',
        'Check your inbox in a few minutes.',
      '</div>'
    ].join('');
  }

  function addBotMessage(text) {
    var el = document.createElement('div');
    el.className = 'msg-row';

    var extras = isConfirmation(text) ? buildConfirmCard() : '';

    el.innerHTML = [
      '<div class="msg-avatar">&#127869;</div>',
      '<div class="msg-content">',
        '<div class="msg-sender">Concierge</div>',
        '<div class="bubble bubble-bot">', escapeHtml(text), '</div>',
        extras,
        '<div class="msg-time">', formatTime(new Date()), '</div>',
      '</div>'
    ].join('');

    $area.appendChild(el);
    scrollBottom();
  }

  /* ----------------------------------------------------------
     SEND MESSAGE
  ---------------------------------------------------------- */
  var sending = false;

  /* Minimum ms to show typing indicator (feels natural) */
  var MIN_TYPING_MS = 750;

  function sendMessage(overrideText) {
    var text = (overrideText !== undefined ? overrideText : $input.value).trim();
    if (!text || sending) { return; }

    sending = true;
    $send.disabled = true;
    $input.value = '';
    $input.style.height = 'auto';

    addUserMessage(text);

    var typingStart = Date.now();

    setTimeout(showTyping, 120);

    callChatbotApi(text)
      .then(function (res) {
        var elapsed = Date.now() - typingStart;
        var wait    = Math.max(0, MIN_TYPING_MS - elapsed);

        setTimeout(function () {
          removeTyping();

          // ── Parse response data ─────────────────────────────────────────
          // axios uses Content-Type to decide whether to auto-parse JSON.
          // If the Lambda/API Gateway returns Content-Type: text/plain or
          // omits it, res.data arrives as a raw string — parse it manually.
          var data = res.data;
          console.log('[DC] raw res.data type:', typeof data);
          console.log('[DC] raw res.data:', data);

          if (typeof data === 'string') {
            try {
              data = JSON.parse(data);
              console.log('[DC] parsed from string:', data);
            } catch (e) {
              console.error('[DC] JSON.parse failed:', e, data);
              addBotMessage('Received an unreadable response. Please try again.');
              sending = false;
              $send.disabled = false;
              return;
            }
          }

          // ── Extract messages ────────────────────────────────────────────
          if (data && data.messages && data.messages.length > 0) {
            data.messages.forEach(function (m) {
              if (m.type === 'unstructured' && m.unstructured && m.unstructured.text) {
                addBotMessage(m.unstructured.text);
              }
            });
          } else {
            console.warn('[DC] Unexpected response shape:', data);
            addBotMessage('Something went wrong. Please try again.');
          }

          sending = false;
          $send.disabled = false;
        }, wait);
      })
      .catch(function (err) {
        console.error('[DiningConcierge] API error:', err);
        console.error('[DiningConcierge] err.response:', err.response);
        console.error('[DiningConcierge] err.message:', err.message);

        setTimeout(function () {
          removeTyping();
          addBotMessage("Oops \u2014 couldn\u2019t connect. Please check your network and try again.");
          sending = false;
          $send.disabled = false;
        }, 400);
      });
  }

  /* ----------------------------------------------------------
     CLEAR CONVERSATION
  ---------------------------------------------------------- */
  function clearChat() {
    $area.innerHTML = '';
    hasMessages = false;

    $empty = buildEmptyState();
    $area.appendChild($empty);

    /* Start a brand-new Lex session */
    sessionId = newSessionId();
  }

  /* ----------------------------------------------------------
     EVENT LISTENERS
  ---------------------------------------------------------- */
  /* Send button */
  $send.addEventListener('click', function () { sendMessage(); });

  /* Enter to send, Shift+Enter for newline */
  $input.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  /* Cuisine chip clicks */
  $chips.addEventListener('click', function (e) {
    var chip = e.target.closest('.chip');
    if (chip && chip.dataset.msg) { sendMessage(chip.dataset.msg); }
  });

  /* Empty-state prompt buttons */
  $area.addEventListener('click', function (e) {
    var btn = e.target.closest('.empty-btn');
    if (btn && btn.dataset.msg) { sendMessage(btn.dataset.msg); }
  });

  /* Clear chat */
  $clear.addEventListener('click', clearChat);

  /* ----------------------------------------------------------
     INITIAL GREETING
     Shown after a short delay on first load.
  ---------------------------------------------------------- */
  setTimeout(function () {
    addBotMessage(
      "Hi there! How can I help you today?"
    );
  }, 650);

})();