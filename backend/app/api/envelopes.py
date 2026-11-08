import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.envelopes import (
    EntryCreate,
    EntryOut,
    EnvelopeCreate,
    EnvelopeList,
    EnvelopeOut,
    EnvelopePay,
    EnvelopeUpdate,
    PayResult,
)
from app.services import envelopes as service

router = APIRouter(prefix="/envelopes", tags=["envelopes"])


@router.get("", response_model=EnvelopeList)
def list_envelopes(db: Session = Depends(get_db)):
    """Envelopes with what each holds, the suggested contribution of the month and the totals."""
    return service.list_envelopes(db)


@router.post("", response_model=EnvelopeOut, status_code=201)
def create_envelope(data: EnvelopeCreate, db: Session = Depends(get_db)):
    return service.create_envelope(db, data)


@router.patch("/{envelope_id}", response_model=EnvelopeOut)
def update_envelope(envelope_id: uuid.UUID, data: EnvelopeUpdate, db: Session = Depends(get_db)):
    return service.update_envelope(db, envelope_id, data)


@router.delete("/{envelope_id}", status_code=204)
def delete_envelope(envelope_id: uuid.UUID, db: Session = Depends(get_db)):
    """Archives an empty envelope. One that still holds money has to be freed or paid first."""
    service.archive_envelope(db, envelope_id)
    return Response(status_code=204)


@router.get("/{envelope_id}/entries", response_model=list[EntryOut])
def list_entries(envelope_id: uuid.UUID, db: Session = Depends(get_db)):
    return service.list_entries(db, envelope_id)


@router.post("/{envelope_id}/entries", response_model=EnvelopeOut, status_code=201)
def add_entry(envelope_id: uuid.UUID, data: EntryCreate, db: Session = Depends(get_db)):
    """Set money apart (it never exceeds what is available) or free it again. Neither is an expense."""
    return service.add_entry(db, envelope_id, data)


@router.post("/{envelope_id}/pay", response_model=PayResult)
def pay_with_envelope(envelope_id: uuid.UUID, data: EnvelopePay, db: Session = Depends(get_db)):
    """Record the payment as an expense and free that amount from the envelope."""
    return service.pay(db, envelope_id, data)
