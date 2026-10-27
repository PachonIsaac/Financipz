import uuid
from typing import Annotated

from pydantic import StringConstraints

from app.schemas.common import Input, Name, Output, PartialUpdate
from app.schemas.enums import CategoryType

Color = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^#[0-9a-fA-F]{6}$")]
Icon = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]


class CategoryCreate(Input):
    name: Name
    type: CategoryType
    # A subcategory hangs from a top-level category of the same type. There are only two levels.
    parent_id: uuid.UUID | None = None
    icon: Icon | None = None
    color: Color | None = None


class CategoryUpdate(PartialUpdate):
    """The type cannot change, because movements of that type may already use the category."""

    required_when_sent = frozenset({"name"})

    name: Name | None = None
    parent_id: uuid.UUID | None = None
    icon: Icon | None = None
    color: Color | None = None


class CategoryOut(Output):
    id: uuid.UUID
    parent_id: uuid.UUID | None
    name: str
    type: CategoryType
    icon: str | None
    color: str | None
