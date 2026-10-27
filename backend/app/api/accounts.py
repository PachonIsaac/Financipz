import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.accounts import (
    AccountCreate,
    AccountOut,
    AccountUpdate,
    IdentifierOut,
    IdentifiersReplace,
)
from app.schemas.transactions import AdjustmentCreate, AdjustmentResult
from app.services import accounts as service
from app.services.transactions import create_adjustment

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountOut])
def list_accounts(archived: bool | None = None, db: Session = Depends(get_db)):
    """Accounts with their computed balance. Use `archived=false` to hide archived ones."""
    return service.list_accounts(db, archived)


@router.post("", response_model=AccountOut, status_code=201)
def create_account(data: AccountCreate, db: Session = Depends(get_db)):
    return service.create_account(db, data)


@router.get("/{account_id}", response_model=AccountOut)
def get_account(account_id: uuid.UUID, db: Session = Depends(get_db)):
    return service.get_account_out(db, account_id)


@router.patch("/{account_id}", response_model=AccountOut)
def update_account(account_id: uuid.UUID, data: AccountUpdate, db: Session = Depends(get_db)):
    """Edit an account or archive it. Accounts are never deleted: their movements are kept."""
    return service.update_account(db, account_id, data)


@router.get("/{account_id}/identifiers", response_model=list[IdentifierOut])
def list_identifiers(account_id: uuid.UUID, db: Session = Depends(get_db)):
    return service.list_identifiers(db, account_id)


@router.put("/{account_id}/identifiers", response_model=list[IdentifierOut])
def replace_identifiers(account_id: uuid.UUID, data: IdentifiersReplace, db: Session = Depends(get_db)):
    """Replace the last digits that identify this account in notifications."""
    return service.replace_identifiers(db, account_id, data.identifiers)


@router.post("/{account_id}/adjustments", response_model=AdjustmentResult, status_code=201)
def adjust_balance(account_id: uuid.UUID, data: AdjustmentCreate, response: Response, db: Session = Depends(get_db)):
    """Take the balance to the observed value. Answers 200 and records nothing if it already matches."""
    result = create_adjustment(db, account_id, data)
    if result.transaction is None:
        response.status_code = 200
    return result
