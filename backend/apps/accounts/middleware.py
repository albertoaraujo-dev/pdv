import time

from django.conf import settings
from django.contrib.sessions.backends.base import UpdateError
from django.contrib.sessions.exceptions import SessionInterrupted
from django.contrib.sessions.middleware import SessionMiddleware
from django.utils.cache import patch_vary_headers
from django.utils.http import http_date


class ScopedSessionMiddleware(SessionMiddleware):
    def session_cookie_name(self, request):
        if request.path == "/admin" or request.path.startswith("/admin/"):
            return settings.ADMIN_SESSION_COOKIE_NAME
        return settings.SESSION_COOKIE_NAME

    def session_cookie_path(self, request):
        if request.path == "/admin" or request.path.startswith("/admin/"):
            return settings.ADMIN_SESSION_COOKIE_PATH
        return settings.SESSION_COOKIE_PATH

    def process_request(self, request):
        session_key = request.COOKIES.get(self.session_cookie_name(request))
        request.session = self.SessionStore(session_key)

    def process_response(self, request, response):
        try:
            accessed = request.session.accessed
            modified = request.session.modified
            empty = request.session.is_empty()
        except AttributeError:
            return response

        cookie_name = self.session_cookie_name(request)
        cookie_path = self.session_cookie_path(request)
        if cookie_name in request.COOKIES and empty:
            response.delete_cookie(
                cookie_name,
                path=cookie_path,
                domain=settings.SESSION_COOKIE_DOMAIN,
                samesite=settings.SESSION_COOKIE_SAMESITE,
            )
            patch_vary_headers(response, ("Cookie",))
        else:
            if accessed:
                patch_vary_headers(response, ("Cookie",))
            if (modified or settings.SESSION_SAVE_EVERY_REQUEST) and not empty and response.status_code < 500:
                if request.session.get_expire_at_browser_close():
                    max_age = None
                    expires = None
                else:
                    max_age = request.session.get_expiry_age()
                    expires_time = time.time() + max_age
                    expires = http_date(expires_time)
                try:
                    request.session.save()
                except UpdateError:
                    raise SessionInterrupted(
                        "The request's session was deleted before the request completed. "
                        "The user may have logged out in a concurrent request, for example."
                    )
                response.set_cookie(
                    cookie_name,
                    request.session.session_key,
                    max_age=max_age,
                    expires=expires,
                    domain=settings.SESSION_COOKIE_DOMAIN,
                    path=cookie_path,
                    secure=settings.SESSION_COOKIE_SECURE or None,
                    httponly=settings.SESSION_COOKIE_HTTPONLY or None,
                    samesite=settings.SESSION_COOKIE_SAMESITE,
                )
        return response
