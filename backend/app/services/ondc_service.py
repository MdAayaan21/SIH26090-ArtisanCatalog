"""
Member 6 — ONDC Beckn Protocol Exporter.

Serializes a fully CONFIRMED Product record into a Beckn-compliant
on_search catalog fragment (seller-side "provider > items" payload), the
format ONDC network gateways expect when a buyer app searches the network.

Reference: https://github.com/ONDC-Official/ONDC-Protocol-Specs (retail /
grocery / handicrafts vertical catalog schema).
"""
import uuid
from datetime import datetime, timezone

from ..config import settings
from ..models import Product, Artisan


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def build_beckn_catalog_item(product: Product, artisan: Artisan) -> dict:
    """Builds the `items[]` entry plus wrapping provider/context envelope
    for a single confirmed product. Multiple items can share one provider
    envelope when batch-exporting an artisan's whole catalog."""

    item_id = product.id
    images = product.processed_photo_paths or product.raw_photo_paths or []

    item = {
        "id": item_id,
        "descriptor": {
            "name": product.title,
            "short_desc": product.description,
            "long_desc": product.description,
            "images": images,
        },
        "category_id": _map_category_to_ondc(product.category),
        "price": {
            "currency": "INR",
            "value": f"{product.suggested_price:.2f}" if product.suggested_price else "0.00",
        },
        "quantity": {
            "available": {"count": str(product.quantity_available or 1)},
            "maximum": {"count": str(product.quantity_available or 1)},
        },
        "@ondc/org/returnable": False,
        "@ondc/org/cancellable": True,
        "@ondc/org/seller_pickup_return": False,
        "@ondc/org/time_to_ship": "P2D",
        "@ondc/org/available_on_cod": True,
        "@ondc/org/contact_details_consumer_care": "support@artisan-marketlink.example",
        "@ondc/org/statutory_reqs_packaged_commodities": {
            "manufacturer_or_packer_name": artisan.full_name,
            "manufacturer_or_packer_address": f"{artisan.village}, {artisan.district}, {artisan.state}",
        },
        "matched": True,
        "related": False,
        "recommended": False,
    }

    if product.weight_kg or product.length_cm or product.width_cm or product.height_cm:
        item["@ondc/org/attributes"] = {
            "weight_kg": product.weight_kg,
            "length_cm": product.length_cm,
            "width_cm": product.width_cm,
            "height_cm": product.height_cm,
        }

    provider = {
        "id": settings.ondc_provider_id,
        "descriptor": {"name": f"{artisan.full_name} Handicrafts"},
        "locations": [
            {
                "id": f"loc-{artisan.id}",
                "address": {
                    "locality": artisan.village,
                    "district": artisan.district,
                    "state": artisan.state,
                    "country": "IND",
                },
            }
        ],
        "items": [item],
    }

    envelope = {
        "context": {
            "domain": "ONDC:RET18",  # handicrafts / home & decor retail vertical
            "action": "on_search",
            "core_version": "1.2.0",
            "bap_id": None,          # filled in by the gateway when relaying to a buyer app
            "bpp_id": settings.ondc_bpp_id,
            "bpp_uri": settings.ondc_bpp_uri,
            "transaction_id": str(uuid.uuid4()),
            "message_id": str(uuid.uuid4()),
            "timestamp": _iso_now(),
            "ttl": "PT30S",
        },
        "message": {
            "catalog": {
                "bpp/descriptor": {"name": "Artisan Market Linkage Network"},
                "bpp/providers": [provider],
            }
        },
    }
    return envelope


_CATEGORY_MAP = {
    "pottery": "Home & Decor",
    "weaving": "Fashion & Apparel",
    "woodwork": "Home & Decor",
    "jewelry": "Fashion & Accessories",
    "basketry": "Home & Decor",
    "metalwork": "Home & Decor",
    "embroidery": "Fashion & Apparel",
    "painting": "Art & Decor",
    "other": "Home & Decor",
}


def _map_category_to_ondc(category: str) -> str:
    return _CATEGORY_MAP.get((category or "other").lower(), "Home & Decor")


def validate_ready_for_export(product: Product) -> list[str]:
    """Returns a list of validation errors; empty list means export-ready.
    Called before export so a half-confirmed product never reaches ONDC."""
    errors = []
    status_value = getattr(product.status, "value", product.status)
    if status_value not in ("confirmed", "exported"):
        errors.append("Product must be in CONFIRMED status before export.")
    if not product.title:
        errors.append("Missing title.")
    if not product.suggested_price:
        errors.append("Missing suggested_price.")
    if not (product.processed_photo_paths or product.raw_photo_paths):
        errors.append("Missing at least one product photo.")
    return errors
