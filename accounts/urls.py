from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.register, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('verify-email/<str:token>/', views.verify_email, name='verify_email'),
    path('password-reset/', views.password_reset_request, name='password_reset'),
    path('password-reset/done/', views.password_reset_done, name='password_reset_done'),
    path('password-reset-confirm/<uidb64>/<token>/', views.password_reset_confirm, name='password_reset_confirm'),
    path('password-reset-complete/', views.password_reset_complete, name='password_reset_complete'),
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('create-ground-owner/', views.create_ground_owner, name='create_ground_owner'),
    path('create-ground/<int:owner_id>/', views.create_ground, name='create_ground'),
    path('customer-dashboard/', views.customer_dashboard, name='customer_dashboard'),
    path('owner-dashboard/', views.owner_dashboard, name='owner_dashboard'),
]