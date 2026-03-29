import requests
import os
import logging
from typing import Dict, Any, Optional
from decimal import Decimal

logger = logging.getLogger(__name__)

class DatafastClient:
  """
  Cliente técnico para la integración con Datafast (Ecuador).
  Maneja la autenticación y las peticiones a los endpoints de la pasarela.
  """
  
  def __init__(self):
    self.base_url = os.getenv('DATAFAST_URL', 'https://eu-test.oppwa.com/v1/')
    self.auth_token = os.getenv('DATAFAST_AUTH_TOKEN', 'Bearer OGE4Mjk0MTg1YTY1YmY1ZTAxNWE2YzhjNzI4YzBkOTV8YmZxR3F3UTMyWA==')
    self.entity_id = os.getenv('DATAFAST_ENTITY_ID', '8ac7a4c872ea49770172ed7feaf7174e')

  def _get_headers(self) -> Dict[str, str]:
    return {
      'Authorization': self.auth_token,
      'Content-Type': 'application/x-www-form-urlencoded'
    }

  def prepare_checkout(self, amount: Decimal, currency: str, transaction_id: str, customer_data: Dict[str, Any]) -> Optional[str]:
    """
    Inicia una sesión de checkout en Datafast y devuelve el ID de la sesión.
    """
    url = f"{self.base_url}checkouts"
    
    # Formatear el monto a 2 decimales string
    formatted_amount = "{:.2f}".format(amount)
    
    payload = {
      'entityId': self.entity_id,
      'amount': formatted_amount,
      'currency': currency,
      'paymentType': 'DB', # Debit/Purchase
      'merchantTransactionId': transaction_id,
      'customer.givenName': customer_data.get('first_name', 'Cliente'),
      'customer.surname': customer_data.get('last_name', 'PagoLink'),
      'customer.email': customer_data.get('email', ''),
      'customer.identificationDocType': 'IDCARD',
      'billing.country': 'EC',
      # Parámetros adicionales requeridos por Datafast Ecuador
      'customParameters[SHOPPER_MID]': os.getenv('DATAFAST_MID', '1000000505'),
      'customParameters[SHOPPER_TID]': os.getenv('DATAFAST_TID', 'PD100406'),
    }

    try:
      response = requests.post(url, data=payload, headers=self._get_headers(), timeout=10)
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
    """
    Consulta el resultado de una transacción usando el resourcePath devuelto por el widget.
    """
    url = f"https://eu-test.oppwa.com{resource_path}"
    params = {'entityId': self.entity_id}
    
    try:
      response = requests.get(url, params=params, headers=self._get_headers(), timeout=10)
      response.raise_for_status()
      return response.json()
    except Exception as e:
      logger.exception(f"Error checking payment status: {str(e)}")
      return {'result': {'code': 'ERROR', 'description': str(e)}}

  def refund_payment(self, transaction_id: str, amount: Decimal) -> Dict[str, Any]:
    """
    Solicita un reembolso a la pasarela.
    """
    url = f"{self.base_url}payments/{transaction_id}"
    params = {
        'entityId': self.entity_id,
        'amount': "{:.2f}".format(amount),
        'currency': 'USD',
        'paymentType': 'RF' # Refund
    }
    
    try:
      response = requests.delete(url, params=params, headers=self._get_headers(), timeout=10)
      return response.json()
    except Exception as e:
      logger.exception(f"Error processing refund: {str(e)}")
      return {'result': {'code': 'ERROR', 'description': str(e)}}
