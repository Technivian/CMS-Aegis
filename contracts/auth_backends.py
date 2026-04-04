from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils.text import slugify

from mozilla_django_oidc.auth import OIDCAuthenticationBackend


class AegisOIDCAuthenticationBackend(OIDCAuthenticationBackend):
    """Authenticate users via OIDC and map identities by email."""

    def _email_from_claims(self, claims):
        return (
            claims.get('email')
            or claims.get('upn')
            or claims.get('preferred_username')
            or ''
        ).strip().lower()

    def _is_allowed_email_domain(self, email: str) -> bool:
        allowed_domains = getattr(settings, 'SSO_ALLOWED_EMAIL_DOMAINS', [])
        if not allowed_domains:
            return True
        if '@' not in email:
            return False
        domain = email.split('@', 1)[1].lower()
        return domain in allowed_domains

    def verify_claims(self, claims):
        email = self._email_from_claims(claims)
        return super().verify_claims(claims) and bool(email) and self._is_allowed_email_domain(email)

    def filter_users_by_claims(self, claims):
        email = self._email_from_claims(claims)
        if not email:
            return self.UserModel.objects.none()
        return self.UserModel.objects.filter(email__iexact=email)

    def create_user(self, claims):
        email = self._email_from_claims(claims)
        preferred = claims.get('preferred_username') or email.split('@')[0] or 'sso-user'
        username_base = slugify(preferred)[:30] or 'sso-user'
        username = username_base

        user_model = get_user_model()
        suffix = 1
        while user_model.objects.filter(username=username).exists():
            suffix += 1
            username = f"{username_base[:24]}-{suffix}"

        user = user_model.objects.create_user(
            username=username,
            email=email,
            first_name=(claims.get('given_name') or '').strip(),
            last_name=(claims.get('family_name') or '').strip(),
        )
        user.is_active = True
        user.save(update_fields=['is_active'])
        return user

    def update_user(self, user, claims):
        email = self._email_from_claims(claims)
        if email and user.email != email:
            user.email = email

        given_name = (claims.get('given_name') or '').strip()
        family_name = (claims.get('family_name') or '').strip()

        if given_name:
            user.first_name = given_name
        if family_name:
            user.last_name = family_name

        user.save(update_fields=['email', 'first_name', 'last_name'])
        return user
