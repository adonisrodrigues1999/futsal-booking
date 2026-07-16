/* Owner Dashboard — AJAX Form Handling & Partial Updates
 *
 * Intercepts all .ajax-form submissions and the booking date filter form,
 * sends them via fetch(), intercepts the redirected response, and updates
 * only the relevant sections of the page without a full refresh.
 *
 * Strategy: Forms POST normally (server still redirects). Fetch follows
 * the redirect automatically, returns the HTML of the destination page.
 * We extract only the sections that need updating from that HTML.
 *
 * This requires ZERO backend changes — all existing views work unchanged.
 */
(function () {
  'use strict';

  if (!window.fetch) return;

  var CSRF_RE = /csrftoken=([^;]+)/;
  function getCSRF() {
    var m = document.cookie.match(CSRF_RE);
    return m ? m[1] : '';
  }

  // ---- Toast notification (reuses the existing app toast) ----
  function showToast(msg, type) {
    if (typeof window.showAppToast === 'function') {
      window.showAppToast(msg, type || 'info', 3800);
    }
  }

  // ---- Update a DOM section with fresh HTML ----
  function updateSection(selector, html) {
    var wrapper = document.createElement('div');
    wrapper.innerHTML = html;
    var newContent = wrapper.querySelector(selector);
    var oldContent = document.querySelector(selector);
    if (newContent && oldContent) {
      oldContent.replaceWith(newContent);
    }
  }

  // ---- Update the metrics section counts (the [data-count] elements) ----
  function refreshCountAnimations() {
    document.querySelectorAll('[data-count]').forEach(function (el) {
      var target = parseInt(el.textContent.toString().replace(/[^0-9]/g, '')) || 0;
      var dur = 500;
      var start = null;
      function step(ts) {
        if (!start) start = ts;
        var p = Math.min((ts - start) / dur, 1);
        el.textContent = Math.floor(p * target).toLocaleString();
        if (p < 1) requestAnimationFrame(step);
      }
      requestAnimationFrame(step);
    });
  }

  // ---- Re-initialize accordion state ----
  function reinitBookingAccordion() {
    document.querySelectorAll('[data-booking-body].open').forEach(function (el) {
      el.classList.remove('open');
      var h = document.querySelector('[data-booking-header="' + el.getAttribute('data-booking-body') + '"]');
      if (h) h.setAttribute('aria-expanded', 'false');
    });
  }

  // ---- Re-bind AJAX to any new forms that were swapped in ----
  function rebindAjaxForms(container) {
    if (!container) container = document;
    var forms = container.querySelectorAll('form.ajax-form');
    Array.prototype.forEach.call(forms, function (f) {
      if (f.getAttribute('data-ajax-bound') === '1') return;
      f.setAttribute('data-ajax-bound', '1');
      bindAjaxForm(f);
    });
  }

  // ---- Determine which section selectors to update based on action URL ----
  function getRefreshSelectors(action) {
    if (!action) return ['#owner-core-metrics', '#owner-section-bookings', '#owner-ground-availability'];
    if (action.indexOf('/toggle/') !== -1) {
      return ['#owner-ground-availability'];
    }
    if (action.indexOf('/attendance/') !== -1 || action.indexOf('/mark-paid/') !== -1 || action.indexOf('/cancel/') !== -1) {
      return ['#owner-section-bookings', '#owner-core-metrics', '#owner-extended-metrics'];
    }
    if (action.indexOf('/expenses/add') !== -1 || action.indexOf('/expenses/') !== -1) {
      return ['#owner-grounds-performance'];
    }
    return ['#owner-core-metrics', '#owner-section-bookings', '#owner-ground-availability'];
  }

  // ---- Extract messages (Django alerts) from HTML and show as toasts ----
  function extractMessages(html) {
    var wrapper = document.createElement('div');
    wrapper.innerHTML = html;
    var alerts = wrapper.querySelectorAll('.alert');
    Array.prototype.forEach.call(alerts, function (a) {
      var text = a.textContent.trim();
      if (!text) return;
      var cls = a.className || '';
      if (cls.indexOf('success') !== -1) showToast(text, 'success');
      else if (cls.indexOf('danger') !== -1 || cls.indexOf('error') !== -1) showToast(text, 'danger');
      else if (cls.indexOf('warning') !== -1) showToast(text, 'warning');
      else showToast(text, 'info');
    });
  }

  // ---- Bind a single form for AJAX ----
  function bindAjaxForm(form) {
    form.addEventListener('submit', function (e) {
      // Check for data-confirm-message on the submit button
      var submitter = e.submitter || form.querySelector('button[type="submit"], input[type="submit"]');
      var confirmMsg = submitter ? submitter.getAttribute('data-confirm-message') : null;
      if (confirmMsg) {
        // Use the global action confirm modal if available
        if (typeof window.openActionConfirm === 'function') {
          e.preventDefault();
          window.openActionConfirm({
            type: 'form',
            form: form,
            submitter: submitter,
            message: confirmMsg
          });
          return;
        }
        if (!confirm(confirmMsg)) {
          e.preventDefault();
          return;
        }
      }

      // Intercept the form submission
      e.preventDefault();

      var action = form.getAttribute('action');
      var method = (form.getAttribute('method') || 'post').toUpperCase();
      var formData = new FormData(form);

      // If the submitter had a name/value, include it
      if (submitter && submitter.getAttribute('name')) {
        formData.append(submitter.getAttribute('name'), submitter.value || '');
      }

      var refreshSelectors = getRefreshSelectors(action);

      showToast('Processing...', 'info');

      fetch(action, {
        method: method,
        body: formData,
        credentials: 'same-origin',
        headers: {
          'X-CSRFToken': getCSRF()
        },
        // Redirect: follow (default) — the server redirects, we follow,
        // and we get the final page HTML
      }).then(function (res) {
        return res.text();
      }).then(function (html) {
        // Extract Django messages from the response and show as toasts
        extractMessages(html);

        // Update each section
        refreshSelectors.forEach(function (sel) {
          updateSection(sel, html);
        });

        // Re-bind AJAX on any new forms
        rebindAjaxForms(document);
        reinitBookingAccordion();
        refreshCountAnimations();
      }).catch(function (err) {
        showToast(err.message || 'Something went wrong. Please try again.', 'danger');
      });
    });
  }

  // ---- Bind the booking date filter form ----
  function bindBookingDateForm() {
    var form = document.querySelector('.booking-date-form');
    if (!form) return;
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var dateInput = form.querySelector('input[name="date"]');
      if (!dateInput || !dateInput.value) return;
      var date = dateInput.value;
      var url = window.location.pathname + '?date=' + encodeURIComponent(date);
      showToast('Loading bookings...', 'info');
      fetch(url, {
        method: 'GET',
        credentials: 'same-origin',
      }).then(function (res) {
        return res.text();
      }).then(function (html) {
        updateSection('#owner-section-bookings', html);
        rebindAjaxForms(document);
        reinitBookingAccordion();
      }).catch(function () {
        showToast('Failed to load bookings.', 'danger');
      });
    });
  }

  // ---- Init ----
  function init() {
    rebindAjaxForms(document);
    bindBookingDateForm();
  }

  if (document.readyState !== 'loading') {
    init();
  } else {
    document.addEventListener('DOMContentLoaded', init);
  }
})();
