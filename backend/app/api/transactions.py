import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domain.entities import TransactionStatus, TransactionType
from app.schemas.transactions import TransactionCreate, TransactionOut, TransactionPage, TransactionUpdate
from app.services import transactions as service
from app.services.transactions import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, TransactionFilters

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("", response_model=TransactionPage)
def list_transactions(
    date_from: date | None = Query(None, alias="from", description="First day, in Colombian time"),
    date_to: date | None = Query(None, alias="to", description="Last day, included"),
    account_id: uuid.UUID | None = None,
    category_id: uuid.UUID | None = None,
    type: TransactionType | None = None,
    status: TransactionStatus | None = None,
    q: str | None = Query(None, max_length=100, description="Text in the merchant or the note"),
    cursor: str | None = None,
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
):
    """Newest first. `account_id` matches both the source and the destination of a transfer.

    Discarded movements are left out unless `status=discarded` is asked for.
    """
    filters = TransactionFilters(
        date_from=date_from,
        date_to=date_to,
        account_id=account_id,
        category_id=category_id,
        type=type,
        status=status,
        text=q,
    )
    rows, next_cursor = service.list_transactions(db, filters, cursor, limit)
    return TransactionPage(items=[TransactionOut.model_validate(row) for row in rows], next_cursor=next_cursor)


@router.post("", response_model=TransactionOut, status_code=201)
def create_transaction(data: TransactionCreate, db: Session = Depends(get_db)):
    """Manual entry, confirmed right away."""
    return service.create_transaction(db, data)


@router.get("/{transaction_id}", response_model=TransactionOut)
def get_transaction(transaction_id: uuid.UUID, db: Session = Depends(get_db)):
    return service.get_transaction(db, transaction_id)


@router.patch("/{transaction_id}", response_model=TransactionOut)
def update_transaction(transaction_id: uuid.UUID, data: TransactionUpdate, db: Session = Depends(get_db)):
    """Balances are computed from movements, so they follow any change automatically."""
    return service.update_transaction(db, transaction_id, data)


@router.delete("/{transaction_id}", status_code=204)
def delete_transaction(transaction_id: uuid.UUID, db: Session = Depends(get_db)):
    """Only manual entries. Automatic ones are discarded so they are not processed again."""
    service.delete_transaction(db, transaction_id)
    return Response(status_code=204)


@router.post("/{transaction_id}/confirm", response_model=TransactionOut)
def confirm_transaction(transaction_id: uuid.UUID, db: Session = Depends(get_db)):
    return service.confirm_transaction(db, transaction_id)


@router.post("/{transaction_id}/discard", response_model=TransactionOut)
def discard_transaction(transaction_id: uuid.UUID, db: Session = Depends(get_db)):
    return service.discard_transaction(db, transaction_id)
