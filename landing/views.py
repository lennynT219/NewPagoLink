from django.views.generic import TemplateView


# Create your views here.
class Index(TemplateView):
  template_name = 'landing/index.html'


class Contact(TemplateView):
  template_name = 'landing/contact.html'


class Pricing(TemplateView):
  template_name = 'landing/pricing.html'
