from rest_framework import serializers
from django.contrib.auth import authenticate, hashers, password_validation
from django.contrib.auth.models import User
from django.apps import apps
import sys
import inspect
from . import fields
from django.db import models
import typing
from django.core.exceptions import ValidationError as DjangoValidationError


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=255)
    password = serializers.CharField(
        max_length=255, style={"input_type": "password"}, write_only=True
    )
    token = serializers.CharField(max_length=255, read_only=True)

    class Meta:
        model = User
        fields = ["username", "password", "token"]
        extra_kwargs = {"password": {"write_only": True}}

    def validate(self, data):
        username = data.get("username")
        password = data.get("password")

        if username and password:
            user = authenticate(
                request=self.context.get("request"),
                username=username,
                password=password,
            )
            if not user:
                raise serializers.ValidationError(
                    "Unable to login with provided credentials.", code="authorization"
                )
        else:
            raise serializers.ValidationError(
                "Must include username and password.", code="authorization"
            )

        data["user"] = user
        return super(LoginSerializer, self).validate(data)


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        max_length=255, style={"input_type": "password"}, write_only=True
    )
    password_2 = serializers.CharField(
        max_length=255, style={"input_type": "password"}, write_only=True
    )

    class Meta:
        model = User
        fields = "__all__"

    def validate_password1(self, data):
        result = password_validation.validate_password(data["password"])
        if data["password"] != data["password_2"]:
            raise serializers.ValidationError("Password doesn't match")
        elif result is not None:
            raise serializers.ValidationError("The password is not strong enough")
        else:
            return data

    def validate(self, data):
        if not (data.get("password") and data.get("password_2")):
            return super().validate(data)
        self.validate_password1(data)
        data.pop("password_2")
        return super().validate(data)

    def create(self, validated_data):
        password = validated_data["password"]
        validated_data.pop("password")
        user = User.objects.create(
            **validated_data,
            password=hashers.make_password(password),
        )
        return user

    def update(self, instance, validated_data):
        if validated_data.get("avatar"):
            validated_data.pop("avatar")
        if validated_data.get("password"):
            validated_data.pop("password")
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class CustomSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()

    def get_display_name(self, obj):
        return str(obj)

    def get_fields(self):
        fields = super().get_fields()
        model = getattr(self.Meta, "model", None)
        reverse_fields = {
            rel.get_accessor_name()
            for rel in model._meta.get_fields()
            if (rel.one_to_many or rel.one_to_one)
            and rel.auto_created
            and not rel.concrete
        }
        denylist = {
            "Meta",
            "DoesNotExist",
            "MultipleObjectsReturned",
            "save_base",
            "asave",
            "adelete",
            "check",
            "clean_fields",
            "from_db",
            "prepare_database_save",
            "unique_error_message",
            "validate_constraints",
            "get_constraints",
            "arefresh_from_db",
            "date_error_message",
            "get_next_by_created_at",
            "get_previous_by_created_at",
            "clean",
            "save",
            "full_clean",
            "validate_unique",
            "delete",
            "refresh_from_db",
            "get_next_by_updated_at",
            "get_previous_by_updated_at",
            "get_deferred_fields",
            "serializable_value",
        }
        rejected_attrs = []

        if model:
            model_instance = model()
            for attr in dir(model_instance):
                class_attr = getattr(model, attr, None)
                if (
                    isinstance(class_attr, property)
                    and attr not in fields
                    and attr != "pk"
                ):
                    fields[attr] = serializers.ReadOnlyField()
                # if attr.startswith("get_") and attr.endswith("_display"):
                #     rejected_attrs.append(attr)
                #     continue
                # if attr.startswith("_"):
                #     rejected_attrs.append(attr)
                #     continue
                # if attr in fields:
                #     rejected_attrs.append(attr)
                #     continue
                # method = getattr(model, attr, None)
                # if not callable(method):
                #     print(attr)
                #     rejected_attrs.append(attr)
                #     continue
                # if hasattr(method, '__self__') and isinstance(method.__self__, models.Field):
                #     rejected_attrs.append(attr)
                #     continue
                # if attr in denylist or attr in reverse_fields:
                #     rejected_attrs.append(attr)
                #     continue
                # fields[attr] = serializers.SerializerMethodField()

                def make_method(name):
                    return lambda self, obj: getattr(obj, name)()

                method_name = f"get_{attr}"
                if not hasattr(self.__class__, method_name):
                    setattr(self.__class__, method_name, make_method(attr))
        # print(rejected_attrs)
        return fields

    def validate(self, attrs):
        model_class = self.Meta.model

        # Start from existing instance or create a new one
        instance = self.instance or model_class()

        # Apply attrs to instance (including M2M)
        for key, value in attrs.items():
            (
                setattr(instance, f"_prefetched_{key}", value)
                if hasattr(value, "__iter__") and not isinstance(value, str)
                else setattr(instance, key, value)
            )

        try:
            instance.clean()
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.message_dict)

        return attrs

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        if cls.__name__ == "BaseSerializer":
            return  # Skip the base

        model_name = cls.__name__.replace("Serializer", "")
        model = None
        for m in apps.get_models():
            serializer_app_label = cls.__module__.split(".")[0]
            if m.__name__ == model_name and m._meta.app_label == serializer_app_label:
                model = m
                break

        if model:
            # Define Meta dynamically
            meta_class = type(
                "Meta",
                (),
                {
                    "model": model,
                    "fields": "__all__",
                },
            )
            cls.Meta = meta_class


def auto_create_serializers(models, excluded_models=None):

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
            serializer_name = f"{model_name}Serializer"
            serializer = type(
                name + "Serializer",
                (CustomSerializer,),
                {
                    "__module__": target_module,
                },
            )
            setattr(sys.modules[target_module], serializer_name, serializer)
