from django.apps import AppConfig
from django.contrib.auth.apps import AuthConfig


class DjangoAuthConfig(AuthConfig):
    verbose_name = "Autenticação e acessos"


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    verbose_name = "Contas e segurança"
