from django.db import transaction

from accounts.models import User
from bookings.models import Booking, Slot, OwnerExpense
from grounds.models import Ground, Tournament, TournamentRegistration, GroundReview


DEMO_PREFIXES = ('Demo', 'Goa')


@transaction.atomic
def purge_demo_data():
    GroundReview.objects.filter(headline__startswith=DEMO_PREFIXES[0]).delete()
    GroundReview.objects.filter(headline__startswith=DEMO_PREFIXES[1]).delete()
    TournamentRegistration.objects.filter(team_name__startswith=DEMO_PREFIXES[0]).delete()
    TournamentRegistration.objects.filter(team_name__startswith=DEMO_PREFIXES[1]).delete()
    Tournament.objects.filter(title__startswith=DEMO_PREFIXES[0]).delete()
    Tournament.objects.filter(title__startswith=DEMO_PREFIXES[1]).delete()
    OwnerExpense.objects.filter(title__startswith=DEMO_PREFIXES[0]).delete()
    OwnerExpense.objects.filter(title__startswith=DEMO_PREFIXES[1]).delete()
    Booking.objects.filter(customer_name__icontains=DEMO_PREFIXES[0]).delete()
    Booking.objects.filter(customer_name__icontains=DEMO_PREFIXES[1]).delete()
    Slot.objects.filter(ground__name__startswith=DEMO_PREFIXES[0]).delete()
    Slot.objects.filter(ground__name__startswith=DEMO_PREFIXES[1]).delete()
    Ground.objects.filter(name__startswith=DEMO_PREFIXES[0]).delete()
    Ground.objects.filter(name__startswith=DEMO_PREFIXES[1]).delete()
    User.objects.filter(email__startswith='demo_').delete()
