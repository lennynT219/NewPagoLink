from django.urls import path

from . import views

app_name = 'landing'

urlpatterns = [
  path('', views.index, name='index'),
  path('contactenos', views.contact, name='contact'),
  path('precios', views.pricing, name='pricing'),
]
