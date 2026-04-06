from django.contrib import admin
from .models import Link, Payment, Refund

@admin.register(Link)
class LinkAdmin(admin.ModelAdmin):
  list_display = ('description', 'seller', 'amount', 'active', 'unique', 'created_at')
  list_filter = ('active', 'unique', 'created_at')
  search_fields = ('description', 'seller__user__username')

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
  list_display = ('first_name', 'last_name', 'amount', 'status', 'transaction_id')
  list_filter = ('status', 'state')
  search_fields = ('first_name', 'last_name', 'transaction_id', 'email')

@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
  list_display = ('payment', 'seller', 'amount', 'status', 'created_at')
  list_filter = ('status',)
