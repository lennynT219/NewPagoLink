from django.views.generic import TemplateView


# Create your views here.
class Index(TemplateView):
  template_name = 'index.html'


class Contact(TemplateView):
  template_name = 'contact.html'


class Pricing(TemplateView):
  template_name = 'pricing.html'
