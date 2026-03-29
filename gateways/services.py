import requests
import logging
from typing import Dict, Any, Optional
from decimal import Decimal
from django.conf import settings

logger = logging.getLogger(__name__)

class DatafastClient:
  """
  Cliente técnico para la integración con Datafast (Ecuador) - Fase 2.
  Implementa el desglose de impuestos y parámetros de seguridad obligatorios.
  """
  
  def __init__(self):
    self.base_url = settings.DATAFAST_BASE_URL
    self.auth_token = settings.DATAFAST_AUTH_TOKEN
    self.entity_id = settings.DATAFAST_ENTITY_ID
    self.mid = settings.DATAFAST_MID
    self.tid = settings.DATAFAST_TID
    self.test_mode = settings.DATAFAST_TEST_MODE

  def _get_headers(self) -> Dict[str, str]:
    return {
      'Authorization': self.auth_token,
      'Content-Type': 'application/x-www-form-urlencoded'
    }

  def prepare_checkout(self, amount: Decimal, subtotal: Decimal, igv: Decimal, 
                       include_igv: bool, transaction_id: str, 
                       customer_data: Dict[str, Any], client_ip: str) -> Optional[str]:
    """
    Inicia una sesión de checkout (Fase 2) con desglose de impuestos.
    """
    url = f"{self.base_url}checkouts"
    
    # Lógica de Impuestos según Datafast Ecuador
    # SHOPPER_VAL_BASEIMP: Base que grava IVA
    # SHOPPER_VAL_BASE0: Base que NO grava IVA
    # SHOPPER_VAL_IVA: Valor del IVA calculado
    
    if igv > 0:
      base_imp = subtotal
      base_0 = Decimal('0.00')
      val_iva = igv
    else:
      base_imp = Decimal('0.00')
      base_0 = subtotal
      val_iva = Decimal('0.00')

    payload = {
      'entityId': self.entity_id,
      'amount': "{:.2f}".format(amount),
      'currency': 'USD',
      'paymentType': 'DB',
      'merchantTransactionId': transaction_id,
      
      # Datos del Cliente (Obligatorios Fase 2)
      'customer.givenName': customer_data.get('first_name', 'Cliente'),
      'customer.surname': customer_data.get('last_name', 'PagoLink'),
      'customer.email': customer_data.get('email', ''),
      'customer.ip': client_ip,
      'customer.identificationDocType': 'IDCARD',
      'customer.identificationDocId': str(customer_data.get('identify', ''))[:10], # Max 10 caracteres
      'customer.phone': customer_data.get('phone', ''),
      
      # Direcciones (Obligatorios)
      'billing.street1': 'Ecuador Main Street',
      'billing.country': 'EC',
      'shipping.street1': 'Ecuador Delivery Street',
      'shipping.country': 'EC',

      # Parámetros Personalizados Datafast
      'customParameters[SHOPPER_MID]': self.mid,
      'customParameters[SHOPPER_TID]': self.tid,
      'customParameters[SHOPPER_VERSIONDF]': '2',
      
      # Parámetros de Riesgo
      'risk.parameters[USER_DATA2]': 'PagoLinkExpress',
    }

    # Modo de Prueba (Comentado si causa conflicto con este MID)
    # if self.test_mode:
    #   payload['testMode'] = self.test_mode

    try:
      response = requests.post(url, data=payload, headers=self._get_headers(), timeout=15)
      response.raise_for_status()
      data = response.json()
      
      if 'id' in data:
        return data['id']
      
      logger.error(f"Datafast checkout error: {data}")
      return None
      
    except Exception as e:
      logger.exception(f"Error connecting to Datafast: {str(e)}")
      return None

  def get_payment_status(self, resource_path: str) -> Dict[str, Any]:
    """Consulta el resultado de la transacción."""
    # Evitar duplicación de /v1/ si resource_path ya lo incluye
    clean_base = self.base_url.replace('/v1/', '')
    url = f"{clean_base.rstrip('/')}{resource_path}"
    params = {'entityId': self.entity_id}
    
    try:
      response = requests.get(url, params=params, headers=self._get_headers(), timeout=10)
      response.raise_for_status()
      return response.json()
    except Exception as e:
      logger.exception(f"Error checking payment status: {str(e)}")
      return {'result': {'code': 'ERROR', 'description': str(e)}}

  def refund_payment(self, transaction_id: str, amount: Decimal) -> Dict[str, Any]:
    """Solicita un reembolso."""
    url = f"{self.base_url}payments/{transaction_id}"
    payload = {
        'entityId': self.entity_id,
        'amount': "{:.2f}".format(amount),
        'currency': 'USD',
        'paymentType': 'RF'
    }
    if self.test_mode:
      payload['testMode'] = self.test_mode
    
    try:
      response = requests.delete(url, data=payload, headers=self._get_headers(), timeout=10)
      return response.json()
    except Exception as e:
      logger.exception(f"Error processing refund: {str(e)}")
      return {'result': {'code': 'ERROR', 'description': str(e)}}
