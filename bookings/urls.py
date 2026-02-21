from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('customer-home/', views.home, name='customer_home'),

    path('grounds/', views.ground_list),
    path('grounds/<int:ground_id>/', views.ground_slots),
    path('grounds/<int:ground_id>/image/', views.ground_image, name='ground_image'),

    path('book/<int:slot_id>/', views.book_slot, name='book_slot'),
    path('payments/razorpay/create-order/', views.create_razorpay_order, name='create_razorpay_order'),
    path('payments/razorpay/verify-and-book/', views.verify_razorpay_payment_and_book, name='verify_razorpay_payment_and_book'),
    path('payments/razorpay/webhook/', views.razorpay_webhook, name='razorpay_webhook'),
    path('cancel/<uuid:booking_id>/', views.cancel_booking, name='cancel_booking'),
    path('my-bookings/', views.my_bookings),

    path('dashboard/owner/', views.owner_dashboard, name='owner_dashboard'),
    path('owner/cancel/<uuid:booking_id>/', views.owner_cancel_booking, name='owner_cancel_booking'),
    path('owner/manual/', views.owner_manual_booking, name='owner_manual_booking'),
    path('owner/manual-booking/', views.owner_manual_booking, name='owner_manual_booking_alias'),

    path('notifications/latest/', views.latest_notification),
    path('dashboard/admin/invoices/', views.admin_invoices, name='admin_invoices'),
    path('dashboard/admin/invoices/mark-paid/', views.mark_invoice_paid, name='mark_invoice_paid'),
    path('dashboard/admin/invoices/mark-unpaid/', views.mark_invoice_unpaid, name='mark_invoice_unpaid'),
    path('dashboard/admin/invoices/export/', views.export_invoices_csv, name='export_invoices_csv'),
    path('dashboard/admin/invoices/export-bookings/', views.export_bookings_csv, name='export_bookings_csv'),
    path('dashboard/admin/invoices/pay/<int:invoice_id>/', views.pay_invoice, name='pay_invoice'),
    path('dashboard/admin/invoices/webhook/', views.stripe_webhook, name='stripe_webhook'),
]
