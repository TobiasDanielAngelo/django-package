from rest_framework import serializers
from django.contrib.auth import authenticate, hashers, password_validation
from django.contrib.auth.models import User
from django.apps import apps
import sys
import inspect
from . import fields


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
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        if cls.__name__ == "BaseSerializer":
            return  # Skip the base

        model_name = cls.__name__.replace("Serializer", "")
        model = next(
            (m for m in apps.get_models() if m.__name__ == model_name),
            None,
        )

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
                {},
            )

            setattr(sys.modules[target_module], serializer_name, serializer)
