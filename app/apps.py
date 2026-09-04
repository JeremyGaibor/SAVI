from django.apps import AppConfig as DjangoAppConfig


class MainAppConfig(DjangoAppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app'
