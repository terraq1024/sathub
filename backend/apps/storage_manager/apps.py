from django.apps import AppConfig


class StorageManagerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.storage_manager"
    label = "storage_manager"
    verbose_name = "存储管理"
