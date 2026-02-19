setInterval(() => {
  fetch('/notifications/latest/')
    .then(res => res.json())
    .then(data => {
      if (!data) return;
      let toast = document.getElementById("live-popup");
      toast.querySelector(".toast-body").innerText =
        `${data.ground} booked just now (${data.time})`;
      toast.style.display = "block";
      setTimeout(() => toast.style.display = "none", 3000);
    });
}, 15000);
