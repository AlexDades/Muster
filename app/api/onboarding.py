from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.onboarding.store import OnboardingStore
from app.config import settings

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


def get_onboarding_store() -> OnboardingStore:
    return OnboardingStore(db_path=settings.db_path)


class SequenceCreate(BaseModel):
    name: str
    description: str = ""


class StepCreate(BaseModel):
    doc_id: str
    doc_name: str
    day_offset: int = 0
    subject: str
    body: str


class EnrollRequest(BaseModel):
    sequence_id: int
    employee_name: str
    employee_email: str
    start_date: str


@router.get("/sequences")
def list_sequences(store: OnboardingStore = Depends(get_onboarding_store)) -> list[dict]:
    return store.list_sequences()


@router.post("/sequences", status_code=201)
def create_sequence(
    body: SequenceCreate,
    store: OnboardingStore = Depends(get_onboarding_store),
) -> dict:
    seq_id = store.create_sequence(name=body.name, description=body.description)
    return {"id": seq_id, "name": body.name, "description": body.description}


@router.delete("/sequences/{sequence_id}", status_code=204)
def delete_sequence(
    sequence_id: int,
    store: OnboardingStore = Depends(get_onboarding_store),
) -> None:
    store.delete_sequence(sequence_id)


@router.get("/sequences/{sequence_id}/steps")
def list_steps(
    sequence_id: int,
    store: OnboardingStore = Depends(get_onboarding_store),
) -> list[dict]:
    return store.list_steps(sequence_id)


@router.post("/sequences/{sequence_id}/steps", status_code=201)
def add_step(
    sequence_id: int,
    body: StepCreate,
    store: OnboardingStore = Depends(get_onboarding_store),
) -> dict:
    step_id = store.add_step(
        sequence_id=sequence_id,
        doc_id=body.doc_id,
        doc_name=body.doc_name,
        day_offset=body.day_offset,
        subject=body.subject,
        body=body.body,
    )
    return {
        "id": step_id,
        "sequence_id": sequence_id,
        "doc_id": body.doc_id,
        "doc_name": body.doc_name,
        "day_offset": body.day_offset,
        "subject": body.subject,
        "body": body.body,
    }


@router.delete("/sequences/{sequence_id}/steps/{step_id}", status_code=204)
def delete_step(
    sequence_id: int,
    step_id: int,
    store: OnboardingStore = Depends(get_onboarding_store),
) -> None:
    store.delete_step(step_id)


@router.get("/enrollments")
def list_enrollments(store: OnboardingStore = Depends(get_onboarding_store)) -> list[dict]:
    return store.list_enrollments()


@router.post("/enrollments", status_code=201)
def enroll_employee(
    body: EnrollRequest,
    store: OnboardingStore = Depends(get_onboarding_store),
) -> dict:
    if not store.get_sequence(body.sequence_id):
        raise HTTPException(status_code=404, detail="Sequence not found.")
    enrollment_id = store.enroll(
        sequence_id=body.sequence_id,
        employee_name=body.employee_name,
        employee_email=body.employee_email,
        start_date=body.start_date,
    )
    return {
        "id": enrollment_id,
        "sequence_id": body.sequence_id,
        "employee_name": body.employee_name,
        "employee_email": body.employee_email,
        "start_date": body.start_date,
    }


@router.delete("/enrollments/{enrollment_id}", status_code=204)
def cancel_enrollment(
    enrollment_id: int,
    store: OnboardingStore = Depends(get_onboarding_store),
) -> None:
    store.cancel_enrollment(enrollment_id)
