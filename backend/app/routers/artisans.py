from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Artisan
from ..schemas import ArtisanCreate, ArtisanOut

router = APIRouter(prefix="/artisans", tags=["artisans"])


@router.post("", response_model=ArtisanOut)
def create_artisan(payload: ArtisanCreate, db: Session = Depends(get_db)):
    existing = db.query(Artisan).filter(Artisan.phone_number == payload.phone_number).first()
    if existing:
        return existing  # idempotent onboarding — re-registering the same phone is a no-op
    artisan = Artisan(**payload.model_dump())
    db.add(artisan)
    db.commit()
    db.refresh(artisan)
    return artisan


@router.get("/{artisan_id}", response_model=ArtisanOut)
def get_artisan(artisan_id: str, db: Session = Depends(get_db)):
    artisan = db.query(Artisan).filter(Artisan.id == artisan_id).first()
    if artisan is None:
        raise HTTPException(404, "Artisan not found")
    return artisan


@router.get("", response_model=list[ArtisanOut])
def list_artisans(db: Session = Depends(get_db)):
    return db.query(Artisan).all()
