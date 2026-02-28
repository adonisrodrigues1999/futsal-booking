document.addEventListener('DOMContentLoaded', function() {
  var appLoader = (function() {
    var root = document.getElementById('app-loader');
    var textEl = root ? root.querySelector('.loader-text') : null;
    var subEl = root ? root.querySelector('.loader-subtext') : null;
    var lockCount = 0;

    function show(message, subtext) {
      if (!root) return;
      lockCount += 1;
      if (textEl && message) textEl.textContent = message;
      if (subEl && subtext) subEl.textContent = subtext;
      root.classList.add('is-active');
      root.setAttribute('aria-hidden', 'false');
    }

    function hide(force) {
      if (!root) return;
      if (force) lockCount = 0;
      else lockCount = Math.max(0, lockCount - 1);
      if (lockCount > 0) return;
      root.classList.remove('is-active');
      root.setAttribute('aria-hidden', 'true');
    }

    return {
      show: show,
      hide: hide
    };
  })();
  window.appLoader = appLoader;

  function getCookie(name) {
    var match = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return match ? match.pop() : '';
  }

  // Keep form token aligned with latest CSRF cookie to avoid stale token posts.
  function syncFormCsrfTokens() {
    var csrftoken = getCookie('csrftoken');
    if (!csrftoken) return;
    document.querySelectorAll('form input[name="csrfmiddlewaretoken"]').forEach(function(input) {
      input.value = csrftoken;
    });
  }

  syncFormCsrfTokens();
  document.querySelectorAll('form').forEach(function(form) {
    form.addEventListener('submit', syncFormCsrfTokens);
  });

  function showAppToast(message, type, delay) {
    var toastEl = document.getElementById('app-toast');
    if (!toastEl) return;
    var toastBody = toastEl.querySelector('.toast-body');
    if (!toastBody) return;

    toastBody.textContent = message;
    toastEl.classList.remove('text-bg-dark', 'text-bg-success', 'text-bg-danger', 'text-bg-warning');
    if (type === 'success') toastEl.classList.add('text-bg-success');
    else if (type === 'danger') toastEl.classList.add('text-bg-danger');
    else if (type === 'warning') toastEl.classList.add('text-bg-warning');
    else toastEl.classList.add('text-bg-dark');

    var toast = bootstrap.Toast.getOrCreateInstance(toastEl, { delay: delay || 2600 });
    toast.show();
  }

  window.showAppToast = showAppToast;

  // Loader policy: show only for background API calls.
  var BG_API_LOADER_DELAY_MS = 1200;
  var BG_API_LOADER_VISIBLE_MS = 1500;

  window.addEventListener('pageshow', function() {
    appLoader.hide(true);
  });

  if (window.fetch) {
    var nativeFetch = window.fetch.bind(window);
    window.fetch = function() {
      var init = arguments[1] || {};
      var shouldUseBackgroundLoader = !!(init && init.__backgroundLoader);
      if (!shouldUseBackgroundLoader) return nativeFetch.apply(null, arguments);

      var shouldShow = false;
      var timer = setTimeout(function() {
        shouldShow = true;
        appLoader.show('Page loading...', 'Do not refresh browser');
        setTimeout(function() {
          appLoader.hide(true);
        }, BG_API_LOADER_VISIBLE_MS);
      }, BG_API_LOADER_DELAY_MS);

      return nativeFetch.apply(null, arguments).finally(function() {
        clearTimeout(timer);
        if (!shouldShow) {
          appLoader.hide(true);
        }
      });
    };
  }

  // Quick shimmer load state for cards
  var loadingCards = document.querySelectorAll('.slot-card, .ground-card, .metric-card');
  if (loadingCards.length) {
    loadingCards.forEach(function(card) { card.classList.add('card-loading'); });
    loadingCards.forEach(function(card, idx) {
      setTimeout(function() { card.classList.remove('card-loading'); }, 220 + (idx * 35));
    });
  }

  // Highlight active nav item based on current path
  var currentPath = window.location.pathname;
  document.querySelectorAll('.site-navbar .nav-link').forEach(function(link) {
    var href = link.getAttribute('href');
    if (!href) return;
    if (href !== '/' && currentPath.indexOf(href) === 0) {
      link.classList.add('active');
      link.style.backgroundColor = 'rgba(255,255,255,0.2)';
    }
    if (href === '/' && currentPath === '/') {
      link.classList.add('active');
      link.style.backgroundColor = 'rgba(255,255,255,0.2)';
    }
  });

  // Reveal sections/cards as they enter viewport
  var revealTargets = document.querySelectorAll('.page-shell, .panel-soft, .ground-card, .metric-card, .slot-wrap');
  if ('IntersectionObserver' in window && revealTargets.length) {
    var revealObserver = new IntersectionObserver(function(entries, obs) {
      entries.forEach(function(entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('reveal-visible');
          obs.unobserve(entry.target);
        }
      });
    }, { threshold: 0.08 });

    revealTargets.forEach(function(node) {
      node.classList.add('reveal');
      revealObserver.observe(node);
    });
  }

  // Password visibility toggles
  document.querySelectorAll('[data-toggle="pw-toggle"]').forEach(function(btn) {
    btn.addEventListener('click', function(e) {
      e.preventDefault();
      var target = document.querySelector(btn.dataset.target);
      if (!target) return;
      if (target.type === 'password') {
        target.type = 'text';
        btn.textContent = 'Hide';
      } else {
        target.type = 'password';
        btn.textContent = 'Show';
      }
    });
  });

  // Password strength meter
  var pw = document.getElementById('id_password');
  var meter = document.getElementById('pw-strength-level');
  if (pw && meter) {
    pw.addEventListener('input', function() {
      var val = pw.value || '';
      var score = 0;
      if (val.length >= 6) score += 1;
      if (/[0-9]/.test(val)) score += 1;
      if (/[A-Z]/.test(val)) score += 1;
      if (/[^A-Za-z0-9]/.test(val)) score += 1;
      var pct = Math.min(100, (score / 4) * 100);
      meter.style.width = pct + '%';
      if (pct < 40) meter.style.background = 'linear-gradient(90deg,#ff6b6b,#ff8a8a)';
      else if (pct < 75) meter.style.background = 'linear-gradient(90deg,#ffd166,#ffc857)';
      else meter.style.background = 'linear-gradient(90deg,#8ee4af,#2ecc71)';
    });
  }

  // Slot card entrance animation (stagger)
  var cards = document.querySelectorAll('.slot-card');
  if (cards.length) {
    cards.forEach(function(c, i) {
      setTimeout(function() { c.classList.add('enter'); }, i * 40);
    });
  }

  // Live counters on slots page
  function setCounterValue(id, value) {
    var el = document.getElementById(id);
    if (!el) return;
    var next = String(value);
    if (el.textContent !== next) {
      el.textContent = next;
      el.classList.remove('count-flash');
      // trigger animation restart
      void el.offsetWidth;
      el.classList.add('count-flash');
    }
  }

  function updateSlotLiveCounters() {
    var flags = document.querySelectorAll('[data-slot-state]');
    if (!flags.length) return;
    var available = 0;
    var booked = 0;
    var yours = 0;

    flags.forEach(function(flag) {
      var state = flag.getAttribute('data-slot-state');
      if (state === 'available') available += 1;
      if (state === 'booked') booked += 1;
      if (state === 'past') booked += 1;
      if (state === 'your') yours += 1;
    });

    setCounterValue('live-available-count', available);
    setCounterValue('live-booked-count', booked);
    setCounterValue('live-your-count', yours);
  }
  window.__updateSlotLiveCounters = updateSlotLiveCounters;

  updateSlotLiveCounters();
  setInterval(updateSlotLiveCounters, 30000);

  // Auto-refresh slot availability every 8s without reloading page.
  (function initSlotAvailabilityAutoRefresh() {
    var cards = Array.prototype.slice.call(document.querySelectorAll('.slot-card[data-slot-id]'));
    if (!cards.length || !window.slotStatusUrl) return;

    function findCard(slotId) {
      return cards.find(function(card) {
        return String(card.getAttribute('data-slot-id')) === String(slotId);
      });
    }

    function markBooked(card) {
      if (!card) return;
      if (card.querySelector('[data-slot-state="your"]')) return;
      if (card.getAttribute('data-availability') === 'booked') return;
      var body = card.querySelector('.slot-body');
      if (!body) return;
      body.classList.add('muted');
      body.innerHTML = '<div class="slot-status"><span data-slot-state="booked">Booked</span></div>' +
        '<button class="btn btn-outline-secondary slot-action" disabled aria-disabled="true">Booked</button>';
      card.setAttribute('data-availability', 'booked');
    }

    function markAvailable(card) {
      if (!card) return;
      if (card.getAttribute('data-past') === '1') return;
      if (card.querySelector('[data-slot-state="your"]')) return;
      if (card.getAttribute('data-availability') === 'available') return;
      var body = card.querySelector('.slot-body');
      if (!body) return;
      var slotId = Number(card.getAttribute('data-slot-id'));
      var startTime = card.getAttribute('data-start-time') || '';
      var endTime = card.getAttribute('data-end-time') || '';
      var price = Number(card.getAttribute('data-price') || 0);
      body.classList.remove('muted');
      body.innerHTML = '<div class="slot-status text-success"><span data-slot-state="available">Available</span></div>' +
        '<button type="button" class="btn btn-primary slot-action">Book</button>';
      var btn = body.querySelector('.slot-action');
      if (btn && typeof window.showConfirmModal === 'function') {
        btn.addEventListener('click', function() {
          window.showConfirmModal(slotId, startTime, endTime, price);
        });
      }
      card.setAttribute('data-availability', 'available');
    }

    var isPolling = false;
    function pollSlotStatus() {
      if (isPolling) return;
      var modalOpen = document.querySelector('.modal.show');
      if (modalOpen) return;
      isPolling = true;
      var slotIds = cards.map(function(card) { return card.getAttribute('data-slot-id'); }).join(',');
      var url = window.slotStatusUrl + (window.slotStatusUrl.indexOf('?') >= 0 ? '&' : '?') + 'slot_ids=' + encodeURIComponent(slotIds);
      fetch(url, {
        credentials: 'same-origin',
        __backgroundLoader: true
      }).then(function(res) {
        return res.json().then(function(data) {
          if (!res.ok || !data.success) throw new Error('slot status fetch failed');
          return data;
        });
      }).then(function(data) {
        (data.slots || []).forEach(function(slotRow) {
          var card = findCard(slotRow.id);
          if (!card) return;
          if (slotRow.is_booked) markBooked(card);
          else markAvailable(card);
        });
        if (typeof window.__updateSlotLiveCounters === 'function') {
          window.__updateSlotLiveCounters();
        }
      }).catch(function() {
        // silent retry on next interval
      }).finally(function() {
        isPolling = false;
      });
    }

    setInterval(pollSlotStatus, 8000);
  })();

  // Styled double-confirmation modal for destructive actions.
  var actionConfirmEl = document.getElementById('actionConfirmModal');
  var actionConfirmModal = actionConfirmEl ? new bootstrap.Modal(actionConfirmEl, { backdrop: 'static' }) : null;
  var actionConfirmMessageEl = document.getElementById('action-confirm-message');
  var actionConfirmHintEl = document.getElementById('action-confirm-hint');
  var actionConfirmNextBtn = document.getElementById('action-confirm-next');
  var actionConfirmFinalBtn = document.getElementById('action-confirm-final');
  var actionConfirmState = {
    step: 1,
    type: null,
    href: null,
    form: null,
    submitter: null
  };

  function resetActionConfirmState() {
    actionConfirmState.step = 1;
    actionConfirmState.type = null;
    actionConfirmState.href = null;
    actionConfirmState.form = null;
    actionConfirmState.submitter = null;
    if (actionConfirmHintEl) actionConfirmHintEl.textContent = 'Step 1 of 2: Review this action.';
    if (actionConfirmNextBtn) actionConfirmNextBtn.classList.remove('d-none');
    if (actionConfirmFinalBtn) actionConfirmFinalBtn.classList.add('d-none');
  }

  function openActionConfirm(opts) {
    if (!actionConfirmModal || !actionConfirmMessageEl) return false;
    resetActionConfirmState();
    actionConfirmState.type = opts.type;
    actionConfirmState.href = opts.href || null;
    actionConfirmState.form = opts.form || null;
    actionConfirmState.submitter = opts.submitter || null;
    actionConfirmMessageEl.textContent = opts.message || 'Please confirm this action.';
    actionConfirmModal.show();
    return true;
  }

  function executeConfirmedAction() {
    if (actionConfirmState.type === 'link' && actionConfirmState.href) {
      window.location = actionConfirmState.href;
      return;
    }
    if (actionConfirmState.type === 'form' && actionConfirmState.form) {
      actionConfirmModal.hide();
      if (actionConfirmState.form.requestSubmit && actionConfirmState.submitter) {
        actionConfirmState.form.requestSubmit(actionConfirmState.submitter);
      } else {
        actionConfirmState.form.submit();
      }
    }
  }

  if (actionConfirmNextBtn) {
    actionConfirmNextBtn.addEventListener('click', function() {
      actionConfirmState.step = 2;
      if (actionConfirmHintEl) actionConfirmHintEl.textContent = 'Step 2 of 2: Final confirmation required.';
      actionConfirmNextBtn.classList.add('d-none');
      if (actionConfirmFinalBtn) actionConfirmFinalBtn.classList.remove('d-none');
    });
  }

  if (actionConfirmFinalBtn) {
    actionConfirmFinalBtn.addEventListener('click', function() {
      executeConfirmedAction();
    });
  }

  if (actionConfirmEl) {
    actionConfirmEl.addEventListener('hidden.bs.modal', function() {
      resetActionConfirmState();
    });
  }

  document.querySelectorAll('a[data-confirm-message]').forEach(function(link) {
    link.addEventListener('click', function(e) {
      if (e.defaultPrevented) return;
      if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      var opened = openActionConfirm({
        type: 'link',
        href: link.getAttribute('href'),
        message: link.dataset.confirmMessage
      });
      if (opened) e.preventDefault();
    });
  });

  document.querySelectorAll('button[data-confirm-message], input[type="submit"][data-confirm-message]').forEach(function(btn) {
    btn.addEventListener('click', function(e) {
      var form = btn.form || btn.closest('form');
      if (!form) return;
      var opened = openActionConfirm({
        type: 'form',
        form: form,
        submitter: btn,
        message: btn.dataset.confirmMessage
      });
      if (opened) e.preventDefault();
    });
  });

  // Ripple effect for slot action buttons
  document.querySelectorAll('.slot-action').forEach(function(btn) {
    btn.style.position = 'relative';
    btn.addEventListener('click', function(e) {
      var rect = btn.getBoundingClientRect();
      var ripple = document.createElement('span');
      ripple.className = 'ripple';
      ripple.style.width = ripple.style.height = Math.max(rect.width, rect.height) + 'px';
      ripple.style.left = (e.clientX - rect.left - rect.width/2) + 'px';
      ripple.style.top = (e.clientY - rect.top - rect.height/2) + 'px';
      btn.appendChild(ripple);
      setTimeout(function() { ripple.remove(); }, 650);
    });
  });
  
  // Simple count-up animation for metrics
  document.querySelectorAll('[data-count]').forEach(function(el) {
    var target = parseInt(el.textContent.toString().replace(/[^0-9]/g,'')) || 0;
    el.textContent = '0';
    var duration = 700;
    var start = null;
    function step(ts) {
      if (!start) start = ts;
      var progress = Math.min((ts - start) / duration, 1);
      el.textContent = Math.floor(progress * target).toLocaleString();
      if (progress < 1) requestAnimationFrame(step);
      else el.textContent = target.toLocaleString();
    }
    requestAnimationFrame(step);
  });

  function getSelectedPaymentMode() {
    var checked = document.querySelector('input[name="cm-payment-mode"]:checked');
    return checked ? checked.value : 'FULL';
  }

  function verifyAndFinalizeBooking(slotId, paymentMode, rpResponse, confirmBtn) {
    var csrftoken = getCookie('csrftoken');
    fetch('/payments/razorpay/verify-and-book/', {
      method: 'POST',
      headers: {
        'X-CSRFToken': csrftoken,
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
      credentials: 'same-origin',
      body: JSON.stringify({
        slot_id: slotId,
        payment_mode: paymentMode,
        razorpay_order_id: rpResponse.razorpay_order_id,
        razorpay_payment_id: rpResponse.razorpay_payment_id,
        razorpay_signature: rpResponse.razorpay_signature
      })
    }).then(function(res) {
      return res.json().then(function(data) {
        if (!res.ok || !data.success) throw new Error((data && data.error) || 'Booking verification failed');
        return data;
      });
    }).then(function(data) {
      showAppToast(data.message || 'Booking confirmed. Non-refundable payment.', 'success', 2600);
      setTimeout(function() {
        window.location = data.redirect_url || '/my-bookings/';
      }, 400);
    }).catch(function(err) {
      showAppToast(err.message || 'Payment verified but booking failed. Contact support.', 'danger', 4200);
      confirmBtn.disabled = false;
      confirmBtn.textContent = 'Proceed to Pay';
    });
  }

  function startSlotCheckout(slotId, confirmBtn) {
    var ack = document.getElementById('cm-non-refundable-ack');
    if (!ack || !ack.checked) {
      showAppToast('Please accept the non-refundable policy before payment.', 'warning', 3000);
      return;
    }

    if (typeof Razorpay === 'undefined') {
      showAppToast('Payment gateway not loaded. Refresh and try again.', 'danger', 3200);
      return;
    }

    var paymentMode = getSelectedPaymentMode();
    var csrftoken = getCookie('csrftoken');

    confirmBtn.disabled = true;
    confirmBtn.textContent = 'Initializing...';

    fetch('/payments/razorpay/create-order/', {
      method: 'POST',
      headers: {
        'X-CSRFToken': csrftoken,
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
      credentials: 'same-origin',
      body: JSON.stringify({
        slot_id: slotId,
        payment_mode: paymentMode
      })
    }).then(function(res) {
      return res.json().then(function(data) {
        if (!res.ok || !data.success) throw new Error((data && data.error) || 'Unable to initialize payment');
        return data;
      });
    }).then(function(orderData) {
      var options = {
        key: orderData.key_id,
        amount: orderData.pay_now_amount * 100,
        currency: orderData.currency || 'INR',
        name: 'FootBook',
        description: 'Slot booking payment (non-refundable)',
        order_id: orderData.order_id,
        handler: function(resp) {
          verifyAndFinalizeBooking(slotId, orderData.payment_mode, resp, confirmBtn);
        },
        modal: {
          ondismiss: function() {
            confirmBtn.disabled = false;
            confirmBtn.textContent = 'Proceed to Pay';
            showAppToast('Payment was cancelled.', 'warning', 2200);
          }
        },
        prefill: orderData.prefill || {}
      };

      var checkout = new Razorpay(options);
      checkout.on('payment.failed', function() {
        confirmBtn.disabled = false;
        confirmBtn.textContent = 'Proceed to Pay';
        showAppToast('Payment failed. Please try again.', 'danger', 3200);
      });
      confirmModal.hide();
      checkout.open();
    }).catch(function(err) {
      confirmBtn.disabled = false;
      confirmBtn.textContent = 'Proceed to Pay';
      showAppToast(err.message || 'Unable to start payment.', 'danger', 3200);
    });
  }

  // Initialize single reusable modal instance
  var modalEl = document.getElementById('confirmModalGlobal');
  var confirmModal = modalEl ? new bootstrap.Modal(modalEl, {}) : null;

  // show reusable confirmation modal
  window.showConfirmModal = function(slotId, startTime, endTime, price) {
    if (!modalEl || !confirmModal) return;
    document.getElementById('cm-slot-time').innerHTML = 'Slot: <strong>' + startTime + ' - ' + endTime + '</strong>';
    document.getElementById('cm-ground').innerHTML = 'Ground: <strong>' + (window.currentGroundName || document.title) + '</strong>';
    document.getElementById('cm-price').innerHTML = 'Price: <strong>₹' + price + '</strong>';
    var fullRadio = document.getElementById('cm-payment-full');
    var ack = document.getElementById('cm-non-refundable-ack');
    if (fullRadio) fullRadio.checked = true;
    if (ack) ack.checked = false;

    var confirmBtn = document.getElementById('cm-confirm-btn');
    confirmBtn.disabled = false;
    confirmBtn.textContent = 'Proceed to Pay';
    // replace click handler
    confirmBtn.onclick = function() { startSlotCheckout(slotId, confirmBtn); };

    confirmModal.show();
  };
});
