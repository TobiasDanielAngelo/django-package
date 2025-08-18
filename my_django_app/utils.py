from django.db.models.functions import (
    ExtractYear,
    ExtractMonth,
    ExtractDay,
    ExtractWeek,
    ExtractWeekDay,
    ExtractQuarter,
)
from django.db.models import CharField, F, Value, Func, Count, Min, Max, Sum, Q
from django.db.models.functions import Concat, Cast, Right
from dateutil.relativedelta import relativedelta
import re
from datetime import datetime
from django.utils import timezone
import socket
import os
from dotenv import load_dotenv
from django.db.models import Aggregate, FloatField, F, ExpressionWrapper
from django.db.models.fields.related import ForeignObjectRel, ManyToManyRel
from django.db import models


def obj_list_to_obj_val(**list):
    obj_val = {}
    for key, value in list.items():
        obj_val[key] = value[0]
    return obj_val


# List of annotations (name, function)
date_annotations = [
    ("year", ExtractYear),
    ("month", ExtractMonth),
    ("day", ExtractDay),
    ("week", ExtractWeek),
    ("weekday", ExtractWeekDay),
    ("quarter", ExtractQuarter),
]


def annotate_period(qs, datetime_key, *fields, separator="-"):
    for name, func in date_annotations:
        qs = qs.annotate(**{name: func(datetime_key)})
    qs = qs.annotate(period=Period(*fields))
    return qs


def generate_period_list(qs, datetime_key, *fields, separator="-"):
    date_range = qs.aggregate(start=Min(datetime_key), end=Max(datetime_key))
    start, end = date_range["start"], date_range["end"]

    if not start or not end:
        return []
    if timezone.is_naive(start):
        start = timezone.make_aware(start)
    if timezone.is_naive(end):
        end = timezone.make_aware(end)
    if not start or not end:
        return []

    periods = []

    def make_label(dt):
        parts = []
        for f in fields:
            if f == "year":
                parts.append(str(dt.year))
            elif f == "month":
                parts.append(f"{dt.month:02d}")
            elif f == "day":
                parts.append(f"{dt.day:02d}")
            elif f == "quarter":
                parts.append(f"Q{(dt.month - 1) // 3 + 1}")
            elif f == "week":
                parts.append(f"W{dt.isocalendar().week:02d}")
            elif f == "weekday":
                parts.append(f"D{dt.weekday() + 1}")
        return separator.join(parts)

    # Handle field type by extracting unique values
    if fields == ("year",):
        for year in range(start.year, end.year + 1):
            periods.append(str(year))

    elif fields == ("year", "quarter"):
        for year in range(start.year, end.year + 1):
            q_start = 1
            q_end = 4

            if year == start.year:
                q_start = (start.month - 1) // 3 + 1
            if year == end.year:
                q_end = (end.month - 1) // 3 + 1

            for q in range(q_start, q_end + 1):
                periods.append(f"{year}-Q{q}")

    elif fields == ("year", "day"):
        current = datetime(start.year, start.month, start.day)
        if timezone.is_naive(current):
            current = timezone.make_aware(current)
        while current <= end:
            periods.append(
                f"{current.year}-{current.timetuple().tm_yday:03d}"
            )  # 001–365
            current += relativedelta(days=1)

    elif fields == ("year", "month", "day"):
        current = datetime(start.year, start.month, start.day)
        if timezone.is_naive(current):
            current = timezone.make_aware(current)
        while current <= end:
            periods.append(f"{current.year}-{current.month:02d}-{current.day:02d}")
            current += relativedelta(days=1)

    elif fields == ("year", "week"):
        current = start
        seen = set()
        while current <= end:
            year, week, _ = current.isocalendar()
            label = f"{year}-W{week:02d}"
            if label not in seen:
                seen.add(label)
                periods.append(label)
            current += relativedelta(days=1)

    elif fields == ("year", "day"):
        current = datetime(start.year, start.month, start.day)
        while current <= end:
            periods.append(f"{current.year}-{current.month:02d}-{current.day:02d}")
            current += relativedelta(days=1)

    elif fields == ("year", "month"):
        for year in range(start.year, end.year + 1):
            m_start = 1
            m_end = 12
            if year == start.year:
                m_start = start.month
            if year == end.year:
                m_end = end.month
            for m in range(m_start, m_end + 1):
                periods.append(f"{year}-{m:02}")

    else:
        # fallback for custom mixes like ("year", "weekday"), etc.
        current = start
        seen = set()
        while current <= end:
            label = make_label(current)
            if label not in seen:
                seen.add(label)
                periods.append(label)
            current += relativedelta(days=1)
    return periods


