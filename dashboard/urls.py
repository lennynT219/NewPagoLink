from django.urls import path, re_path, reverse_lazy
from django.contrib.auth import views as auth_views
from accounts.views import ProfileUpdateView
from . import views

app_name = 'dashboard'

urlpatterns = [
  path('registrarse', views.Register.as_view(), name='register'),
  path('perfil/', ProfileUpdateView.as_view(), name='user-update'),
  re_path(
    r'^activar/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z\-]+)/$',
    views.ActivateAccount.as_view(),
    name='activate',
  ),
  path('iniciar-sesion', views.Login.as_view(), name='login'),
  
  # Flujo de Recuperación de Contraseña
  path('password-reset/', 
       auth_views.PasswordResetView.as_view(template_name='dashboard/registration/password_reset_form.html', email_template_name='dashboard/registration/password_reset_email.html', success_url=reverse_lazy('dashboard:password_reset_done')), 
       name='password_reset'),
  path('password-reset/done/', 
       auth_views.PasswordResetDoneView.as_view(template_name='dashboard/registration/password_reset_done.html'), 
       name='password_reset_done'),
  path('password-reset-confirm/<uidb64>/<token>/', 
       auth_views.PasswordResetConfirmView.as_view(template_name='dashboard/registration/password_reset_confirm.html', success_url=reverse_lazy('dashboard:password_reset_complete')), 
       name='password_reset_confirm'),
  path('password-reset-complete/', 
       auth_views.PasswordResetCompleteView.as_view(template_name='dashboard/registration/password_reset_complete.html'), 
       name='password_reset_complete'),

  path('contrato', views.ContractAccept.as_view(), name='contract'),
  path('', views.Dashboard.as_view(), name='dashboard'),
  path('logout', views.Logout.as_view(), name='logout'),
  path('restablecer-contrasena', views.ResetPassword.as_view(), name='reset_password'),
]
