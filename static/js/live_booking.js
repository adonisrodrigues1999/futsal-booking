(() => {
  const POLL_MS = 30 * 60 * 1000; // 30 minutes
  const LAST_SEEN_KEY = 'live_booking_last_seen_event_id';

  function showLiveToast(message) {
    const toast = document.getElementById('live-popup');
    if (!toast) return;
    const body = toast.querySelector('.toast-body');
    if (!body) return;

    body.innerText = message;
    toast.style.display = 'block';
    setTimeout(() => {
      toast.style.display = 'none';
    }, 3500);
  }

  function checkLatestBookingNotification() {
    fetch('/notifications/latest/', { credentials: 'same-origin' })
      .then((res) => res.json())
      .then((data) => {
        if (!data || !data.event_id) return;

        const lastSeen = localStorage.getItem(LAST_SEEN_KEY);
        if (lastSeen === data.event_id) return;

        // Format is strictly hours and minutes from backend (HH:MM)
        showLiveToast(`${data.ground} booked at ${data.time}`);
        localStorage.setItem(LAST_SEEN_KEY, data.event_id);
      })
      .catch(() => {
        // Ignore polling errors silently.
      });
  }

  // Initial check, then poll every 30 minutes for all users.
  checkLatestBookingNotification();
  setInterval(checkLatestBookingNotification, POLL_MS);
})();