class LPAD(Func):
    function = "LPAD"
    arity = 3  # needs 3 arguments: value, length, pad_char


def Period(*fields, separator="-"):
    parts = []
    for i, f in enumerate(fields):
        if f == "quarter":
            parts.append(Value("Q"))
            parts.append(Cast(F(f), output_field=CharField()))
        elif f == "week":
            parts.append(Value("W"))
            padded = Right(Concat(Value("00"), Cast(F(f), output_field=CharField())), 2)
            parts.append(padded)
        elif f == "weekday":
            parts.append(Value("D"))
            parts.append(Cast(F(f), output_field=CharField()))
        elif f in ["month", "day"]:
            padded = Right(Concat(Value("00"), Cast(F(f), output_field=CharField())), 2)
            parts.append(padded)
        else:
            parts.append(Cast(F(f), output_field=CharField()))

        if i < len(fields) - 1:
            parts.append(Value(separator))

    return Concat(*parts, output_field=CharField())


def camel_to_kebab(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "-", name).lower()


def LOAD_ENV(BASE_DIR):
    load_dotenv(os.path.join(BASE_DIR, ".env"), override=True)
    env_type = os.environ.get("ENV")
    if os.environ.get("RUNNING_IN_DOCKER") == "1":
        load_dotenv(os.path.join(BASE_DIR, ".env.docker"), override=True)
    elif env_type == "lan":
        load_dotenv(os.path.join(BASE_DIR, ".env.lan"), override=True)
        local_ip = get_local_ip()
        os.environ["LOCAL_IP"] = local_ip
        os.environ["ALLOWED_HOSTS"] = f"{GET_ENV('ALLOWED_HOSTS','')},{local_ip}"
        os.environ["ALLOWED_ORIGINS"] = (
            f"{GET_ENV('ALLOWED_ORIGINS','')},"
            f"http://{local_ip}:3000,http://{local_ip}:5173"
        )
    elif env_type == "rpi":
        load_dotenv(os.path.join(BASE_DIR, ".env.rpi"), override=True)
    elif env_type == "production":
        load_dotenv(os.path.join(BASE_DIR, ".env.prod"), override=True)
    else:
        load_dotenv(os.path.join(BASE_DIR, ".env.local"), override=True)


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't have to be reachable
        s.connect(("10.255.255.255", 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = "127.0.0.1"
    finally:
        s.close()
    return IP


def GET_ENV_LIST(key: str) -> list[str]:
    raw = os.environ.get(key, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def GET_ENV(key: str, default: str = "") -> str:
    raw = os.environ.get(key, default)
    return raw.strip()


def GET_BOOL(key: str, default: str = "False") -> bool:
    val = os.environ.get(key, default).lower()
    return val in ("true", "1", "yes")


class SumProduct(Aggregate):
    function = "SUM"
    template = "%(function)s(%(expressions)s)"
    output_field = FloatField()

    def __init__(self, field1, field2, **extra):
        expression = ExpressionWrapper(F(field1) * F(field2), output_field=FloatField())
        super().__init__(expression, **extra)


def get_key(choices, value):
    return next((k for k, v in choices if v == value), None)


def invert_choices(choices):
    return {v: k for k, v in choices}


def to_money(n):
    return f"\u20b1{n:.2f}"


def annotate_most_frequent(queryset):
    model = queryset.model
    related_counts = {}

    for field in model._meta.get_fields():
        # Reverse ForeignKey or ManyToMany (related_name)
        if isinstance(field, (ForeignObjectRel, ManyToManyRel)):
            related_name = field.get_accessor_name()
            related_counts[f"links_{related_name}"] = Count(related_name, distinct=True)

    # Annotate all counts
    annotated_qs = queryset.annotate(**related_counts)

    # Build total sum expression
    if related_counts:
        total_expr = None
        for name in related_counts.keys():
            total_expr = F(name) if total_expr is None else total_expr + F(name)
        annotated_qs = annotated_qs.annotate(total_links=total_expr)
        annotated_qs = annotated_qs.order_by("-total_links")

    return annotated_qs


def CannotEqual(field1: str, field2: str, model_name: str = None, name: str = None):
    """
    Ensure field1 != field2.
    Automatically includes model name in the constraint name for uniqueness.
    """
    if not name:
        if not model_name:
            raise ValueError("model_name is required if name is not provided")
        name = f"{model_name.lower()}_cannot_equal_{field1}_{field2}"
    return models.CheckConstraint(check=~Q(**{field1: F(field2)}), name=name)
