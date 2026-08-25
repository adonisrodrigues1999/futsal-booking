(() => {
  const dateInput = document.getElementById('login-slots-date');
  const status = document.getElementById('login-slots-status');
  const list = document.getElementById('login-slots-list');
  if (!dateInput || !status || !list) return;

  const localDate = new Date();
  const today = [localDate.getFullYear(), String(localDate.getMonth() + 1).padStart(2, '0'), String(localDate.getDate()).padStart(2, '0')].join('-');
  dateInput.min = today;
  dateInput.value = today;

  function renderSlots(slots, date) {
    list.replaceChildren();
    if (!slots.length) {
      status.textContent = 'No open slots found for this date. Try another date.';
      return;
    }
    status.textContent = `${slots.length} open slot${slots.length === 1 ? '' : 's'} found.`;
    slots.slice(0, 12).forEach((slot) => {
      const link = document.createElement('a');
      link.className = 'list-group-item list-group-item-action d-flex justify-content-between align-items-center gap-2';
      link.href = `/accounts/login/?next=${encodeURIComponent(`/grounds/${slot.ground_id}/?date=${date}`)}`;
      const details = document.createElement('span');
      details.innerHTML = `<strong>${slot.ground_name}</strong><span class="d-block small text-muted">${slot.ground_location} · ${slot.time}</span>`;
      const price = document.createElement('span');
      price.className = 'badge text-bg-success rounded-pill';
      price.textContent = `₹${slot.price}`;
      link.append(details, price);
      list.append(link);
    });
    if (slots.length > 12) {
      const more = document.createElement('div');
      more.className = 'small text-muted pt-2';
      more.textContent = `Showing the first 12 of ${slots.length} open slots. Choose a date to refine the list.`;
      list.append(more);
    }
  }

  async function loadSlots() {
    const date = dateInput.value;
    status.textContent = 'Loading available slots…';
    list.replaceChildren();
    try {
      const response = await fetch(`/slots/search/?date=${encodeURIComponent(date)}`, { credentials: 'same-origin' });
      const payload = await response.json();
      if (!response.ok || !payload.success) throw new Error(payload.error || 'Unable to load slots');
      renderSlots(payload.slots || [], date);
    } catch (_) {
      status.textContent = 'Availability could not be loaded right now. Please try again shortly.';
    }
  }

  dateInput.addEventListener('change', loadSlots);
  loadSlots();
})();
