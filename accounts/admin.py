from django.contrib import admin

from .models import Contract, ContractAcceptance, CustomUser


@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
  list_display = ('user', 'identification', 'phone', 'state', 'email_active')
  search_fields = ('user__username', 'identification', 'user__email')


@admin.register(ContractAcceptance)
class ContractAcceptanceAdmin(admin.ModelAdmin):
  list_display = ('seller', 'version', 'text_hash', 'accepted_at', 'ip', 'city')
  readonly_fields = ('seller', 'version', 'text_hash', 'text_snapshot', 'accepted_at', 'ip', 'city')
  search_fields = ('seller__user__username', 'version', 'text_hash')

  def has_add_permission(self, request):
    return False

  def has_change_permission(self, request, obj=None):
    return False

  def has_delete_permission(self, request, obj=None):
    return False


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
  list_display = ('seller', 'ip', 'city', 'created_at')
  readonly_fields = ('created_at',)
