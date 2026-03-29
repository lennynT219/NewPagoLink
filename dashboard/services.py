from typing import Any, Dict, Optional
from accounts.services import (
    create_user,
    send_activation_email,
    login_redirect_url,
    get_client_ip,
    get_location_from_ip
)
from payments.services import get_seller_stats
from accounts.models import CustomUser

# Re-exponemos las funciones para no romper dashboard/views.py
__all__ = [
    'create_user',
    'send_activation_email',
    'login_redirect_url',
    'get_client_ip',
    'get_location_from_ip',
    'get_dashboard_stats'
]

def get_dashboard_stats(user: CustomUser) -> Optional[Dict[str, Any]]:
  """
  Orquestador: Obtiene las estadísticas desde el servicio de pagos.
  Mantiene la firma original para compatibilidad con la vista.
  """
  try:
    return get_seller_stats(user)
  except Exception:
    return None
