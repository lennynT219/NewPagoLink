from django.urls import path
from . import views

app_name = 'banking'

urlpatterns = [
    path('config/', views.PaymentMethodView.as_view(), name='config'),
    path('admin/bancos/', views.BankListView.as_view(), name='bank_list'),
    path('admin/bancos/nuevo/', views.BankCreateView.as_view(), name='bank_create'),
]
