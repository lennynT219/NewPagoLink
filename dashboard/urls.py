from django.urls import path, re_path
from . import views

app_name = 'dashboard'

urlpatterns = [
  path('registrarse', views.Register.as_view(), name='register'),
  re_path(
    r'^activar/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z\-]+)/$',
    views.ActivateAccount.as_view(),
    name='activate',
  ),
  path('iniciar-sesion', views.Login.as_view(), name='login'),
  path('restablecer-contrasena', views.ResetPassword.as_view(), name='reset_password'),
]
