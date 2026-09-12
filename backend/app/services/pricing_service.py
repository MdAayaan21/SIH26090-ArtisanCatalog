"""
Member 6 — Cost-Plus Pricing Formula & Category Benchmark Fallbacks.

    Suggested Price = Material Cost + (Labor Hours x Wage Benchmark) + Market Adjustment

Any field missing from the artisan's spoken description (because they didn't
mention it) is backfilled from the CraftBenchmark table for their category,
so a price can always be produced — transparently, with the fallback flagged
so the UI can show the artisan which numbers were assumed.
"""
import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from ..models import CraftBenchmark

logger = logging.getLogger("pricing_service")

DEFAULT_CATEGORY = "other"


@dataclass
class PriceResult:
    suggested_price: float
    material_cost: float
    labor_hours: float
    wage_benchmark: float
    labor_cost: float
    market_adjustment: float
    used_benchmark_fallback: bool

    def breakdown(self) -> dict:
        return {
            "material_cost": round(self.material_cost, 2),
            "labor_hours": round(self.labor_hours, 2),
            "wage_benchmark_per_hour": round(self.wage_benchmark, 2),
            "labor_cost": round(self.labor_cost, 2),
            "market_adjustment": round(self.market_adjustment, 2),
            "suggested_price": round(self.suggested_price, 2),
            "used_benchmark_fallback": self.used_benchmark_fallback,
        }


def _get_benchmark(db: Session, category: Optional[str]) -> CraftBenchmark:
    category = category or DEFAULT_CATEGORY
    benchmark = db.query(CraftBenchmark).filter(CraftBenchmark.category == category).first()
    if benchmark is None:
        benchmark = db.query(CraftBenchmark).filter(CraftBenchmark.category == DEFAULT_CATEGORY).first()
    if benchmark is None:
        raise RuntimeError(
            "No CraftBenchmark rows seeded — run seed_benchmarks.py before pricing any product."
        )
    return benchmark


def calculate_price(
    db: Session,
    category: Optional[str],
    material_cost: Optional[float],
    labor_hours: Optional[float],
) -> PriceResult:
    """Applies the cost-plus formula, filling any missing input from the
    category's CraftBenchmark row and flagging whether a fallback was used."""
    benchmark = _get_benchmark(db, category)
    used_fallback = False

    if material_cost is None:
        material_cost = benchmark.default_material_cost
        used_fallback = True
    if labor_hours is None:
        labor_hours = benchmark.default_labor_hours
        used_fallback = True

    wage_benchmark = benchmark.default_wage_benchmark
    labor_cost = labor_hours * wage_benchmark
    subtotal = material_cost + labor_cost
    market_adjustment = subtotal * benchmark.market_adjustment_pct
    suggested_price = subtotal + market_adjustment

    return PriceResult(
        suggested_price=suggested_price,
        material_cost=material_cost,
        labor_hours=labor_hours,
        wage_benchmark=wage_benchmark,
        labor_cost=labor_cost,
        market_adjustment=market_adjustment,
        used_benchmark_fallback=used_fallback,
    )


def fill_dimension_fallbacks(db: Session, category: Optional[str], weight_kg, length_cm, width_cm, height_cm):
    """Fills any missing package dimensions from the benchmark, needed for
    ONDC catalog export (shipping requires these)."""
    benchmark = _get_benchmark(db, category)
    return {
        "weight_kg": weight_kg if weight_kg is not None else benchmark.default_weight_kg,
        "length_cm": length_cm if length_cm is not None else benchmark.default_length_cm,
        "width_cm": width_cm if width_cm is not None else benchmark.default_width_cm,
        "height_cm": height_cm if height_cm is not None else benchmark.default_height_cm,
    }
