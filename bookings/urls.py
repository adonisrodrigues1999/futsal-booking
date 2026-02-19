from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('customer-home/', views.home, name='customer_home'),

    path('grounds/', views.ground_list),
    path('grounds/<int:ground_id>/', views.ground_slots),

    path('book/<int:slot_id>/', views.book_slot, name='book_slot'),
    path('cancel/<uuid:booking_id>/', views.cancel_booking, name='cancel_booking'),
    path('my-bookings/', views.my_bookings),

    path('dashboard/owner/', views.owner_dashboard, name='owner_dashboard'),
    path('owner/cancel/<uuid:booking_id>/', views.owner_cancel_booking, name='owner_cancel_booking'),
    path('owner/manual/', views.owner_manual_booking, name='owner_manual_booking'),
    path('owner/manual-booking/', views.owner_manual_booking, name='owner_manual_booking_alias'),

    path('notifications/latest/', views.latest_notification),
]
