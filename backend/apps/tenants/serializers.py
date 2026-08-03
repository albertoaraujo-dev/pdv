from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Organization, Store, UserProfile


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ["id", "name", "legal_name", "document", "is_active"]


class UserStoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Store
        fields = ["id", "name", "code", "is_active"]


class StoreSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source="organization.name", read_only=True)

    class Meta:
        model = Store
        fields = ["id", "organization", "organization_name", "name", "code", "is_active"]


class UserProfileSerializer(serializers.ModelSerializer):
    role_label = serializers.CharField(source="get_role_display", read_only=True)
    organization_name = serializers.CharField(source="organization.name", read_only=True)
    stores = serializers.SerializerMethodField()

    class Meta:
        model = UserProfile
        fields = ["role", "role_label", "organization", "organization_name", "is_active", "must_change_password", "stores"]

    def get_stores(self, profile):
        stores = Store.objects.filter(user_accesses__profile=profile).order_by("name")
        return UserStoreSerializer(stores, many=True).data


class TenantUserSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(read_only=True)

    class Meta:
        model = get_user_model()
        fields = ["id", "username", "first_name", "last_name", "email", "is_active", "is_staff", "is_superuser", "profile"]
