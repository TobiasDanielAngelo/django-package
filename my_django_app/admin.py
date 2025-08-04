from django.contrib import admin
from django.apps import apps
import sys
import inspect
from . import fields


class CustomAdmin(admin.ModelAdmin):
    items = []

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        if hasattr(cls, "items") and cls.items:
            cls.inlines = [
                type(
                    f"{item.__name__}Inline",
                    (admin.TabularInline,),
                    {"model": item, "extra": 1},
                )
                for item in cls.items
            ]

    def get_list_display(self, request):
        return [field.name for field in self.model._meta.fields]

    def has_delete_permission(self, request, obj=None):
        if obj and obj.pk > 1000000:
            return False
        return super().has_delete_permission(request, obj)


def auto_create_admins(models, excluded_models=None):

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
            admin_name = f"{model_name}Admin"
            admin_class = type(
                name + "Admin",
                (CustomAdmin,),
                {"model": model_class},
            )
            admin.site.register(model_class, admin_class)
            setattr(sys.modules[target_module], admin_name, admin_class)
