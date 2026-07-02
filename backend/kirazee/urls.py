"""
URL configuration for kirazee project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
import delivery.routing
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from rest_framework import permissions
from django.shortcuts import render
from django.views.generic import TemplateView

# For WebSocket
application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": URLRouter(
        delivery.routing.websocket_urlpatterns
    ),
})

schema_view = get_schema_view(
    openapi.Info(
        title="Kirazee API",
        default_version='v1',
        description="API documentation for all Kirazee services",
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('kirazee/', include('kirazee_app.urls')),
    path('kirazee/business/', include('business.urls')),
    path('kirazee/grocery/', include('consumer.gro_urls')),
    path('kirazee/consumer/', include('consumer.urls')),
    path('kirazee/vendor/', include('vendor.urls')),
    path('kirazee/delivery-partner/', include('delivery.urls')),
    path('kirazee/api/v1/admin/', include('kirazee_admin.urls')),
    path('kirazee/management/', include('management.urls')),
    path('kirazee/api/notifications/', include('notifications.urls')),
    # # Swagger / OpenAPI
    re_path(
        r'^kirazee/swagger(?P<format>\.json|\.yaml)$',
        schema_view.without_ui(cache_timeout=0),
        name='schema-json',
    ),
    path(
        'kirazee/swagger/',
        schema_view.with_ui('swagger', cache_timeout=0),
        name='schema-swagger-ui',
    ),
    path('kirazee/e1nt3y5mz623uykumners3df354/', lambda request: render(request, 'docs/redoc.html'), name='docs-redoc'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Always serve static files (needed for DRF admin interface)
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
