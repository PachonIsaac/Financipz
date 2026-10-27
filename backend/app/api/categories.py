import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.categories import CategoryCreate, CategoryOut, CategoryUpdate
from app.schemas.enums import CategoryType
from app.services import categories as service

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryOut])
def list_categories(type: CategoryType | None = None, db: Session = Depends(get_db)):
    """Flat list. Subcategories point to their main category through `parent_id`."""
    return service.list_categories(db, type)


@router.post("", response_model=CategoryOut, status_code=201)
def create_category(data: CategoryCreate, db: Session = Depends(get_db)):
    return service.create_category(db, data)


@router.patch("/{category_id}", response_model=CategoryOut)
def update_category(category_id: uuid.UUID, data: CategoryUpdate, db: Session = Depends(get_db)):
    return service.update_category(db, category_id, data)


@router.delete("/{category_id}", status_code=204)
def delete_category(category_id: uuid.UUID, reassign_to: uuid.UUID | None = None, db: Session = Depends(get_db)):
    """Delete a category. If it has movements, `reassign_to` says which category receives them."""
    service.delete_category(db, category_id, reassign_to)
    return Response(status_code=204)
