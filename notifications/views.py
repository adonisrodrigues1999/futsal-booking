from bookings.models import Booking
from django.http import JsonResponse

def latest_booking(request):
    b = Booking.objects.filter(status='BOOKED').latest('created_at')
    return JsonResponse({
        'ground': b.ground.name,
        'time': str(b.start_time)
    })
