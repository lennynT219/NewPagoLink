from django.urls import path
from . import views

app_name = 'payments'

urlpatterns = [
    path('links/', views.LinkListView.as_view(), name='link_list'),
    path('links/add/', views.LinkCreateView.as_view(), name='link_create'),
    path('history/', views.PaymentListView.as_view(), name='payment_history'),
    path('history/export/csv/', views.PaymentExportCSVView.as_view(), name='export_csv'),
    path('history/export/excel/', views.PaymentExportExcelView.as_view(), name='export_excel'),
    # Reembolsos
    path('refunds/', views.RefundListView.as_view(), name='refund_list'),
    path('refunds/request/<int:payment_id>/', views.RefundRequestView.as_view(), name='refund_request'),
    # Ruta pública de Checkout
    path('pay/<int:pk>/', views.LinkCheckoutView.as_view(), name='link_checkout'),
    path('pay/result/', views.PaymentResultView.as_view(), name='payment_result'),
]
