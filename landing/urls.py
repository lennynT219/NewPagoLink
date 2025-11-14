from django.urls import path

from . import views

app_name = 'landing'

urlpatterns = [
  path('', views.Index.as_view(), name='index'),
  path('contactenos', views.Contact.as_view(), name='contact'),
  path('precios', views.Pricing.as_view(), name='pricing'),
]
