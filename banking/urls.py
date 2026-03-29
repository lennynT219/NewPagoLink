from django.urls import path
from . import views

app_name = 'banking'

urlpatterns = [
    path('config/', views.PaymentMethodView.as_view(), name='config'),
]
