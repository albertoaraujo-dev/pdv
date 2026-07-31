from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class ActiveQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)

    def for_organization(self, organization):
        return self.filter(organization=organization)


class Organization(models.Model):
    name = models.CharField("nome", max_length=160)
    legal_name = models.CharField("razão social", max_length=200, blank=True)
    document = models.CharField("documento", max_length=32, unique=True, blank=True, null=True)
    is_active = models.BooleanField("ativo", default=True)
    created_at = models.DateTimeField("criado em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    objects = ActiveQuerySet.as_manager()

    class Meta:
        verbose_name = "organização"
        verbose_name_plural = "organizações"
        ordering = ["name"]
        indexes = [models.Index(fields=["is_active", "name"])]

    def __str__(self):
        return self.name


class Store(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="stores", verbose_name="organização")
    name = models.CharField("nome", max_length=160)
    code = models.CharField("código", max_length=32)
    is_active = models.BooleanField("ativo", default=True)
    created_at = models.DateTimeField("criado em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    objects = ActiveQuerySet.as_manager()

    class Meta:
        verbose_name = "loja"
        verbose_name_plural = "lojas"
        ordering = ["organization__name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "code"],
                name="unique_store_code_per_organization",
                violation_error_message="Já existe uma loja com este código nesta organização.",
            )
        ]
        indexes = [models.Index(fields=["organization", "is_active"])]

    def __str__(self):
        return f"{self.organization} - {self.name}"


class UserProfile(models.Model):
    class Role(models.TextChoices):
        ADMIN = "admin", "Administrador"
        MANAGER = "manager", "Gerente"
        OPERATOR = "operator", "Operador"
        CASHIER = "cashier", "Caixa"
        FISCAL = "fiscal", "Fiscal"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile", verbose_name="usuário")
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="user_profiles", verbose_name="organização")
    role = models.CharField("perfil", max_length=24, choices=Role.choices, default=Role.OPERATOR)
    is_active = models.BooleanField("ativo", default=True)
    must_change_password = models.BooleanField("exige troca de senha", default=False)
    created_at = models.DateTimeField("criado em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    objects = ActiveQuerySet.as_manager()

    class Meta:
        verbose_name = "perfil de usuário"
        verbose_name_plural = "perfis de usuário"
        ordering = ["organization__name", "user__username"]
        indexes = [models.Index(fields=["organization", "role", "is_active"])]

    def __str__(self):
        return f"{self.user} ({self.get_role_display()})"


class UserStoreAccess(models.Model):
    profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name="store_accesses", verbose_name="perfil")
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="user_accesses", verbose_name="loja")
    is_active = models.BooleanField("ativo", default=True)
    created_at = models.DateTimeField("criado em", auto_now_add=True)

    objects = ActiveQuerySet.as_manager()

    class Meta:
        verbose_name = "acesso de usuário a loja"
        verbose_name_plural = "acessos de usuários a lojas"
        ordering = ["profile__user__username", "store__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "store"],
                name="unique_user_store_access",
                violation_error_message="Este usuário já possui acesso a esta loja.",
            )
        ]
        indexes = [models.Index(fields=["store", "is_active"])]

    def clean(self):
        if self.profile_id and self.store_id and self.profile.organization_id != self.store.organization_id:
            raise ValidationError("A loja precisa pertencer à mesma organização do usuário.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.profile.user} -> {self.store}"
