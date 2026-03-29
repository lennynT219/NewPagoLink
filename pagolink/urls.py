from django.contrib import admin
from django.urls import include, path

urlpatterns = [
  path('admin/', admin.site.urls),
  path('', include('landing.urls')),
  path('dashboard/', include('dashboard.urls')),
  path('accounts/', include('accounts.urls')),
  path('payments/', include('payments.urls')),
  path('banking/', include('banking.urls')),
  path('gateways/', include('gateways.urls')),
]
