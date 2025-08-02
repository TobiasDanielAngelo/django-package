from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from django.db.models import DateTimeField, DateField, TimeField
from core.fields import AmountField
import math


def to_camel_case(s):
    parts = s.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


class CustomPagination(PageNumberPagination):
    page_size_query_param = "page_size"

    def __init__(self, *args, **kwargs):
        self.model = None
        super().__init__(*args, **kwargs)

    def get_paginated_response(self, data):
        total_pages = math.ceil(
            self.page.paginator.count / self.page.paginator.per_page
        )

        ids = [
            item.get("id") for item in data if isinstance(item, dict) and "id" in item
        ]

        related = []
        related_fields = []
        option_fields = []
        datetime_fields = []
        date_fields = []
        price_fields = []
        time_fields = []
        if self.model:
            for field in self.model._meta.get_fields():
                field_name = field.name
                values = set()
                if field.is_relation and field.many_to_one or field.many_to_many:
                    related_fields.append(to_camel_case(field.name))
                    values = set()

                    for obj in self.page:
                        value = getattr(obj, field_name, None)
                        if not value:
                            continue
                        if field.many_to_one:
                            values.add(value)
                        elif field.many_to_many:
                            for rel in value.all():
                                values.add(rel)

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
                    for obj in self.page:
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
        return Response(
            {
                "count": self.page.paginator.count,
                "current_page": self.page.number,
                "total_pages": total_pages,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "ids": ids,
                "related_fields": related_fields,
                "option_fields": option_fields,
                "date_fields": date_fields,
                "datetime_fields": datetime_fields,
                "price_fields": price_fields,
                "results": data,
                "related": related,
            }
        )
