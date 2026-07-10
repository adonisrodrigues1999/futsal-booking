from datetime import datetime, timedelta
from calendar import monthrange

from django.utils import timezone

from .models import Slot


def _build_time_ranges(ground, slot_config=None):
    ranges = []
    if slot_config:
        slot_1_start = slot_config.get("slot_1_start")
        slot_1_end = slot_config.get("slot_1_end")
        slot_2_start = slot_config.get("slot_2_start")
        slot_2_end = slot_config.get("slot_2_end")

        if slot_1_start and slot_1_end:
            ranges.append((slot_1_start, slot_1_end))
        if slot_2_start and slot_2_end:
            ranges.append((slot_2_start, slot_2_end))

    if ranges:
        return ranges

    return [(ground.opening_time, ground.closing_time)]


def ensure_slots_for_ground_date(ground, slot_date, slot_config=None):
    time_ranges = _build_time_ranges(ground, slot_config=slot_config)
    existing_keys = set(
        Slot.objects.filter(
            ground=ground,
            date__in=[slot_date, slot_date + timedelta(days=1)],
        ).values_list("date", "start_time")
    )
    slots_to_create = []

    for start_time, end_time in time_ranges:
        start_dt = datetime.combine(slot_date, start_time)
        end_dt = datetime.combine(slot_date, end_time)
        if end_dt <= start_dt:
            end_dt += timedelta(days=1)

        current = start_dt
        while current < end_dt:
            next_dt = min(current + timedelta(hours=1), end_dt)
            slot_key = (current.date(), current.time())
            if slot_key not in existing_keys:
                slots_to_create.append(
                    Slot(
                        ground=ground,
                        date=current.date(),
                        start_time=current.time(),
                        end_time=next_dt.time(),
                        is_booked=False,
                    )
                )
                existing_keys.add(slot_key)
            current = next_dt

    if slots_to_create:
        Slot.objects.bulk_create(slots_to_create, ignore_conflicts=True)


def create_initial_slots_for_ground(ground, days=14, start_date=None, slot_config=None):
    if start_date is None:
        start_date = timezone.localdate()

    for offset in range(days):
        ensure_slots_for_ground_date(
            ground=ground,
            slot_date=start_date + timedelta(days=offset),
            slot_config=slot_config,
        )


def ensure_next_month_slots_for_ground(ground, slot_config=None, today=None):
    if today is None:
        today = timezone.localdate()

    year = today.year
    month = today.month + 1
    if month == 13:
        month = 1
        year += 1

    days_in_month = monthrange(year, month)[1]
    month_start = datetime(year, month, 1).date()
    month_end = datetime(year, month, days_in_month).date()

    has_slots = Slot.objects.filter(
        ground=ground,
        date__gte=month_start,
        date__lte=month_end,
    ).exists()

    if has_slots:
        return

    for offset in range(days_in_month):
        ensure_slots_for_ground_date(
            ground=ground,
            slot_date=month_start + timedelta(days=offset),
            slot_config=slot_config,
        )
