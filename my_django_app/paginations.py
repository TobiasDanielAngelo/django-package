from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from django.db.models import DateTimeField, DateField, TimeField
from .fields import AmountField
import math
from django.db.models.fields import Field


def to_camel_case(s):
    parts = s.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


class CustomPagination(PageNumberPagination):
    page_size_query_param = "page_size"

    def __init__(self, *args, **kwargs):
        self.model = None
        self.page_param = None
        self.all_data = None
        super().__init__(*args, **kwargs)

    def paginate_queryset(self, queryset, request, view=None):
        self.page_param = request.query_params.get(self.page_query_param)
        if self.page_param == "all":
            self.all_data = list(queryset)
            return self.all_data
        return super().paginate_queryset(queryset, request, view)

    def build_field_metadata(self, objects, data):
        """Shared logic for related/option/date/price fields."""
        related = []
        related_fields, option_fields, datetime_fields = [], [], []
        date_fields, price_fields, time_fields = [], [], []

        if self.model:
            for field in self.model._meta.get_fields():
                if not isinstance(field, Field):
                    continue
                field_name = field.name
                values = set()

                if field.is_relation and (
                    field.many_to_one or field.many_to_many or field.one_to_one
                ):
                    related_fields.append(to_camel_case(field.name))
                    for obj in objects:
                        value = getattr(obj, field_name, None)
                        if not value:
                            continue
                        if field.many_to_one or field.one_to_one:
                            values.add(value)
                        elif field.many_to_many:
                            values.update(value.all())
                    related.extend(
                        [
                            {
                                "field": to_camel_case(field_name),
                                "id": rel.pk,
                                "name": str(rel),
                            }
                            for rel in values
                        ]
                    )
                elif getattr(field, "choices", None):
                    option_fields.append(to_camel_case(field.name))
                    for obj in objects:
                        raw_value = getattr(obj, field_name, None)
                        if raw_value is not None:
                            values.add(raw_value)
                    related.extend(
                        [
                            {
                                "field": to_camel_case(field_name),
                                "id": val,
                                "name": dict(field.choices).get(val, str(val)),
                            }
                            for val in values
                        ]
                    )
                elif isinstance(field, DateTimeField):
                    datetime_fields.append(to_camel_case(field.name))
                elif isinstance(field, DateField):
                    date_fields.append(to_camel_case(field.name))
                elif isinstance(field, TimeField):
                    time_fields.append(to_camel_case(field.name))
                elif isinstance(field, AmountField):
                    price_fields.append(to_camel_case(field.name))

        return {
            "related": related,
            "related_fields": related_fields,
            "option_fields": option_fields,
            "date_fields": date_fields,
            "datetime_fields": datetime_fields,
            "time_fields": time_fields,
            "price_fields": price_fields,
        }

    def get_paginated_response(self, data):
        ids = [
            item.get("id") for item in data if isinstance(item, dict) and "id" in item
        ]

        if self.page_param == "all":
            meta = self.build_field_metadata(self.all_data, data)
            return Response(
                {
                    "count": len(data),
                    "current_page": 1,
                    "total_pages": 1,
                    "next": None,
                    "previous": None,
                    "ids": ids,
                    "results": data,
                    **meta,
                }
            )

        # Normal paginated
        total_pages = math.ceil(
            self.page.paginator.count / self.page.paginator.per_page
        )
        meta = self.build_field_metadata(self.page, data)

        return Response(
            {
                "count": self.page.paginator.count,
                "current_page": self.page.number,
                "total_pages": total_pages,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "ids": ids,
                "results": data,
                **meta,
            }
        )
