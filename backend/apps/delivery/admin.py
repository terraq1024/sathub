from django.contrib import admin
from .models import DeliveryBasket, DeliveryBasketItem, ExportJob


@admin.register(DeliveryBasket)
class DeliveryBasketAdmin(admin.ModelAdmin):
    list_display = ("owner", "updated_at")


@admin.register(DeliveryBasketItem)
class DeliveryBasketItemAdmin(admin.ModelAdmin):
    list_display = ("basket", "imagery", "added_at")


@admin.register(ExportJob)
class ExportJobAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "format", "status", "file_size", "created_at")
    list_filter = ("format", "status")
    readonly_fields = ("file_path", "file_size", "started_at", "finished_at")
