/* ============================================================
   DINING CONCIERGE — chat.js
============================================================ */

/* SDK init — must be global, before the IIFE */
var sdk = apigClientFactory.newClient({});

(function () {
  'use strict';

  /* ── SESSION ─────────────────────────────────────────────── */
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

  /* ── DOM REFS ────────────────────────────────────────────── */
  var $area  = document.getElementById('messagesArea');
  var $input = document.getElementById('msgInput');
  var $send  = document.getElementById('sendBtn');
  var $clear = document.getElementById('clearBtn');
  var hasMessages = false;

  /* ── AUTO-RESIZE TEXTAREA ────────────────────────────────── */
  $input.addEventListener('input', function () {
    this.style.height = 'auto';
    this.style.height = Math.min(this.scrollHeight, 130) + 'px';
  });

  /* ── API CALL ────────────────────────────────────────────── */
  function callChatbotApi(message) {
    return sdk.chatbotPost(
      {},
      {
        messages: [{
          type: 'unstructured',
          unstructured: {
            id: sessionId,
            text: message,
            timestamp: new Date().toISOString()
          }
        }]
      },
      {}
    );
  }

  /* ── UTILITIES ───────────────────────────────────────────── */
  function escapeHtml(str) {
    return String(str)
      .replace(/&/g,  '&amp;')
      .replace(/</g,  '&lt;')
      .replace(/>/g,  '&gt;')
      .replace(/"/g,  '&quot;')
      .replace(/\n/g, '<br>');
  }

  function formatTime(date) {
    var h = date.getHours(), m = date.getMinutes();
    var ap = h >= 12 ? 'PM' : 'AM';
    h = h % 12 || 12;
    return h + ':' + (m < 10 ? '0' : '') + m + ' ' + ap;
  }

  function scrollBottom() {
    $area.scrollTop = $area.scrollHeight;
  }

  /* ── EMPTY STATE ─────────────────────────────────────────── */
  function hideEmptyState() {
    if (!hasMessages) {
      hasMessages = true;
      var el = document.getElementById('emptyState');
      if (el) el.style.display = 'none';
    }
  }

  /* ── CONTEXT-AWARE QUICK REPLY BUTTONS ──────────────────── */
  /*
    Detects what Lex just asked and surfaces the right option set.
    Sending the bare word (e.g. "Japanese", "Brooklyn") is enough
    because Lex slot-filling accepts plain values.
  */

  var QR_CUISINES = [
    { label: '🍣 Japanese',       msg: 'Japanese'       },
    { label: '🍕 Italian',        msg: 'Italian'        },
    { label: '🥢 Chinese',        msg: 'Chinese'        },
    { label: '🌮 Mexican',        msg: 'Mexican'        },
    { label: '🍛 Indian',         msg: 'Indian'         },
    { label: '🍜 Thai',           msg: 'Thai'           },
    { label: '🥩 Korean',         msg: 'Korean'         },
    { label: '🥐 French',         msg: 'French'         },
    { label: '🫒 Mediterranean',  msg: 'Mediterranean'  },
    { label: '🍔 American',       msg: 'American'       },
    { label: '🍲 Vietnamese',     msg: 'Vietnamese'     },
    { label: '🥘 Spanish',        msg: 'Spanish'        }
  ];

  var QR_LOCATIONS = [
    { label: '🗽 Manhattan',         msg: 'Manhattan'        },
    { label: '🌉 Brooklyn',          msg: 'Brooklyn'         },
    { label: '🌆 Queens',            msg: 'Queens'           },
    { label: '🏙 Bronx',             msg: 'Bronx'            },
    { label: '🏝 Staten Island',     msg: 'Staten Island'    },
    { label: '🌇 Jersey City',       msg: 'Jersey City'      },
    { label: '🚢 Hoboken',           msg: 'Hoboken'          },
    { label: '🏗 Long Island City',  msg: 'Long Island City' }
  ];

  var QR_DATE = [
    { label: '📅 Today',      msg: 'Today'    },
    { label: '📅 Tomorrow',   msg: 'Tomorrow' },
    { label: '📅 Saturday',   msg: 'Saturday' },
    { label: '📅 Sunday',     msg: 'Sunday'   }
  ];

  var QR_TIME = [
    { label: '🕕 5:00 PM', msg: '5:00 PM' },
    { label: '🕖 6:00 PM', msg: '6:00 PM' },
    { label: '🕖 6:30 PM', msg: '6:30 PM' },
    { label: '🕖 7:00 PM', msg: '7:00 PM' },
    { label: '🕗 7:30 PM', msg: '7:30 PM' },
    { label: '🕗 8:00 PM', msg: '8:00 PM' },
    { label: '🕗 8:30 PM', msg: '8:30 PM' },
    { label: '🕘 9:00 PM', msg: '9:00 PM' }
  ];

  var QR_PARTY = [
    { label: '👤 1',  msg: '1'  },
    { label: '👥 2',  msg: '2'  },
    { label: '👥 3',  msg: '3'  },
    { label: '👥 4',  msg: '4'  },
    { label: '👥 5',  msg: '5'  },
    { label: '👥 6',  msg: '6'  },
    { label: '👥 8',  msg: '8'  },
    { label: '👥 10', msg: '10' }
  ];

  var QR_REPEAT = [
    { label: '✅ Same as last time',    msg: 'Same'               },
    { label: '🔄 Something different',  msg: 'Something different' }
  ];

  /* Detect which set of quick replies to show based on bot text */
  function detectQuickReplySet(botText) {
    var t = botText.toLowerCase();

    if (t.includes('same') && t.includes('different') && t.includes('last time')) {
      return { title: null, items: QR_REPEAT };
    }
    if (t.includes('city') || t.includes('area') || t.includes('location') ||
        t.includes('dine in') || t.includes('looking to dine') || t.includes('where')) {
      return { title: '📍 Pick a location', items: QR_LOCATIONS };
    }
    if (t.includes('cuisine') || t.includes('food') || t.includes('craving') ||
        t.includes('what kind') || t.includes('type of')) {
      return { title: '🍽 Pick a cuisine', items: QR_CUISINES };
    }
    if (t.includes('what date') || t.includes('which date') || t.includes('what day') ||
        (t.includes('date') && !t.includes('up to date'))) {
      return { title: '📅 Pick a date', items: QR_DATE };
    }
    if (t.includes('what time') || t.includes('which time') ||
        (t.includes('time') && !t.includes('next time') && !t.includes('last time'))) {
      return { title: '🕐 Pick a time', items: QR_TIME };
    }
    if (t.includes('party') || t.includes('how many') || t.includes('number of people') ||
        t.includes('guests') || t.includes('people in your')) {
      return { title: '👥 Party size', items: QR_PARTY };
    }
    return null;
  }

  function buildQuickReplies(botText) {
    var result = detectQuickReplySet(botText);
    if (!result) return '';

    var titleHtml = result.title
      ? '<div class="qr-title">' + escapeHtml(result.title) + '</div>'
      : '';

    var btns = result.items.map(function (r) {
      return '<button class="qr-btn" data-msg="' + escapeHtml(r.msg) + '">' +
               escapeHtml(r.label) + '</button>';
    }).join('');

    return '<div class="quick-replies">' + titleHtml + btns + '</div>';
  }

  /* ── CONFIRMATION DETECTION ──────────────────────────────── */
  var CONFIRM_PHRASES = [
    "you're all set", "all set", "expect my suggestions",
    "will notify", "suggestions shortly", "sent to your email"
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

  /* ── RENDER: USER MESSAGE ────────────────────────────────── */
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

  /* ── RENDER: TYPING INDICATOR ────────────────────────────── */
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
          '<div class="td"></div><div class="td"></div><div class="td"></div>',
        '</div>',
      '</div>'
    ].join('');
    $area.appendChild(el);
    scrollBottom();
  }

  function removeTyping() {
    var el = document.getElementById('typingRow');
    if (el) el.remove();
  }

  /* ── RENDER: BOT MESSAGE ─────────────────────────────────── */
  function addBotMessage(text) {
    var el = document.createElement('div');
    el.className = 'msg-row';

    // Don't show quick replies after a confirmation — conversation is done
    var quickRepliesHtml = isConfirmation(text) ? '' : buildQuickReplies(text);
    var confirmCardHtml  = isConfirmation(text) ? buildConfirmCard() : '';

    el.innerHTML = [
      '<div class="msg-avatar">&#127869;</div>',
      '<div class="msg-content">',
        '<div class="msg-sender">Concierge</div>',
        '<div class="bubble bubble-bot">', escapeHtml(text), '</div>',
        confirmCardHtml,
        quickRepliesHtml,
        '<div class="msg-time">', formatTime(new Date()), '</div>',
      '</div>'
    ].join('');

    $area.appendChild(el);
    scrollBottom();
  }

  /* ── SEND MESSAGE ────────────────────────────────────────── */
  var sending = false;
  var MIN_TYPING_MS = 750;

  function sendMessage(overrideText) {
    var text = (overrideText !== undefined ? overrideText : $input.value).trim();
    if (!text || sending) return;

    sending = true;
    $send.disabled = true;
    $input.value = '';
    $input.style.height = 'auto';

    addUserMessage(text);
    var typingStart = Date.now();
    setTimeout(showTyping, 120);

    callChatbotApi(text)
      .then(function (res) {
        var wait = Math.max(0, MIN_TYPING_MS - (Date.now() - typingStart));
        setTimeout(function () {
          removeTyping();

          var data = res.data;
          if (typeof data === 'string') {
            try { data = JSON.parse(data); } catch (e) {
              addBotMessage('Received an unreadable response. Please try again.');
              sending = false; $send.disabled = false;
              return;
            }
          }

          if (data && data.messages && data.messages.length > 0) {
            data.messages.forEach(function (m) {
              if (m.type === 'unstructured' && m.unstructured && m.unstructured.text) {
                addBotMessage(m.unstructured.text);
              }
            });
          } else {
            addBotMessage('Something went wrong. Please try again.');
          }

          sending = false;
          $send.disabled = false;
        }, wait);
      })
      .catch(function (err) {
        console.error('[DC] API error:', err);
        setTimeout(function () {
          removeTyping();
          addBotMessage("Oops \u2014 couldn\u2019t connect. Please try again.");
          sending = false; $send.disabled = false;
        }, 400);
      });
  }

  /* ── CLEAR CHAT ──────────────────────────────────────────── */
  function clearChat() {
    $area.innerHTML = '';
    hasMessages = false;
    sessionId = newSessionId();
    // Re-show empty state
    var es = document.createElement('div');
    es.className = 'empty-state';
    es.id = 'emptyState';
    es.innerHTML = [
      '<div class="empty-glyph">&#10022;</div>',
      '<div class="empty-ornament">&middot; &middot; &middot; &middot; &middot;</div>',
      '<div class="empty-heading">Where would you like to dine tonight?</div>',
      '<div class="empty-body">Tell me a cuisine and location<br>and I\'ll find the perfect table</div>'
    ].join('');
    $area.appendChild(es);
  }

  /* ── EVENT LISTENERS ─────────────────────────────────────── */
  $send.addEventListener('click', function () { sendMessage(); });

  $input.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });

  // Quick reply buttons (delegated — they're added dynamically)
  $area.addEventListener('click', function (e) {
    var btn = e.target.closest('.qr-btn');
    if (btn && btn.dataset.msg) { sendMessage(btn.dataset.msg); }
  });

  $clear.addEventListener('click', clearChat);

  /* ── INITIAL GREETING ────────────────────────────────────── */
  setTimeout(function () {
    addBotMessage(
      "Hi there! How can I help you today?"
    );
  }, 650);

})();