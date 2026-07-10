from django.db import transaction

from accounts.models import User

from .models import RewardTransaction


BOOKING_POINTS = 5
REFERRAL_BOOKING_POINTS = 20
REFERRAL_TOURNAMENT_POINTS = 20
POINTS_FOR_FREE_BOOKING = 100


def _record_transaction(user, reason, points, booking=None, notes=''):
    RewardTransaction.objects.create(
        user=user,
        reason=reason,
        points=points,
        booking=booking,
        notes=notes,
    )


def _rollover_points(user):
    while user.loyalty_points >= POINTS_FOR_FREE_BOOKING:
        user.loyalty_points -= POINTS_FOR_FREE_BOOKING
        user.free_booking_credits += 1
        _record_transaction(
            user,
            'LOYALTY_REDEMPTION',
            POINTS_FOR_FREE_BOOKING,
            notes='Converted 100 loyalty points into one free booking credit.',
        )


@transaction.atomic
def award_booking_rewards(booking):
    user = booking.user
    if not user:
        return

    user = User.objects.select_for_update().get(id=user.id)
    user.booking_count += 1
    user.loyalty_points += BOOKING_POINTS
    booking.reward_points_earned = BOOKING_POINTS

    if booking.loyalty_reward_redeemed:
        booking.reward_discount_amount = booking.total_amount

    _record_transaction(
        user,
        'BOOKING',
        BOOKING_POINTS,
        booking=booking,
        notes='Base booking reward.',
    )

    if user.referred_by_id and user.booking_count == 1:
        referrer = User.objects.select_for_update().filter(id=user.referred_by_id).first()
        if referrer:
            referrer.loyalty_points += REFERRAL_BOOKING_POINTS
            _record_transaction(
                referrer,
                'FIRST_BOOKING_REFERRAL',
                REFERRAL_BOOKING_POINTS,
                booking=booking,
                notes=f'Referral reward for {user.name} first booking.',
            )
            referrer.save(update_fields=['loyalty_points'])

            user.loyalty_points += REFERRAL_BOOKING_POINTS
            _record_transaction(
                user,
                'FIRST_BOOKING_REFERRAL',
                REFERRAL_BOOKING_POINTS,
                booking=booking,
                notes='Referral bonus for first booking.',
            )

    _rollover_points(user)
    user.save(update_fields=['booking_count', 'loyalty_points', 'free_booking_credits'])
    booking.save(update_fields=['reward_points_earned', 'reward_discount_amount'])


@transaction.atomic
def award_tournament_registration_rewards(registration):
    user = registration.user
    if not user:
        return

    user = User.objects.select_for_update().get(id=user.id)
    first_registration = registration.tournament.registrations.filter(user=user, status='REGISTERED').count() == 1

    if user.referred_by_id and first_registration and not registration.referral_bonus_applied:
        referrer = User.objects.select_for_update().filter(id=user.referred_by_id).first()
        if referrer:
            referrer.loyalty_points += REFERRAL_TOURNAMENT_POINTS
            _record_transaction(
                referrer,
                'FIRST_TOURNAMENT_REGISTRATION',
                REFERRAL_TOURNAMENT_POINTS,
                notes=f'Referral reward for {user.name} tournament registration.',
            )
            referrer.save(update_fields=['loyalty_points'])

            user.loyalty_points += REFERRAL_TOURNAMENT_POINTS
            _record_transaction(
                user,
                'FIRST_TOURNAMENT_REGISTRATION',
                REFERRAL_TOURNAMENT_POINTS,
                notes='Referral bonus for tournament registration.',
            )
            registration.referral_bonus_applied = True

    _rollover_points(user)
    user.save(update_fields=['loyalty_points', 'free_booking_credits'])
    registration.save(update_fields=['referral_bonus_applied'])


@transaction.atomic
def redeem_free_booking_credit(user, booking):
    user = User.objects.select_for_update().get(id=user.id)
    if user.free_booking_credits <= 0:
        return False

    user.free_booking_credits -= 1
    booking.loyalty_reward_redeemed = True
    booking.reward_discount_amount = booking.total_amount
    _record_transaction(
        user,
        'LOYALTY_REDEMPTION',
        0,
        booking=booking,
        notes='Redeemed one free booking credit.',
    )
    user.save(update_fields=['free_booking_credits'])
    booking.save(update_fields=['loyalty_reward_redeemed', 'reward_discount_amount'])
    return True
