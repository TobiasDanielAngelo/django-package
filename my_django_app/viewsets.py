from rest_framework import viewsets, response
from .serializers import *
from .permissions import CustomDjangoModelPermission
from knox.auth import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from django.core.exceptions import FieldDoesNotExist
from django.db.models import Q
import json
from lzstring import LZString
from django.db.models import CharField
from django.utils.module_loading import import_string
from . import fields
import sys
import inspect


class CustomAuthentication(TokenAuthentication):
    def authenticate(self, request):
        token = request.COOKIES.get("knox_token")

        if not token:
            token = request.headers.get("Authorization")
            if token and token.startswith("Token "):
                token = token.split("Token ")[1]
            elif "token" in request.data:
                token = request.data.get("token")

        if token:
            return self.authenticate_credentials(token.encode("utf-8"))

        return None


def decode_query_param(encoded_param):
    lz = LZString()
    return json.loads(lz.decompressFromEncodedURIComponent(encoded_param))


class CustomModelViewSet(viewsets.ModelViewSet):
    permission_classes = [
        # AllowAny,
        IsAuthenticated,
        CustomDjangoModelPermission,
    ]
    authentication_classes = (CustomAuthentication,)

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        if cls.__name__ == "CustomModelViewSet":
            return

        model_name = cls.__name__.replace("ViewSet", "")
        model = next((m for m in apps.get_models() if m.__name__ == model_name), None)

        if model:
            cls.queryset = model.objects.all()

            try:
                serializer_path = f"{model.__module__.rsplit('.', 1)[0]}.serializers.{model_name}Serializer"
                cls.serializer_class = import_string(serializer_path)
            except ImportError:
                pass

    def list(self, request, *args, **kwargs):
        params = self.request.query_params.copy()
        page_param = params.get("page", None)
        order_by = params.pop("order_by", [])
        encoded = params.get("q", None)

        decoded_params = {}
        if encoded:
            try:
                decoded_params = decode_query_param(encoded)
                params = decoded_params
            except Exception as e:
                print("Decoding failed:", e)

        filter_kwargs = {}
        exclude_kwargs = {}
        search_q = Q()
        model_fields = [f.name for f in self.queryset.model._meta.get_fields()]
        for key, value in params.items():
            base_key = key.split("__")[0]
            if base_key not in model_fields:
                continue
            if "__search" in key:
                field_name = key.replace("__search", "")
                search_terms = value.split()
                try:
                    field = self.queryset.model._meta.get_field(field_name)
                    for term in search_terms:
                        search_q &= Q(**{f"{field_name}__icontains": term})
                except FieldDoesNotExist:
                    for term in search_terms:
                        search_q &= Q(**{f"{field_name}__icontains": term})
                if field.choices:
                    matched_values = [
                        val
                        for val, label in field.choices
                        if any(term.lower() in label.lower() for term in search_terms)
                    ]
                    search_q &= Q(**{f"{field_name}__in": matched_values})
                if field.is_relation:
                    rel_model = field.related_model
                    char_fields = [
                        f.name
                        for f in rel_model._meta.get_fields()
                        if isinstance(f, CharField)
                    ]
                    for term in search_terms:
                        for rel_char in char_fields:
                            lookup = f"{field.name}__{rel_char}__icontains"
                            search_q |= Q(**{lookup: term})
            elif "__not_" in key:
                actual_key = key.replace("__not_", "__")
                if actual_key.endswith("__in"):
                    exclude_kwargs[actual_key] = value.split(",")
                else:
                    exclude_kwargs[actual_key] = value
            else:
                if key.endswith("__in"):
                    filter_kwargs[key] = value.split(",")
                else:
                    filter_kwargs[key] = value

        queryset = (
            self.filter_queryset(self.get_queryset())
            .filter(**filter_kwargs)
            .filter(search_q)
            .exclude(**exclude_kwargs)
        )

        if order_by:
            try:
                queryset = queryset.order_by(*order_by)
            except Exception as e:
                print("Order failed:", e)
        else:
            queryset = queryset.order_by("-id")

        self.paginator.model = queryset.model

        check_last_updated = params.get("check_last_updated")
        last_updated = params.get("last_updated")
        if check_last_updated:
            queryset = queryset.filter(updated_at__gte=last_updated)
            return response.Response({"count": len(queryset)})

        if page_param == "all":
            all_queryset = list(queryset)
            serializer = self.get_serializer(all_queryset, many=True)

            return response.Response(
                {
                    "count": len(all_queryset),
                    "current_page": 1,
                    "total_pages": 1,
                    "next": None,
                    "previous": None,
                    "ids": [
                        item.get("id")
                        for item in serializer.data
                        if isinstance(item, dict)
                    ],
                    "results": serializer.data,
                }
            )

        queryset = self.paginate_queryset(queryset)
        if queryset is not None:
            serializer = self.get_serializer(queryset, many=True)
            return self.get_paginated_response(serializer.data)


def auto_create_viewsets(models, excluded_models=None):

    frame = inspect.stack()[1]
    caller_module = inspect.getmodule(frame[0])
    target_module = caller_module.__name__

    excluded_models = excluded_models or []

    for name in dir(models):
        obj = getattr(models, name)
        if name in excluded_models:
            continue
        if (
            isinstance(obj, type)
            and issubclass(obj, fields.CustomModel)
            and obj.__module__ == models.__name__
        ):
            model_class = obj
            model_name = model_class.__name__
            viewset_name = f"{model_name}ViewSet"
            viewset = type(
                name + "ViewSet",
                (CustomModelViewSet,),
                {
                    "queryset": model_class.objects.all(),
                },
            )

            setattr(sys.modules[target_module], viewset_name, viewset)
