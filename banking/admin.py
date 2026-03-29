from django.contrib import admin
from .models import Bank, PaymentMethod

@admin.register(Bank)
class BankAdmin(admin.ModelAdmin):
  list_display = ('title',)

@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
  list_display = ('seller', 'bank', 'account_number', 'account_type')
