"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
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
import logging

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import render
from django.views.generic import TemplateView # Import TemplateView
from contracts import views as contract_views

from django.contrib.auth import views as auth_views

logger = logging.getLogger(__name__)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', contract_views.index, name='index'),
    path('_health/', contract_views.health_check, name='health_check'),
    path('dashboard/', contract_views.dashboard, name='dashboard'),
    path('profile/', contract_views.profile, name='profile'),
    path('settings/', contract_views.settings_hub, name='settings_hub'),
    path('register/', contract_views.SignUpView.as_view(), name='register'),
    path('login/', auth_views.LoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('toggle-redesign/', contract_views.toggle_redesign, name='toggle_redesign'),
    path('__reload__/', include('django_browser_reload.urls')),
]

try:
    urlpatterns.append(path('contracts/', include('contracts.urls')))
except Exception as exc:
    logger.warning('Skipping contracts.urls include due to import error: %s', exc)

if settings.SSO_ENABLED:
    urlpatterns.append(path('oidc/', include('mozilla_django_oidc.urls')))

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
