from django.urls import path
from . import views

app_name = 'payments'

urlpatterns = [
    path('links/', views.LinkListView.as_view(), name='link_list'),
    path('links/add/', views.LinkCreateView.as_view(), name='link_create'),
    # Ruta pública de Checkout
    path('pay/<int:pk>/', views.LinkCheckoutView.as_view(), name='link_checkout'),
]
