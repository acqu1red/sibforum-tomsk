from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.decorators.cache import never_cache
from django.views.static import serve

urlpatterns = [
    path('', include('accounts.urls')),
    path('api/v1/', include('forums.urls')),
    path('api/v1/', include('registrations.urls')),
    path('api/v1/', include('voting.urls')),
    path('admin/', include('registrations.staff_urls')),
    path('admin/', admin.site.urls),
    path('media/<path:path>', never_cache(serve), {'document_root': settings.MEDIA_ROOT}, name='media'),
]
