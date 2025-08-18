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
from django.db.models.functions import Concat
from django.db.models import BooleanField, Value, F, Case, When, CharField


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


def get_display_fields(model, visited=None, depth=0, max_depth=2):
    if visited is None:
        visited = set()
    if model in visited or depth > max_depth:
        return []

    visited.add(model)

    result = []
    for field in model._meta.get_fields():

        if hasattr(field, "display"):  # you'd need this in Python
            if field.display:
                if field.is_relation and not field.many_to_many:
                    rel_model = field.related_model
                    # recursively fetch related model's display fields
                    rel_fields = get_display_fields(
                        rel_model, visited, depth + 1, max_depth
                    )
                    result.extend([f"{field.name}__{rf}" for rf in rel_fields])
                else:
                    result.append(field.name)
    return result


def annotate_display_name(queryset):
    display_fields = get_display_fields(queryset.model)

    if not display_fields:
        return queryset.annotate(
            display_name=Concat(
                Value(f"{queryset.model.__name__} # "),
                F("pk"),
                output_field=CharField(),
            )
        )

    if len(display_fields) == 1:
        return queryset.annotate(display_name=F(display_fields[0]))

    concat_args = []
    for i, field_name in enumerate(display_fields):
        try:
            field = queryset.model._meta.get_field(field_name)
        except FieldDoesNotExist:
            continue
        if isinstance(field, BooleanField):
            # Use Case/When: if True -> display title_cased field name, else empty string
            title_cased = field_name
            if field_name.lower().startswith("is"):
                title_cased = field_name[2:]
            title_cased = title_cased.replace("_", " ").strip().title()

            case_expr = Case(
                When(**{field_name: True}, then=Value(title_cased)),
                default=Value(""),
                output_field=CharField(),
            )
            concat_args.append(case_expr)
        else:
            if isinstance(field, fields.ChoiceIntegerField):
                concat_args.append(
                    Case(
                        *[
                            When(**{field_name: choice_val}, then=Value(choice_label))
                            for choice_val, choice_label in field.choices
                        ],
                        output_field=CharField(),
                    )
                )
            else:
                concat_args.append(F(field_name))

        # Append space except after last field
        if i < len(display_fields) - 1:
            concat_args.append(Value(" "))

    if len(concat_args) == 0:
        return queryset  # nothing to annotate

    if len(concat_args) == 1:
        single = concat_args[0]
        # If single is F(field_name), annotate directly
        if isinstance(single, F):
            return queryset.annotate(display_name=single)
        else:
            # For Value or expressions, annotate directly
            return queryset.annotate(display_name=single)
    else:
        return queryset.annotate(
            display_name=Concat(*concat_args, output_field=CharField())
        )


def get_char_fields(model, prefix="", depth=0, max_depth=2):
    if depth > max_depth:
        return []

    char_fields = []
    for f in model._meta.get_fields():
        if isinstance(f, CharField):
            char_fields.append(f"{prefix}{f.name}")
        elif (
            f.is_relation
            and hasattr(f, "related_model")
            and f.related_model != model
            and not f.many_to_many
        ):
            char_fields.extend(
                get_char_fields(
                    f.related_model,
                    prefix=f"{prefix}{f.name}__",
                    depth=depth + 1,
                    max_depth=max_depth,
                )
            )
    return char_fields


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
        model = next(
            (
                m
                for m in apps.get_models()
                if m.__name__ == model_name
                and m._meta.app_label == cls.queryset.model._meta.app_label
            ),
            None,
        )

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
            search_terms = value.split()
            if key == "display_name__search":
                for term in search_terms:
                    search_q &= Q(**{f"display_name__icontains": term})
            base_key = key.split("__")[0]
            if base_key not in model_fields:
                continue
            if "__search" in key:
                field_name = key.replace("__search", "")
                try:
                    field = self.queryset.model._meta.get_field(field_name)
                    if field.is_relation:
                        char_fields = get_char_fields(field.related_model)
                        for term in search_terms:
                            for rel_char in char_fields:
                                lookup = f"{field.name}__{rel_char}__icontains"
                                search_q |= Q(**{lookup: term})
                    else:
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
            annotate_display_name(self.filter_queryset(self.get_queryset()))
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

        queryset = self.paginate_queryset(queryset)
        if queryset is not None:
            serializer = self.get_serializer(queryset, many=True)
            return self.get_paginated_response(serializer.data)


def auto_create_viewsets(models, excluded_models=None):
    all_viewsets = []
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
                    "__module__": target_module,
                    "queryset": model_class.objects.all(),
                },
            )
            all_viewsets.append(viewset)
            setattr(sys.modules[target_module], viewset_name, viewset)
    return all_viewsets
