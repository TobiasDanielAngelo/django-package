def auto_generate_router_url_patterns(vs_module):
    from django.urls import include, path
    from django.conf import settings
    from django.conf.urls.static import static
    from rest_framework.routers import DefaultRouter
    from rest_framework.viewsets import ViewSetMixin
    import inflect
    import re
    from .utils import camel_to_kebab

    router = DefaultRouter()

    inflector = inflect.engine()

    for attr_name in dir(vs_module):
        viewset = getattr(vs_module, attr_name)

        if (
            isinstance(viewset, type)
            and issubclass(viewset, ViewSetMixin)
            and attr_name != "CustomModelViewSet"
            and attr_name != "viewset"
        ):
            base = re.sub(r"ViewSet$", "", attr_name)
            if base != "CustomModel":
                kebab = camel_to_kebab(base)
                route = inflector.plural(kebab)
                router.register(route, viewset, basename=route)

    urlpatterns = [
        path("", include(router.urls)),
    ] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

    return urlpatterns


def auth_url_patterns():
    from django.urls import path
    from . import views

    urlpatterns = [
        path("logout", views.CookieLogoutView.as_view(), name="logout"),
        path("login", views.CookieLoginView.as_view(), name="login"),
        path("reauth", views.CookieReauthView.as_view(), name="reauth"),
    ]

    return urlpatterns
