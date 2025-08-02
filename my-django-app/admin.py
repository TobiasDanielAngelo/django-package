from django.contrib import admin
import importlib
from django.apps import apps


class CustomAdmin(admin.ModelAdmin):
    model = None
    items = []

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        if cls.model is None:
            model_name = cls.__name__.removesuffix("Admin")
            app_label = cls.__module__.split(".")[0]
            try:
                cls.model = apps.get_model(app_label, model_name)
            except LookupError:
                raise Exception(f"Could not infer model for {cls.__name__}")

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


class SettingAdmin(CustomAdmin):
    pass


for app_config in apps.get_app_configs():
    try:
        importlib.import_module(f"{app_config.name}.admin")
    except ModuleNotFoundError:
        continue

for cls in CustomAdmin.__subclasses__():
    if not getattr(cls, "model", None):
        continue
    admin.site.register(cls.model, cls)
