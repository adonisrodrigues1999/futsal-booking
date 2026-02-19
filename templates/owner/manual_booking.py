{% extends 'base/base.html' %}
{% block content %}

<h4>Manual Booking</h4>

<form method="post">
  {% csrf_token %}

  <select name="slot" class="form-control mb-2" required>
    {% for slot in slots %}
      <option value="{{ slot.id }}">
        {{ slot.ground.name }} | {{ slot.start_time|date:"H:i" }}
      </option>
    {% endfor %}
  </select>

  <input type="text" name="name" placeholder="Customer Name" class="form-control mb-2" required>
  <input type="text" name="phone" placeholder="Phone Number" class="form-control mb-2" required>

  <button class="btn btn-warning">Confirm Manual Booking</button>
</form>

{% endblock %}
