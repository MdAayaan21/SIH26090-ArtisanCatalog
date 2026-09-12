"""
Member 6 — ONDC export endpoint. Only CONFIRMED products may be exported;
validate_ready_for_export enforces this so a half-confirmed listing never
reaches the network.
"""
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Product, ProductStatus, Artisan
from ..services import ondc_service

router = APIRouter(prefix="/ondc", tags=["ondc"])


@router.post("/export/{product_id}")
def export_product_to_ondc(product_id: str, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None:
        raise HTTPException(404, "Product not found")

    artisan = db.query(Artisan).filter(Artisan.id == product.artisan_id).first()
    if artisan is None:
        raise HTTPException(404, "Artisan not found")

    errors = ondc_service.validate_ready_for_export(product)
    if errors:
        raise HTTPException(422, {"message": "Product is not export-ready", "errors": errors})

    catalog_json = ondc_service.build_beckn_catalog_item(product, artisan)

    product.ondc_catalog_json = catalog_json
    product.status = ProductStatus.EXPORTED
    product.exported_at = datetime.utcnow()
    db.commit()
    db.refresh(product)

    return {"product_id": product.id, "status": product.status.value, "catalog": catalog_json}


@router.get("/catalog/{artisan_id}")
def get_full_catalog(artisan_id: str, db: Session = Depends(get_db)):
    """Returns a combined on_search-style catalog for every exported product
    belonging to one artisan — useful for a single ONDC provider registration
    covering their whole shop."""
    products = (
        db.query(Product)
        .filter(Product.artisan_id == artisan_id, Product.status == ProductStatus.EXPORTED)
        .all()
    )
    return {"artisan_id": artisan_id, "exported_products": [p.ondc_catalog_json for p in products]}
