from decimal import Decimal
from typing import Annotated, Any, ClassVar

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, model_validator

def to_cents(value: Decimal) -> Decimal:
    """Always two decimals, so what the API answers is what the database stores ("250" becomes "250.00")."""
    return value.quantize(Decimal("0.01"))


# Amounts have at most 14 digits and 2 decimals, like the numeric(14,2) columns.
PositiveMoney = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2), AfterValidator(to_cents)]
Money = Annotated[Decimal, Field(max_digits=14, decimal_places=2), AfterValidator(to_cents)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class Input(BaseModel):
    """Base for request bodies: unknown fields are errors, so typos do not pass silently."""

    model_config = ConfigDict(extra="forbid")


class PartialUpdate(Input):
    """Base for PATCH bodies. Fields that were sent are in `model_fields_set`.

    A field that cannot be cleared lists itself in `required_when_sent`: sending it as null is an error.
    """

    required_when_sent: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="after")
    def reject_null_for_required_fields(self) -> "PartialUpdate":
        for name in self.model_fields_set & self.required_when_sent:
            if getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self

    def changes(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.model_fields_set}


class Output(BaseModel):
    model_config = ConfigDict(from_attributes=True)
