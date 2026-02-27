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
    { label: 'Manhattan',         msg: 'Manhattan'        },
    { label: 'Brooklyn',          msg: 'Brooklyn'         },
    { label: 'Queens',            msg: 'Queens'           },
    { label: 'Bronx',             msg: 'Bronx'            },
    { label: 'Staten Island',     msg: 'Staten Island'    },
    { label: 'Jersey City',       msg: 'Jersey City'      },
    { label: 'Hoboken',           msg: 'Hoboken'          },
    { label: 'Long Island City',  msg: 'Long Island City' }
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
    { label: '🔄 Different',  msg: 'Different' }
  ];

  /* Detect which set of quick replies to show based on bot text */
  function detectQuickReplySet(botText) {
    var t = botText.toLowerCase();

    if (t.includes('same') && t.includes('different') && t.includes('last time')) {
      return { title: null, items: QR_REPEAT, type: 'buttons' };
    }
    // Match normal ask + validation error re-ask (error contains city names like "manhattan")
    if (t.includes('city') || t.includes('area') || t.includes('location') ||
        t.includes('dine in') || t.includes('looking to dine') || t.includes('where') ||
        t.includes('manhattan') || t.includes('brooklyn') || t.includes('which area')) {
      return { title: '📍 Pick a location', items: QR_LOCATIONS, type: 'buttons' };
    }
    // Match normal ask + validation error re-ask (error contains cuisine names like "japanese")
    if (t.includes('cuisine') || t.includes('food') || t.includes('craving') ||
        t.includes('what kind') || t.includes('type of') ||
        t.includes('japanese') || t.includes('italian') || t.includes('choose from')) {
      return { title: '🍽 Pick a cuisine', items: QR_CUISINES, type: 'buttons' };
    }
    // Match normal ask + past-date error re-ask
    if (t.includes('what date') || t.includes('which date') || t.includes('what day') ||
        t.includes('future date') || t.includes('valid date') || t.includes('in the past') ||
        (t.includes('date') && !t.includes('up to date'))) {
      return { title: '📅 Pick a date', items: null, type: 'date-picker' };
    }
    // Match normal ask + invalid-time error re-ask
    if (t.includes('what time') || t.includes('which time') ||
        t.includes('valid time') || t.includes('like 7pm') ||
        (t.includes('time') && !t.includes('next time') && !t.includes('last time'))) {
      return { title: '🕐 Pick a time', items: null, type: 'time-picker' };
    }
    // Match normal ask + out-of-range error re-ask
    if (t.includes('party') || t.includes('how many') || t.includes('number of people') ||
        t.includes('guests') || t.includes('people in your') ||
        t.includes('between 1 and 20') || t.includes('valid number of people')) {
      return { title: '👥 Party size', items: null, type: 'party-picker' };
    }
    return null;
  }

  function buildQuickReplies(botText) {
    var result = detectQuickReplySet(botText);
    if (!result) return '';

    if (result.type === 'buttons') {
      var titleHtml = result.title
        ? '<div class="qr-title">' + escapeHtml(result.title) + '</div>'
        : '';

      var btns = result.items.map(function (r) {
        return '<button class="qr-btn" data-msg="' + escapeHtml(r.msg) + '">' +
                 escapeHtml(r.label) + '</button>';
      }).join('');

      return '<div class="quick-replies">' + titleHtml + btns + '</div>';
    }
    
    if (result.type === 'date-picker') {
      return buildDatePicker(result.title);
    }
    
    if (result.type === 'time-picker') {
      return buildTimePicker(result.title);
    }
    
    if (result.type === 'party-picker') {
      return buildPartyPicker(result.title);
    }
    
    return '';
  }

  /* ── DATE PICKER ──────────────────────────────────────────── */
  function buildDatePicker(title) {
    var today = new Date();
    var currentMonth = today.getMonth();
    var currentYear = today.getFullYear();
    
    var html = '<div class="picker-container" data-picker="date">';
    html += '<div class="picker-title">' + escapeHtml(title) + '</div>';
    html += '<div class="date-picker">';
    html += '<div class="date-picker-header">';
    html += '<button class="date-picker-nav" data-action="prev-month">‹</button>';
    html += '<div class="date-picker-month" data-month="' + currentMonth + '" data-year="' + currentYear + '">';
    html += getMonthName(currentMonth) + ' ' + currentYear;
    html += '</div>';
    html += '<button class="date-picker-nav" data-action="next-month">›</button>';
    html += '</div>';
    html += buildDateGrid(currentMonth, currentYear, today);
    html += '</div>';
    html += '<button class="picker-confirm-btn" data-action="confirm-date" disabled>Confirm Date</button>';
    html += '</div>';
    
    return html;
  }

  function buildDateGrid(month, year, today) {
    var firstDay = new Date(year, month, 1).getDay();
    var daysInMonth = new Date(year, month + 1, 0).getDate();
    
    var html = '<div class="date-grid">';
    var dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    dayNames.forEach(function(day) {
      html += '<div class="date-grid-header">' + day + '</div>';
    });
    
    for (var i = 0; i < firstDay; i++) {
      html += '<button class="date-cell date-cell-empty"></button>';
    }
    
    for (var day = 1; day <= daysInMonth; day++) {
      var cellDate = new Date(year, month, day);
      var isToday = cellDate.toDateString() === today.toDateString();
      var isPast = cellDate < today && !isToday;
      var classes = 'date-cell';
      if (isToday) classes += ' date-cell-today';
      if (isPast) classes += ' date-cell-disabled';
      
      html += '<button class="' + classes + '" data-date="' + cellDate.toDateString() + '" ';
      html += 'data-day="' + day + '" data-month="' + month + '" data-year="' + year + '" ';
      html += (isPast ? 'disabled' : '') + '>' + day + '</button>';
    }
    
    html += '</div>';
    return html;
  }

  function getMonthName(month) {
    var names = ['January', 'February', 'March', 'April', 'May', 'June',
                 'July', 'August', 'September', 'October', 'November', 'December'];
    return names[month];
  }

  /* ── TIME PICKER ──────────────────────────────────────────── */
  function buildTimePicker(title) {
    var html = '<div class="picker-container" data-picker="time">';
    html += '<div class="picker-title">' + escapeHtml(title) + '</div>';
    html += '<div class="time-picker">';
    html += '<div class="time-display" data-time-display>5:00 PM</div>';
    html += '<div class="time-controls">';
    
    html += '<div class="time-control-group">';
    html += '<div class="time-control-label">Hour</div>';
    html += '<div class="time-control-btns">';
    html += '<button class="time-btn" data-action="hour-up">▲</button>';
    html += '<button class="time-btn" data-action="hour-down">▼</button>';
    html += '</div>';
    html += '</div>';
    
    html += '<div class="time-control-group">';
    html += '<div class="time-control-label">Minutes</div>';
    html += '<div class="time-control-btns">';
    html += '<button class="time-btn" data-action="min-up">▲</button>';
    html += '<button class="time-btn" data-action="min-down">▼</button>';
    html += '</div>';
    html += '</div>';
    
    html += '</div>';
    
    html += '<div class="time-presets">';
    var presets = ['5:00 PM', '6:00 PM', '7:00 PM', '8:00 PM'];
    presets.forEach(function(preset, idx) {
      html += '<button class="time-preset-btn' + (idx === 0 ? ' active' : '') + '" data-preset="' + preset + '">' + preset + '</button>';
    });
    html += '</div>';
    
    html += '</div>';
    html += '<button class="picker-confirm-btn" data-action="confirm-time">Confirm Time</button>';
    html += '</div>';
    
    return html;
  }

  /* ── PARTY PICKER ─────────────────────────────────────────── */
  function buildPartyPicker(title) {
    var html = '<div class="picker-container" data-picker="party">';
    html += '<div class="picker-title">' + escapeHtml(title) + '</div>';
    html += '<div class="party-picker">';
    
    var sizes = [
      { num: 1, icon: '👤', label: '1 person' },
      { num: 2, icon: '👥', label: '2 people' },
      { num: 3, icon: '👥', label: '3 people' },
      { num: 4, icon: '👥', label: '4 people' },
      { num: 5, icon: '👥', label: '5 people' },
      { num: 6, icon: '👥', label: '6 people' },
      { num: 8, icon: '👥', label: '8 people' },
      { num: 10, icon: '👥', label: '10+ people' }
    ];
    
    sizes.forEach(function(size) {
      html += '<button class="party-btn" data-party="' + size.num + '">';
      html += '<div class="party-btn-icon">' + size.icon + '</div>';
      html += '<div class="party-btn-label">' + size.num + '</div>';
      html += '</button>';
    });
    
    html += '</div>';
    html += '<button class="picker-confirm-btn" data-action="confirm-party" disabled>Confirm Party Size</button>';
    html += '</div>';
    
    return html;
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
    if (btn && btn.dataset.msg) { 
      sendMessage(btn.dataset.msg); 
      return;
    }
    
    // Date picker interactions
    var datePicker = e.target.closest('[data-picker="date"]');
    if (datePicker) {
      var dateCell = e.target.closest('.date-cell');
      if (dateCell && !dateCell.classList.contains('date-cell-disabled') && 
          !dateCell.classList.contains('date-cell-empty')) {
        datePicker.querySelectorAll('.date-cell').forEach(function(c) {
          c.classList.remove('date-cell-selected');
        });
        dateCell.classList.add('date-cell-selected');
        var confirmBtn = datePicker.querySelector('[data-action="confirm-date"]');
        confirmBtn.disabled = false;
        confirmBtn.dataset.selectedDate = dateCell.dataset.date;
      }
      
      if (e.target.dataset.action === 'confirm-date') {
        var selectedDate = e.target.dataset.selectedDate;
        if (selectedDate) {
          var date = new Date(selectedDate);
          var dateStr = formatDateForMessage(date);
          sendMessage(dateStr);
        }
      }
      
      if (e.target.dataset.action === 'prev-month' || e.target.dataset.action === 'next-month') {
        var monthEl = datePicker.querySelector('.date-picker-month');
        var currentMonth = parseInt(monthEl.dataset.month);
        var currentYear = parseInt(monthEl.dataset.year);
        
        if (e.target.dataset.action === 'prev-month') {
          currentMonth--;
          if (currentMonth < 0) {
            currentMonth = 11;
            currentYear--;
          }
        } else {
          currentMonth++;
          if (currentMonth > 11) {
            currentMonth = 0;
            currentYear++;
          }
        }
        
        monthEl.dataset.month = currentMonth;
        monthEl.dataset.year = currentYear;
        monthEl.textContent = getMonthName(currentMonth) + ' ' + currentYear;
        
        var gridContainer = datePicker.querySelector('.date-grid');
        var parent = gridContainer.parentNode;
        parent.removeChild(gridContainer);
        parent.insertAdjacentHTML('beforeend', buildDateGrid(currentMonth, currentYear, new Date()));
        
        var confirmBtn = datePicker.querySelector('[data-action="confirm-date"]');
        confirmBtn.disabled = true;
      }
    }
    
    // Time picker interactions
    var timePicker = e.target.closest('[data-picker="time"]');
    if (timePicker) {
      var timeDisplay = timePicker.querySelector('[data-time-display]');
      var currentTime = parseTime(timeDisplay.textContent);
      
      if (e.target.dataset.action === 'hour-up') {
        currentTime.hour = (currentTime.hour % 12) + 1;
        updateTimeDisplay(timeDisplay, currentTime);
        clearActivePreset(timePicker);
      }
      
      if (e.target.dataset.action === 'hour-down') {
        currentTime.hour = currentTime.hour - 1;
        if (currentTime.hour < 1) currentTime.hour = 12;
        updateTimeDisplay(timeDisplay, currentTime);
        clearActivePreset(timePicker);
      }
      
      if (e.target.dataset.action === 'min-up') {
        currentTime.minute = (currentTime.minute + 15) % 60;
        updateTimeDisplay(timeDisplay, currentTime);
        clearActivePreset(timePicker);
      }
      
      if (e.target.dataset.action === 'min-down') {
        currentTime.minute = currentTime.minute - 15;
        if (currentTime.minute < 0) currentTime.minute = 45;
        updateTimeDisplay(timeDisplay, currentTime);
        clearActivePreset(timePicker);
      }
      
      var presetBtn = e.target.closest('.time-preset-btn');
      if (presetBtn) {
        timePicker.querySelectorAll('.time-preset-btn').forEach(function(b) {
          b.classList.remove('active');
        });
        presetBtn.classList.add('active');
        timeDisplay.textContent = presetBtn.dataset.preset;
      }
      
      if (e.target.dataset.action === 'confirm-time') {
        sendMessage(timeDisplay.textContent);
      }
    }
    
    // Party picker interactions
    var partyPicker = e.target.closest('[data-picker="party"]');
    if (partyPicker) {
      var partyBtn = e.target.closest('.party-btn');
      if (partyBtn) {
        partyPicker.querySelectorAll('.party-btn').forEach(function(b) {
          b.classList.remove('active');
        });
        partyBtn.classList.add('active');
        var confirmBtn = partyPicker.querySelector('[data-action="confirm-party"]');
        confirmBtn.disabled = false;
        confirmBtn.dataset.selectedParty = partyBtn.dataset.party;
      }
      
      if (e.target.dataset.action === 'confirm-party') {
        var partySize = e.target.dataset.selectedParty;
        if (partySize) {
          sendMessage(partySize);
        }
      }
    }
  });

  function formatDateForMessage(date) {
    var today = new Date();
    var tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);
    
    if (date.toDateString() === today.toDateString()) return 'Today';
    if (date.toDateString() === tomorrow.toDateString()) return 'Tomorrow';
    
    var days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
    var months = ['January', 'February', 'March', 'April', 'May', 'June',
                  'July', 'August', 'September', 'October', 'November', 'December'];
    
    return days[date.getDay()] + ', ' + months[date.getMonth()] + ' ' + date.getDate();
  }

  function parseTime(timeStr) {
    var parts = timeStr.match(/(\d+):(\d+)\s*(AM|PM)/);
    return {
      hour: parseInt(parts[1]),
      minute: parseInt(parts[2]),
      period: parts[3]
    };
  }

  function updateTimeDisplay(display, time) {
    var minStr = time.minute < 10 ? '0' + time.minute : time.minute;
    display.textContent = time.hour + ':' + minStr + ' ' + time.period;
  }

  function clearActivePreset(timePicker) {
    timePicker.querySelectorAll('.time-preset-btn').forEach(function(b) {
      b.classList.remove('active');
    });
  }

  $clear.addEventListener('click', clearChat);

  /* ── INITIAL GREETING ────────────────────────────────────── */
  setTimeout(function () {
    addBotMessage(
      "Hi there! How can I help you today?"
    );
  }, 650);

})();