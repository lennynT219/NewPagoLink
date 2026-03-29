from django.contrib import admin
from .models import CustomUser, Contract

@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
  list_display = ('user', 'identification', 'phone', 'state', 'email_active')
  search_fields = ('user__username', 'identification', 'user__email')

@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
  list_display = ('seller', 'ip', 'city', 'created_at')
  readonly_fields = ('created_at',)
