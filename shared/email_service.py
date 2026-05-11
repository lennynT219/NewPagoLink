import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


def send_html_email(
    subject: str,
    recipient_list: list[str],
    html_template_path: str,
    context: dict,
    from_email: str | None = None,
) -> bool:
    """Sends an HTML email with plaintext fallback using Django's email system.

    Args:
        subject: The email subject.
        recipient_list: List of recipient email addresses.
        html_template_path: Path to the HTML template (Django template system).
        context: Context for template rendering.
        from_email: Sender. Defaults to settings.DEFAULT_FROM_EMAIL.

    Returns:
        True if sent successfully, False if any error occurred.
    """
    from_email = from_email or settings.DEFAULT_FROM_EMAIL
    try:
        html_content = render_to_string(html_template_path, context)
        text_content = strip_tags(html_content)
        msg = EmailMultiAlternatives(subject, text_content, from_email, recipient_list)
        msg.attach_alternative(html_content, 'text/html')
        msg.send()
        return True
    except Exception as e:
        logger.error('Failed to send email to %s: %s', recipient_list, e)
        return False
