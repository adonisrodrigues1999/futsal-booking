(() => {
  const dateInput = document.getElementById('login-slots-date');
  const groundSelect = document.getElementById('login-slots-ground');
  const status = document.getElementById('login-slots-status');
  const list = document.getElementById('login-slots-list');
  if (!dateInput || !groundSelect || !status || !list) return;
  let availableSlots = [];

  const localDate = new Date();
  const today = [localDate.getFullYear(), String(localDate.getMonth() + 1).padStart(2, '0'), String(localDate.getDate()).padStart(2, '0')].join('-');
  dateInput.min = today;
  dateInput.value = today;

  function populateGrounds(slots) {
    const grounds = new Map();
    slots.forEach((slot) => {
      if (!grounds.has(String(slot.ground_id))) {
        grounds.set(String(slot.ground_id), {
          name: slot.ground_name,
          location: slot.ground_location,
        });
      }
    });
    groundSelect.replaceChildren();
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = grounds.size ? 'Choose a ground' : 'No grounds available';
    groundSelect.append(placeholder);
    grounds.forEach((ground, id) => {
      const option = document.createElement('option');
      option.value = id;
      option.textContent = `${ground.name} — ${ground.location}`;
      groundSelect.append(option);
    });
    groundSelect.disabled = !grounds.size;
  }

  function renderSlots() {
    list.replaceChildren();
    const groundId = groundSelect.value;
    if (!groundId) {
      status.textContent = availableSlots.length ? 'Choose a ground to view its available slots.' : 'No open slots found for this date. Try another date.';
      return;
    }
    const slots = availableSlots.filter((slot) => String(slot.ground_id) === groundId);
    const date = dateInput.value;
    if (!slots.length) {
      status.textContent = 'No open slots found for this ground on this date.';
      return;
    }
    status.textContent = `${slots.length} open slot${slots.length === 1 ? '' : 's'} available.`;
    slots.forEach((slot) => {
      const column = document.createElement('div');
      column.className = 'col';
      const link = document.createElement('a');
      link.className = 'btn btn-outline-success w-100 text-start d-flex justify-content-between align-items-center gap-2';
      link.href = `/accounts/login/?next=${encodeURIComponent(`/grounds/${slot.ground_id}/?date=${date}`)}`;
      const details = document.createElement('span');
      const slotTime = document.createElement('strong');
      slotTime.textContent = slot.time;
      const slotMeta = document.createElement('span');
      slotMeta.className = 'd-block small text-muted';
      slotMeta.textContent = 'Book this slot';
      details.append(slotTime, slotMeta);
      const price = document.createElement('span');
      price.className = 'badge text-bg-success rounded-pill';
      price.textContent = `₹${slot.price}`;
      link.append(details, price);
      column.append(link);
      list.append(column);
    });
  }

  async function loadSlots() {
    const date = dateInput.value;
    status.textContent = 'Loading available slots…';
    list.replaceChildren();
    groundSelect.disabled = true;
    groundSelect.replaceChildren();
    const loading = document.createElement('option');
    loading.textContent = 'Loading grounds…';
    groundSelect.append(loading);
    try {
      const response = await fetch(`/slots/search/?date=${encodeURIComponent(date)}`, { credentials: 'same-origin' });
      const payload = await response.json();
      if (!response.ok || !payload.success) throw new Error(payload.error || 'Unable to load slots');
      availableSlots = payload.slots || [];
      populateGrounds(availableSlots);
      renderSlots();
    } catch (_) {
      availableSlots = [];
      groundSelect.disabled = true;
      groundSelect.replaceChildren();
      const unavailable = document.createElement('option');
      unavailable.textContent = 'Grounds unavailable';
      groundSelect.append(unavailable);
      status.textContent = 'Availability could not be loaded right now. Please try again shortly.';
    }
  }

  dateInput.addEventListener('change', loadSlots);
  groundSelect.addEventListener('change', renderSlots);
  loadSlots();
})();
