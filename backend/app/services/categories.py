import uuid

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db import models
from app.schemas.categories import CategoryCreate, CategoryUpdate
from app.schemas.enums import CategoryType
from app.services.common import get_or_404


def get_category(db: Session, category_id: uuid.UUID) -> models.Category:
    return get_or_404(db, models.Category, category_id, "La categoría no existe.")


def list_categories(db: Session, category_type: CategoryType | None) -> list[models.Category]:
    query = select(models.Category).order_by(models.Category.type, models.Category.name)
    if category_type is not None:
        query = query.where(models.Category.type == category_type.value)
    return list(db.scalars(query))


def create_category(db: Session, data: CategoryCreate) -> models.Category:
    _check_parent(db, data.parent_id, data.type.value, category_id=None)
    _check_name_is_free(db, data.name, data.type.value, data.parent_id, exclude=None)

    row = models.Category(
        id=uuid.uuid4(),
        parent_id=data.parent_id,
        name=data.name,
        type=data.type.value,
        icon=data.icon,
        color=data.color,
    )
    db.add(row)
    _commit(db)
    return row


def update_category(db: Session, category_id: uuid.UUID, data: CategoryUpdate) -> models.Category:
    row = get_category(db, category_id)
    changes = data.changes()

    parent_id = changes.get("parent_id", row.parent_id)
    name = changes.get("name", row.name)
    if "parent_id" in changes:
        _check_parent(db, parent_id, row.type, category_id=row.id)
    if "parent_id" in changes or "name" in changes:
        _check_name_is_free(db, name, row.type, parent_id, exclude=row.id)

    for field, value in changes.items():
        setattr(row, field, value)
    _commit(db)
    return row


def delete_category(db: Session, category_id: uuid.UUID, reassign_to: uuid.UUID | None) -> None:
    """Delete a category. If movements use it, they must move to `reassign_to` first.

    Rules and budgets that point to the category are deleted with it.
    """
    row = get_category(db, category_id)

    has_children = db.scalar(select(func.count()).select_from(models.Category).where(models.Category.parent_id == row.id))
    if has_children:
        raise ApiError(409, "category_has_children", "Primero elimina o mueve sus subcategorías.")

    in_use = db.scalar(
        select(func.count()).select_from(models.Transaction).where(models.Transaction.category_id == row.id)
    )
    if in_use:
        if reassign_to is None:
            raise ApiError(
                409,
                "category_in_use",
                "La categoría tiene movimientos. Elige a cuál categoría pasarlos.",
                {"transactions": in_use},
            )
        target = db.get(models.Category, reassign_to)
        if target is None or target.id == row.id:
            raise ApiError(422, "invalid_reassign_target", "La categoría de destino no es válida.")
        if target.type != row.type:
            raise ApiError(422, "category_type_mismatch", "La categoría de destino debe ser del mismo tipo.")
        db.execute(
            update(models.Transaction)
            .where(models.Transaction.category_id == row.id)
            .values(category_id=target.id)
        )

    db.delete(row)
    db.commit()


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "conflict", "Los datos chocan con algo que ya existe.") from None


def _check_parent(db: Session, parent_id: uuid.UUID | None, category_type: str, category_id: uuid.UUID | None) -> None:
    if parent_id is None:
        return
    if parent_id == category_id:
        raise ApiError(422, "invalid_parent", "Una categoría no puede ser su propia subcategoría.")
    parent = db.get(models.Category, parent_id)
    if parent is None:
        raise ApiError(422, "parent_not_found", "La categoría principal no existe.")
    if parent.parent_id is not None:
        raise ApiError(422, "invalid_parent", "Solo hay dos niveles: una subcategoría no puede tener hijas.")
    if parent.type != category_type:
        raise ApiError(422, "category_type_mismatch", "La subcategoría debe ser del mismo tipo que la principal.")
    if category_id is not None:
        has_children = db.scalar(
            select(func.count()).select_from(models.Category).where(models.Category.parent_id == category_id)
        )
        if has_children:
            raise ApiError(422, "invalid_parent", "Una categoría con subcategorías no puede volverse subcategoría.")


def _check_name_is_free(
    db: Session, name: str, category_type: str, parent_id: uuid.UUID | None, exclude: uuid.UUID | None
) -> None:
    query = select(models.Category.id).where(
        func.lower(models.Category.name) == name.lower(),
        models.Category.type == category_type,
        models.Category.parent_id == parent_id if parent_id is not None else models.Category.parent_id.is_(None),
    )
    if exclude is not None:
        query = query.where(models.Category.id != exclude)
    if db.scalar(query) is not None:
        raise ApiError(409, "category_exists", "Ya existe una categoría con ese nombre.")
