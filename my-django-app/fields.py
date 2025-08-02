from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django import forms
from datetime import datetime, time
import re


class AmountField(models.DecimalField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("max_digits", 10)
        kwargs.setdefault("decimal_places", 2)
        super().__init__(*args, **kwargs)


class DecimalField(models.DecimalField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("max_digits", 10)
        kwargs.setdefault("decimal_places", 3)
        super().__init__(*args, **kwargs)


class LongCharField(models.CharField):
    def __init__(self, display=False, *args, **kwargs):
        self.display = display
        kwargs.setdefault("max_length", 1023)
        kwargs.setdefault("default", "")
        kwargs.setdefault("blank", True)
        super().__init__(*args, **kwargs)


class MediumCharField(models.CharField):
    def __init__(self, display=False, *args, **kwargs):
        self.display = display
        kwargs.setdefault("max_length", 255)
        kwargs.setdefault("default", "")
        kwargs.setdefault("blank", True)
        super().__init__(*args, **kwargs)


class ShortCharField(models.CharField):
    def __init__(self, display=False, *args, **kwargs):
        self.display = display
        kwargs.setdefault("max_length", 50)
        kwargs.setdefault("default", "")
        kwargs.setdefault("blank", True)
        super().__init__(*args, **kwargs)


class ColorField(models.CharField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("max_length", 7)
        kwargs.setdefault("default", "")
        kwargs.setdefault("blank", True)
        kwargs.setdefault("help_text", "Hex color code, e.g. #FF5733")
        super().__init__(*args, **kwargs)


class AutoCreatedAtField(models.DateTimeField):
    """
    Automatically sets the datetime when the object is first created.
    Equivalent to auto_now_add=True. Not editable.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("auto_now_add", True)
        super().__init__(*args, **kwargs)


class AutoUpdatedAtField(models.DateTimeField):
    """
    Automatically updates the datetime every time the object is saved.
    Equivalent to auto_now=True. Not editable.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("auto_now", True)
        super().__init__(*args, **kwargs)


class DefaultNowField(models.DateTimeField):
    """
    Sets the default datetime to now, but allows manual editing.
    Useful for editable timestamps that default to current time.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("default", timezone.now)
        kwargs.setdefault("null", True)
        kwargs.setdefault("blank", True)
        super().__init__(*args, **kwargs)


class DefaultTodayField(models.DateField):
    """
    Sets the default date to now, but allows manual editing.
    Useful for editable timestamps that default to current time.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("default", timezone.localdate)
        kwargs.setdefault("null", True)
        kwargs.setdefault("blank", True)
        super().__init__(*args, **kwargs)


class OptionalDateTimeField(models.DateTimeField):
    """
    A fully optional DateTimeField with no default.
    Useful for fields that may be left empty (e.g. closed_at, due_at).
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("null", True)
        kwargs.setdefault("blank", True)
        super().__init__(*args, **kwargs)


class OptionalDateField(models.DateField):
    """
    A fully optional DateTimeField with no default.
    Useful for fields that may be left empty (e.g. closed_at, due_at).
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("null", True)
        kwargs.setdefault("blank", True)
        super().__init__(*args, **kwargs)


class ChoiceIntegerField(models.IntegerField):
    """
    IntegerField that accepts choices as first positional argument.
    Automatically sets default to 0. Safe for migrations.
    """

    def __init__(self, choices_list, *args, **kwargs):
        self._choices_list = choices_list  # store for deconstruction
        kwargs.setdefault("choices", choices_list)

        if len(args) >= 1:
            default = args[0]
            args = args[1:]  # remove default from args
            kwargs.setdefault("default", default)
        else:
            kwargs.setdefault("default", 0)

        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()

        # Put choices_list and default back into args
        args = [self._choices_list, kwargs.get("default", 0)] + args

        # Clean up if kwargs were auto-set
        if kwargs.get("choices") == self._choices_list:
            del kwargs["choices"]
        if kwargs.get("default") == 0:
            del kwargs["default"]

        return name, path, args, kwargs


class DefaultBooleanField(models.BooleanField):
    """
    BooleanField where the first argument is treated as the default value.
    Usage:
        is_active = DefaultBooleanField(True)
    """

    def __init__(self, default_value, *args, **kwargs):
        self._default_value = default_value  # for deconstruction
        kwargs.setdefault("default", default_value)
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        args = [self._default_value] + args
        if kwargs.get("default") == self._default_value:
            del kwargs["default"]
        return name, path, args, kwargs


class OptionalLimitedTimeField(models.TimeField):
    """
    A TimeField that:
    - Accepts only 'h:mm AM/PM' format from user input
    - Supports min_time/max_time as either time() or "h:mm AM/PM" strings

    Usage:
        CustomTimeField()  # no limits
        CustomTimeField("8:00 AM", "5:00 PM")
        CustomTimeField("8:00 AM")  # min only
        CustomTimeField(None, "9:00 PM")  # max only
    """

    TIME_FORMAT = "%I:%M %p"  # '3:15 PM'
    TIME_REGEX = re.compile(r"^(0?[1-9]|1[0-2]):[0-5][0-9]\s?(AM|PM)$", re.IGNORECASE)

    def __init__(self, *args, **kwargs):
        def parse(t):
            if isinstance(t, str):
                try:
                    return datetime.strptime(t.strip().upper(), self.TIME_FORMAT).time()
                except ValueError:
                    raise ValueError(f"Invalid time format: '{t}'. Use 'h:mm AM/PM'")
            return t

        min_time = parse(args[0]) if len(args) >= 1 else None
        max_time = parse(args[1]) if len(args) >= 2 else None

        validators = kwargs.pop("validators", [])
        if min_time:
            validators.append(MinValueValidator(min_time))
        if max_time:
            validators.append(MaxValueValidator(max_time))

        kwargs.setdefault("blank", True)
        kwargs.setdefault("null", True)
        kwargs["validators"] = validators

        self.min_time = min_time
        self.max_time = max_time

        super().__init__(**kwargs)

    def to_python(self, value):
        if isinstance(value, time) or value is None:
            return value

        if isinstance(value, str):
            value = value.strip().upper()
            if not self.TIME_REGEX.match(value):
                raise ValidationError(
                    "Time must be in format h:mm AM/PM (e.g., 3:45 PM)"
                )
            try:
                return datetime.strptime(value, self.TIME_FORMAT).time()
            except ValueError:
                raise ValidationError(
                    "Invalid time format. Use h:mm AM/PM (e.g., 3:45 PM)"
                )

        return super().to_python(value)


class ForeignKey(models.ForeignKey):
    """
    Base FK with auto related_name = <modelname>_<fieldname> (if not set).
    """

    def __init__(self, to, *args, **kwargs):
        self._to_model = to
        self._related_name_set = "related_name" in kwargs
        super().__init__(to, *args, **kwargs)

    def contribute_to_class(self, cls, name, **kwargs):
        if not self._related_name_set:
            self.remote_field.related_name = f"{cls.__name__.lower()}_{name}"
        super().contribute_to_class(cls, name, **kwargs)


class CascadeRequiredForeignKey(ForeignKey):
    """
    Required ForeignKey with CASCADE delete and auto related_name.
    """

    def __init__(self, to, *args, **kwargs):
        kwargs.setdefault("on_delete", models.CASCADE)
        super().__init__(to, *args, **kwargs)


class CascadeOptionalForeignKey(ForeignKey):
    """
    Optional ForeignKey with CASCADE delete and auto related_name.
    """

    def __init__(self, to, *args, **kwargs):
        kwargs.setdefault("on_delete", models.CASCADE)
        kwargs.setdefault("null", True)
        kwargs.setdefault("blank", True)
        super().__init__(to, *args, **kwargs)


class SetNullOptionalForeignKey(ForeignKey):
    """
    Optional ForeignKey with SET_NULL delete and auto related_name.
    """

    def __init__(self, to, *args, **kwargs):
        kwargs.setdefault("on_delete", models.SET_NULL)
        kwargs.setdefault("null", True)
        kwargs.setdefault("blank", True)
        super().__init__(to, *args, **kwargs)


class ManyToManyField(models.ManyToManyField):
    """
    ManyToManyField with auto related_name = <modelname>_<fieldname> if not set.
    """

    def __init__(self, to, *args, **kwargs):
        self._to_model = to
        self._related_name_set = "related_name" in kwargs
        super().__init__(to, *args, **kwargs)

    def contribute_to_class(self, cls, name, **kwargs):
        if not self._related_name_set:
            self.remote_field.related_name = f"{cls.__name__.lower()}_{name}"
        super().contribute_to_class(cls, name, **kwargs)


class OptionalManyToManyField(ManyToManyField):
    def __init__(self, to, *args, **kwargs):
        kwargs.setdefault("blank", True)
        super().__init__(to, *args, **kwargs)


class OneToOneField(models.OneToOneField):
    """
    OneToOneField with auto related_name = <modelname>_<fieldname> if not set.
    """

    def __init__(self, to, *args, **kwargs):
        self._to_model = to
        self._related_name_set = "related_name" in kwargs
        super().__init__(to, *args, **kwargs)

    def contribute_to_class(self, cls, name, **kwargs):
        if not self._related_name_set:
            self.remote_field.related_name = f"{cls.__name__.lower()}_{name}"
        super().contribute_to_class(cls, name, **kwargs)


class OptionalOneToOneField(OneToOneField):
    def __init__(self, to, *args, **kwargs):
        kwargs.setdefault("null", True)
        kwargs.setdefault("blank", True)
        kwargs.setdefault("on_delete", models.CASCADE)
        super().__init__(to, *args, **kwargs)


class OptionalSetNullOneToOneField(OneToOneField):
    def __init__(self, to, *args, **kwargs):
        kwargs.setdefault("null", True)
        kwargs.setdefault("blank", True)
        kwargs.setdefault("on_delete", models.SET_NULL)
        super().__init__(to, *args, **kwargs)


class OneToOneField(OneToOneField):
    def __init__(self, to, *args, **kwargs):
        kwargs.setdefault("on_delete", models.CASCADE)
        super().__init__(to, *args, **kwargs)


class OptionalEmailField(models.EmailField):
    """
    EmailField with null=True, blank=True by default.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("null", True)
        kwargs.setdefault("blank", True)
        super().__init__(*args, **kwargs)


class OptionalURLField(models.URLField):
    """
    EmailField with null=True, blank=True by default.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("null", True)
        kwargs.setdefault("blank", True)
        super().__init__(*args, **kwargs)


class LimitedDecimalField(models.DecimalField):
    """
    A DecimalField with optional min, max, and default value via positional args.

    Usage:
        LimitedDecimalField(0, 10, 5)     # min=0, max=10, default=5
        LimitedDecimalField(None, 100, 50)
        LimitedDecimalField(0, None, 1)
        LimitedDecimalField(5)           # min=5, no max
    """

    def __init__(self, *args, **kwargs):
        validators = kwargs.pop("validators", [])

        # Defaults
        min_value = None
        max_value = None
        default_value = None

        # Unpack arguments
        if len(args) == 1:
            min_value = args[0]
        elif len(args) == 2:
            min_value, max_value = args
        elif len(args) == 3:
            min_value, max_value, default_value = args
        elif len(args) > 3:
            raise TypeError("LimitedDecimalField accepts up to 3 positional arguments.")

        # Add validators
        if min_value is not None:
            validators.append(MinValueValidator(min_value))
        if max_value is not None:
            validators.append(MaxValueValidator(max_value))

        # Validate default is within range
        if default_value is not None:
            if (min_value is not None and default_value < min_value) or (
                max_value is not None and default_value > max_value
            ):
                raise ValueError("Default value is out of bounds.")
            kwargs.setdefault("default", default_value)

        kwargs["validators"] = validators
        kwargs.setdefault("max_digits", 10)
        kwargs.setdefault("decimal_places", 2)

        super().__init__(**kwargs)


class OptionalLimitedDecimalField(models.DecimalField):
    """
    A DecimalField with optional min, max, and default value via positional args.

    Usage:
        OptionalLimitedDecimalField(0, 10, 5)     # min=0, max=10, default=5
        OptionalLimitedDecimalField(None, 100, 50)
        OptionalLimitedDecimalField(0, None, 1)
        OptionalLimitedDecimalField(5)           # min=5, no max
    """

    def __init__(self, *args, **kwargs):
        validators = kwargs.pop("validators", [])

        # Defaults
        min_value = None
        max_value = None
        default_value = None

        # Unpack arguments
        if len(args) == 1:
            min_value = args[0]
        elif len(args) == 2:
            min_value, max_value = args
        elif len(args) == 3:
            min_value, max_value, default_value = args
        elif len(args) > 3:
            raise TypeError("LimitedDecimalField accepts up to 3 positional arguments.")

        # Add validators
        if min_value is not None:
            validators.append(MinValueValidator(min_value))
        if max_value is not None:
            validators.append(MaxValueValidator(max_value))

        # Validate default is within range
        if default_value is not None:
            if (min_value is not None and default_value < min_value) or (
                max_value is not None and default_value > max_value
            ):
                raise ValueError("Default value is out of bounds.")
            kwargs.setdefault("default", default_value)

        kwargs["validators"] = validators
        kwargs.setdefault("max_digits", 10)
        kwargs.setdefault("decimal_places", 2)
        kwargs.setdefault("null", True)
        kwargs.setdefault("blank", True)

        super().__init__(**kwargs)


class BaseArrayField(models.JSONField):
    def __init__(
        self,
        choices=None,
        base_type=str,
        min_items=None,
        max_items=None,
        **kwargs,
    ):
        kwargs.setdefault("blank", True)
        kwargs.setdefault("default", list)

        self.base_type = base_type
        self.min_items = min_items
        self.max_items = max_items

        if choices:
            if all(isinstance(c, (list, tuple)) for c in choices):
                self.choices = [(k, v) for k, v in choices]
                self.valid_choices = [k for k, _ in choices]
            else:
                self.choices = [(c, c) for c in choices]
                self.valid_choices = choices
        else:
            self.choices = None
            self.valid_choices = []

        super().__init__(**kwargs)
        self.validators.append(self._validate_array)

    def formfield(self, **kwargs):
        if self.valid_choices:
            return forms.MultipleChoiceField(
                choices=[(c, c) for c in self.valid_choices],
                widget=forms.SelectMultiple,
                required=not self.blank,
                **kwargs,
            )
        return forms.JSONField(required=not self.blank, **kwargs)

    def to_python(self, value):
        if isinstance(value, str):
            try:
                import json

                value = json.loads(value)
            except Exception:
                pass
        if isinstance(value, list):
            try:
                return [self.base_type(v) for v in value]
            except Exception:
                return value
        return value

    def _validate_array(self, value):
        if value is None:
            return
        if not isinstance(value, list):
            raise ValidationError("Value must be a list.")

        # Coerce each item
        coerced = []
        for item in value:
            try:
                item = self.base_type(item)  # e.g., int("4") → 4
            except (ValueError, TypeError):
                raise ValidationError(f"Invalid type: {item}")
            coerced.append(item)

        if self.min_items is not None and len(coerced) < self.min_items:
            raise ValidationError(f"Minimum {self.min_items} items required.")
        if self.max_items is not None and len(coerced) > self.max_items:
            raise ValidationError(f"Maximum {self.max_items} items allowed.")

        if self.valid_choices:
            for item in coerced:
                if item not in self.valid_choices:
                    raise ValidationError(f"{item} is not a valid choice.")


class StringArrayField(BaseArrayField):
    def __init__(self, **kwargs):
        super().__init__(base_type=str, **kwargs)


class NumberArrayField(BaseArrayField):
    def __init__(self, **kwargs):
        super().__init__(base_type=int, **kwargs)


class ChoicesStringArrayField(BaseArrayField):
    def __init__(self, choices=None, min_items=None, max_items=None, **kwargs):
        flat_choices = [
            (c[0], c[1]) if isinstance(c, (list, tuple)) else (c, str(c))
            for c in choices or []
        ]

        super().__init__(
            choices=flat_choices,
            base_type=str,
            min_items=min_items,
            max_items=max_items,
            **kwargs,
        )
        self._original_choices = choices
        self.min_items = min_items
        self.max_items = max_items

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        kwargs["choices"] = self._original_choices
        if self.min_items is not None:
            kwargs["min_items"] = self.min_items
        if self.max_items is not None:
            kwargs["max_items"] = self.max_items
        return name, path, args, kwargs


class ChoicesNumberArrayField(BaseArrayField):
    def __init__(self, choices=None, min_items=None, max_items=None, **kwargs):
        flat_choices = [
            c if isinstance(c, (list, tuple)) else (c, str(c)) for c in choices or []
        ]
        super().__init__(
            base_type=int,
            choices=flat_choices,
            min_items=min_items,
            max_items=max_items,
            **kwargs,
        )
        self._original_choices = choices
        self.min_items = min_items
        self.max_items = max_items

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        kwargs["choices"] = self._original_choices
        if self.min_items is not None:
            kwargs["min_items"] = self.min_items
        if self.max_items is not None:
            kwargs["max_items"] = self.max_items
        return name, path, args, kwargs


class FileField(models.FileField):
    def __init__(self, upload_to, *args, **kwargs):
        super().__init__(upload_to=upload_to, *args, **kwargs)
