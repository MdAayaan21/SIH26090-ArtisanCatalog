"""
Member 6 — seeds the CraftBenchmark table with realistic default values per
craft category, used whenever a spoken description omits labor hours,
material cost, wage benchmark, or package dimensions.

Run with:  python -m app.seed_benchmarks
"""
from app.database import SessionLocal, Base, engine
from app.models import CraftBenchmark

BENCHMARKS = [
    dict(category="pottery", default_labor_hours=3, default_material_cost=80,
         default_wage_benchmark=45, default_length_cm=15, default_width_cm=15,
         default_height_cm=20, default_weight_kg=1.5, market_adjustment_pct=0.15),
    dict(category="weaving", default_labor_hours=24, default_material_cost=400,
         default_wage_benchmark=50, default_length_cm=200, default_width_cm=100,
         default_height_cm=2, default_weight_kg=0.6, market_adjustment_pct=0.20),
    dict(category="woodwork", default_labor_hours=6, default_material_cost=250,
         default_wage_benchmark=55, default_length_cm=30, default_width_cm=20,
         default_height_cm=15, default_weight_kg=2.0, market_adjustment_pct=0.18),
    dict(category="jewelry", default_labor_hours=4, default_material_cost=600,
         default_wage_benchmark=60, default_length_cm=10, default_width_cm=8,
         default_height_cm=3, default_weight_kg=0.1, market_adjustment_pct=0.25),
    dict(category="basketry", default_labor_hours=5, default_material_cost=60,
         default_wage_benchmark=40, default_length_cm=30, default_width_cm=30,
         default_height_cm=25, default_weight_kg=0.8, market_adjustment_pct=0.15),
    dict(category="metalwork", default_labor_hours=8, default_material_cost=350,
         default_wage_benchmark=55, default_length_cm=25, default_width_cm=20,
         default_height_cm=10, default_weight_kg=1.8, market_adjustment_pct=0.18),
    dict(category="embroidery", default_labor_hours=15, default_material_cost=200,
         default_wage_benchmark=48, default_length_cm=100, default_width_cm=80,
         default_height_cm=1, default_weight_kg=0.4, market_adjustment_pct=0.20),
    dict(category="painting", default_labor_hours=10, default_material_cost=150,
         default_wage_benchmark=50, default_length_cm=40, default_width_cm=30,
         default_height_cm=2, default_weight_kg=0.5, market_adjustment_pct=0.22),
    dict(category="other", default_labor_hours=5, default_material_cost=150,
         default_wage_benchmark=45, default_length_cm=20, default_width_cm=20,
         default_height_cm=10, default_weight_kg=1.0, market_adjustment_pct=0.15),
]


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        for row in BENCHMARKS:
            existing = db.query(CraftBenchmark).filter(CraftBenchmark.category == row["category"]).first()
            if existing:
                for k, v in row.items():
                    setattr(existing, k, v)
            else:
                db.add(CraftBenchmark(**row))
        db.commit()
        print(f"Seeded/updated {len(BENCHMARKS)} CraftBenchmark categories.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
