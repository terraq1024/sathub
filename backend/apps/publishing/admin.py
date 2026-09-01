from django.contrib import admin

from .models import ImageryService, ImageryServiceAsset, ServicePublishJob


admin.site.register(ImageryService)
admin.site.register(ImageryServiceAsset)
admin.site.register(ServicePublishJob)
