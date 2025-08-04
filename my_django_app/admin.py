from django.contrib import admin
from django.apps import apps
import sys
import inspect
from . import fields


class CustomAdmin(admin.ModelAdmin):
    model = None
    items = []

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        # if cls.model is None:
        #     model_name = cls.__name__.removesuffix("Admin")
        #     print("X--------------", model_name)
        #     app_label = cls.__module__.split(".")[0]
        #     try:
        #         cls.model = apps.get_model(app_label, model_name)
        #     except LookupError:
        #         raise Exception(f"Could not infer model for {cls.__name__}")

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


def register_all_admins():
    from django.apps import apps
    import importlib

    for app_config in apps.get_app_configs():
        try:
            importlib.import_module(f"{app_config.name}.admin")
        except ModuleNotFoundError:
            continue

    for cls in CustomAdmin.__subclasses__():
        if not getattr(cls, "model", None):
            continue
        admin.site.register(cls.model, cls)


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
            setattr(sys.modules[target_module], admin_name, admin_class)
