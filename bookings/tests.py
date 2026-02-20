from django.test import TestCase
from datetime import time, date

from accounts.models import User
from grounds.models import Ground

from .models import Slot
from .slot_generation import create_initial_slots_for_ground, ensure_slots_for_ground_date


class SlotGenerationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email='owner@example.com',
            phone_number='9999999999',
            name='Owner',
            password='password123',
            role='owner',
            email_verified=True,
        )

    def test_create_initial_slots_uses_opening_and_closing_times(self):
        ground = Ground.objects.create(
            name='Arena 1',
            location='City',
            owner=self.owner,
            day_price=500,
            night_price=1000,
            opening_time=time(6, 0),
            closing_time=time(9, 0),
        )

        create_initial_slots_for_ground(
            ground=ground,
            days=2,
            start_date=date(2026, 2, 19),
        )

        self.assertEqual(Slot.objects.filter(ground=ground).count(), 6)

    def test_create_initial_slots_handles_cross_midnight_ranges(self):
        ground = Ground.objects.create(
            name='Arena 2',
            location='City',
            owner=self.owner,
            day_price=500,
            night_price=1000,
            opening_time=time(6, 0),
            closing_time=time(22, 0),
        )

        create_initial_slots_for_ground(
            ground=ground,
            days=1,
            start_date=date(2026, 2, 19),
            slot_config={
                'slot_1_start': time(18, 0),
                'slot_1_end': time(1, 0),
                'slot_2_start': None,
                'slot_2_end': None,
            },
        )

        self.assertEqual(Slot.objects.filter(ground=ground).count(), 7)
        self.assertTrue(
            Slot.objects.filter(
                ground=ground,
                date=date(2026, 2, 20),
                start_time=time(0, 0),
            ).exists()
        )

    def test_ensure_slots_for_ground_date_is_idempotent(self):
        ground = Ground.objects.create(
            name='Arena 3',
            location='City',
            owner=self.owner,
            day_price=500,
            night_price=1000,
            opening_time=time(6, 0),
            closing_time=time(8, 0),
        )

        ensure_slots_for_ground_date(ground=ground, slot_date=date(2026, 2, 19))
        ensure_slots_for_ground_date(ground=ground, slot_date=date(2026, 2, 19))

        self.assertEqual(Slot.objects.filter(ground=ground).count(), 2)
