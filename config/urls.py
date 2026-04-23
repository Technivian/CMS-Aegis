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
from contracts.api import views as contract_api_views
from django.contrib.auth import views as auth_views

logger = logging.getLogger(__name__)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', contract_views.index, name='index'),
    path('_health/', contract_views.health_check, name='health_check'),
    path('dashboard/', contract_views.dashboard, name='dashboard'),
    path('scim/v2/Users', contract_api_views.scim_users_api, name='scim_users_api_root'),
    path('scim/v2/Users/<str:scim_id>', contract_api_views.scim_user_api, name='scim_user_api_root'),
    path('scim/v2/Groups', contract_api_views.scim_groups_api, name='scim_groups_api_root'),
    path('scim/v2/Groups/<str:scim_id>', contract_api_views.scim_group_api, name='scim_group_api_root'),
    path('saml/', contract_views.saml_select, name='saml_select'),
    path('saml/<slug:organization_slug>/login/', contract_views.saml_login, name='saml_login'),
    path('saml/<slug:organization_slug>/acs/', contract_views.saml_acs, name='saml_acs'),
    path('saml/<slug:organization_slug>/logout/', contract_views.saml_logout, name='saml_logout'),
    path('saml/<slug:organization_slug>/metadata/', contract_views.saml_metadata, name='saml_metadata'),
    path('contracts/', include('contracts.urls')),
    path('profile/', contract_views.profile, name='profile'),
    path('settings/', contract_views.settings_hub, name='settings_hub'),
    path('settings/organization-security/', contract_views.organization_security_settings, name='organization_security_settings'),
    path('settings/organization-security/export/', contract_views.organization_security_export, name='organization_security_export'),
    path('settings/organization-security/sessions/', contract_views.organization_session_audit, name='organization_session_audit'),
    path('settings/organization-security/sessions/export/', contract_views.organization_session_audit_export, name='organization_session_audit_export'),
    path('settings/identity/', contract_views.organization_identity_settings, name='organization_identity_settings'),
    path('operations/', contract_views.operations_dashboard, name='operations_dashboard'),
    path('register/', contract_views.SignUpView.as_view(), name='register'),
    path('login/', contract_views.LoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('toggle-redesign/', contract_views.toggle_redesign, name='toggle_redesign'),
]

if 'debug_toolbar' in settings.INSTALLED_APPS:
    urlpatterns.append(path('__debug__/', include('debug_toolbar.urls')))
if 'django_browser_reload' in settings.INSTALLED_APPS:
    urlpatterns.append(path('__reload__/', include('django_browser_reload.urls')))

if settings.SSO_ENABLED:
    urlpatterns.append(path('oidc/', include('mozilla_django_oidc.urls')))

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
