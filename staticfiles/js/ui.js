document.addEventListener('DOMContentLoaded', function() {
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

  updateSlotLiveCounters();
  setInterval(updateSlotLiveCounters, 30000);

  // Replace browser confirm with toast-driven 2-step confirmation
  document.querySelectorAll('a[data-confirm-message]').forEach(function(link) {
    link.addEventListener('click', function(e) {
      var now = Date.now();
      var armedUntil = parseInt(link.dataset.confirmArmedUntil || '0', 10);
      if (armedUntil > now) {
        showAppToast('Processing request...', 'info', 1200);
        return;
      }

      e.preventDefault();
      link.dataset.confirmArmedUntil = String(now + 4200);
      showAppToast((link.dataset.confirmMessage || 'Please confirm action.') + ' Tap again to continue.', 'warning', 3600);
      setTimeout(function() {
        if ((parseInt(link.dataset.confirmArmedUntil || '0', 10)) <= Date.now()) {
          delete link.dataset.confirmArmedUntil;
        }
      }, 4400);
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

  // Book slot via fetch (CSRF safe)
  window.bookSlot = function(slotId, btn) {
    var url = '/book/' + slotId + '/';
    var csrftoken = null;
    // try cookie
    function getCookie(name) {
      var v = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
      return v ? v.pop() : '';
    }
    csrftoken = getCookie('csrftoken');

    btn.disabled = true;
    btn.textContent = 'Booking...';

    fetch(url, {
      method: 'POST',
      headers: {
        'X-CSRFToken': csrftoken,
        'Accept': 'text/html'
      },
      credentials: 'same-origin'
    }).then(function(res) {
      if (res.redirected) {
        btn.textContent = 'Booked!';
        // follow redirect
        setTimeout(function() { window.location = res.url; }, 240);
        return;
      }
      if (res.ok) {
        btn.textContent = 'Booked!';
        showAppToast('Booking confirmed successfully.', 'success', 1800);
        // reload to reflect booking state
        setTimeout(function() { window.location.reload(); }, 240);
      } else {
        return res.text().then(function(t) { throw new Error('Booking failed'); });
      }
    }).catch(function(err){
      showAppToast('Unable to book slot. Please try again.', 'danger', 2800);
      btn.disabled = false;
      btn.textContent = 'Confirm Booking';
      console.error(err);
    });
  };

  // Initialize single reusable modal instance
  var modalEl = document.getElementById('confirmModalGlobal');
  var confirmModal = modalEl ? new bootstrap.Modal(modalEl, {}) : null;

  // show reusable confirmation modal
  window.showConfirmModal = function(slotId, startTime, endTime, price) {
    if (!modalEl || !confirmModal) return;
    document.getElementById('cm-slot-time').innerHTML = 'Slot: <strong>' + startTime + ' - ' + endTime + '</strong>';
    document.getElementById('cm-ground').innerHTML = 'Ground: <strong>' + (window.currentGroundName || document.title) + '</strong>';
    document.getElementById('cm-price').innerHTML = 'Price: <strong>₹' + price + '</strong>';

    var confirmBtn = document.getElementById('cm-confirm-btn');
    confirmBtn.disabled = false;
    confirmBtn.textContent = 'Confirm Booking';
    // replace click handler
    confirmBtn.onclick = function() { bookSlot(slotId, confirmBtn); };

    confirmModal.show();
  };
});
