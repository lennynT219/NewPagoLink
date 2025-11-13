from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
  path('iniciar-sesion', views.Login.as_view(), name='login'),
  path('registrarse', views.Register.as_view(), name='register'),
  path('restablecer-contrasena', views.ResetPassword.as_view(), name='reset_password'),
]
