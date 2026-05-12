from django.urls import path
from . import views

app_name = 'banking'

urlpatterns = [
    path('config/', views.PaymentMethodView.as_view(), name='config'),
    path('admin/bancos/', views.BankListView.as_view(), name='bank_list'),
    path('admin/bancos/nuevo/', views.BankCreateView.as_view(), name='bank_create'),
    path('admin/bancos/<int:pk>/eliminar/', views.BankDeleteView.as_view(), name='bank_delete'),
    
    # Desembolsos
    path('retirar/', views.DisbursementCreateView.as_view(), name='disbursement_create'),
    path('historial/', views.DisbursementListView.as_view(), name='disbursement_list'),
    
    # Admin Desembolsos
    path('admin/desembolsos/', views.AdminDisbursementListView.as_view(), name='admin_disbursement_list'),
    path('admin/desembolsos/<int:pk>/procesar/', views.AdminDisbursementProcessView.as_view(), name='admin_disbursement_process'),
]
