from django.db.models.functions import (
    ExtractYear,
    ExtractMonth,
    ExtractDay,
    ExtractWeek,
    ExtractWeekDay,
    ExtractQuarter,
)
from django.db.models import CharField, F, Value, Func, Count, Min, Max, Sum
from django.db.models.functions import Concat, Cast, Right
from dateutil.relativedelta import relativedelta
import re
from datetime import datetime
from django.utils import timezone


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
