from datetime import datetime, timedelta

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

    for start_time, end_time in time_ranges:
        start_dt = datetime.combine(slot_date, start_time)
        end_dt = datetime.combine(slot_date, end_time)
        if end_dt <= start_dt:
            end_dt += timedelta(days=1)

        current = start_dt
        while current < end_dt:
            next_dt = min(current + timedelta(hours=1), end_dt)
            Slot.objects.get_or_create(
                ground=ground,
                date=current.date(),
                start_time=current.time(),
                defaults={
                    "end_time": next_dt.time(),
                    "is_booked": False,
                },
            )
            current = next_dt


def create_initial_slots_for_ground(ground, days=14, start_date=None, slot_config=None):
    if start_date is None:
        start_date = timezone.localdate()

    for offset in range(days):
        ensure_slots_for_ground_date(
            ground=ground,
            slot_date=start_date + timedelta(days=offset),
            slot_config=slot_config,
        )
