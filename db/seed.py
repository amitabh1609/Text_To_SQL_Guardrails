"""
Seed the supply chain database with realistic fake data using Faker.
Run: python db/seed.py
Produces: 100 suppliers, 300 products, 20 warehouses, ~1800 inventory rows,
          2000 purchase orders, ~1600 shipments.
"""
import os
import random
import sys
from datetime import date, timedelta

from dotenv import load_dotenv
from faker import Faker
from sqlalchemy import create_engine, text

load_dotenv()

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://supplychain:supplychain@localhost:5432/supplychain",
)

fake = Faker()
random.seed(42)
Faker.seed(42)

# -------------------------------------------------------------------------
# Domain constants
# -------------------------------------------------------------------------
COUNTRIES = ["India", "China", "Germany", "USA", "Japan", "Vietnam", "Mexico",
             "Brazil", "South Korea", "Thailand", "Singapore", "UK", "France"]

CATEGORIES = ["Electronics", "Mechanical Parts", "Chemicals", "Packaging",
              "Raw Materials", "Fasteners", "Hydraulics", "Electrical",
              "Safety Equipment", "Tools"]

CARRIERS = ["DHL", "FedEx", "UPS", "Maersk", "MSC", "COSCO", "DB Schenker",
            "Kuehne+Nagel", "Expeditors", "Blue Dart"]

STATUSES = ["pending", "shipped", "delivered", "cancelled"]
STATUS_WEIGHTS = [0.15, 0.10, 0.65, 0.10]

WAREHOUSE_CITIES = [
    ("Mumbai", "India"), ("Delhi", "India"), ("Pune", "India"),
    ("Shanghai", "China"), ("Shenzhen", "China"),
    ("Hamburg", "Germany"), ("Frankfurt", "Germany"),
    ("Chicago", "USA"), ("Houston", "USA"),
    ("Tokyo", "Japan"), ("Osaka", "Japan"),
    ("Ho Chi Minh City", "Vietnam"),
    ("Singapore", "Singapore"),
    ("Seoul", "South Korea"),
    ("Bangkok", "Thailand"),
    ("São Paulo", "Brazil"),
    ("Monterrey", "Mexico"),
    ("London", "UK"),
    ("Lyon", "France"),
    ("Busan", "South Korea"),
]


def seed_suppliers(conn, n: int = 100) -> list[int]:
    ids = []
    for _ in range(n):
        onboarded = fake.date_between(start_date=date(2015, 1, 1), end_date=date(2023, 12, 31))
        rating = round(random.uniform(1.5, 5.0), 1)
        is_active = random.random() > 0.12  # 12% inactive
        row = conn.execute(
            text(
                "INSERT INTO suppliers (supplier_name, country, rating, is_active, onboarded_at) "
                "VALUES (:name, :country, :rating, :active, :onboarded) RETURNING supplier_id"
            ),
            {
                "name": fake.company(),
                "country": random.choice(COUNTRIES),
                "rating": rating,
                "active": is_active,
                "onboarded": onboarded,
            },
        )
        ids.append(row.scalar())
    print(f"  Seeded {n} suppliers")
    return ids


def seed_products(conn, n: int = 300) -> list[int]:
    ids = []
    used_skus: set[str] = set()
    for i in range(n):
        sku = fake.bothify("SKU-????-####").upper()
        while sku in used_skus:
            sku = fake.bothify("SKU-????-####").upper()
        used_skus.add(sku)
        unit_cost = round(random.uniform(0.50, 5000.00), 2)
        reorder_level = random.randint(10, 500)
        is_disc = random.random() < 0.08  # 8% discontinued
        row = conn.execute(
            text(
                "INSERT INTO products (sku, product_name, category, unit_cost, reorder_level, is_discontinued) "
                "VALUES (:sku, :name, :cat, :cost, :reorder, :disc) RETURNING product_id"
            ),
            {
                "sku": sku,
                "name": fake.catch_phrase()[:190],
                "cat": random.choice(CATEGORIES),
                "cost": unit_cost,
                "reorder": reorder_level,
                "disc": is_disc,
            },
        )
        ids.append(row.scalar())
    print(f"  Seeded {n} products")
    return ids


def seed_warehouses(conn) -> list[int]:
    ids = []
    for city, country in WAREHOUSE_CITIES:
        capacity = random.randint(5_000, 100_000)
        row = conn.execute(
            text(
                "INSERT INTO warehouses (warehouse_name, city, country, capacity_units) "
                "VALUES (:name, :city, :country, :cap) RETURNING warehouse_id"
            ),
            {
                "name": f"{city} Distribution Center",
                "city": city,
                "country": country,
                "cap": capacity,
            },
        )
        ids.append(row.scalar())
    print(f"  Seeded {len(WAREHOUSE_CITIES)} warehouses")
    return ids


def seed_inventory(conn, product_ids: list[int], warehouse_ids: list[int]) -> None:
    count = 0
    for p_id in product_ids:
        # Each product is stocked in 3–8 warehouses
        whs = random.sample(warehouse_ids, k=min(random.randint(3, 8), len(warehouse_ids)))
        for w_id in whs:
            qty = random.randint(0, 5_000)
            conn.execute(
                text(
                    "INSERT INTO inventory (product_id, warehouse_id, quantity_on_hand, last_updated) "
                    "VALUES (:pid, :wid, :qty, NOW() - INTERVAL ':days days')"
                    .replace(":days", str(random.randint(0, 90)))
                ),
                {"pid": p_id, "wid": w_id, "qty": qty},
            )
            count += 1
    print(f"  Seeded {count} inventory rows")


def seed_purchase_orders(
    conn,
    supplier_ids: list[int],
    product_ids: list[int],
    warehouse_ids: list[int],
    n: int = 2000,
) -> list[int]:
    ids = []
    for _ in range(n):
        order_date = fake.date_between(start_date=date(2022, 1, 1), end_date=date(2025, 3, 31))
        lead_days = random.randint(5, 90)
        expected_delivery = order_date + timedelta(days=lead_days)
        status = random.choices(STATUSES, weights=STATUS_WEIGHTS, k=1)[0]

        actual_delivery = None
        if status == "delivered":
            delay_days = random.choices(
                [-5, -3, 0, 3, 7, 14, 30],
                weights=[0.05, 0.10, 0.30, 0.25, 0.15, 0.10, 0.05],
                k=1,
            )[0]
            actual_delivery = expected_delivery + timedelta(days=delay_days)
            # Clamp to a reasonable past date
            if actual_delivery > date(2025, 4, 30):
                actual_delivery = date(2025, 4, 30)

        unit_price = round(random.uniform(0.50, 4500.00), 2)
        row = conn.execute(
            text(
                "INSERT INTO purchase_orders "
                "(supplier_id, product_id, warehouse_id, quantity_ordered, unit_price, "
                " order_date, expected_delivery, actual_delivery, status) "
                "VALUES (:sid, :pid, :wid, :qty, :price, :odate, :edate, :adate, :status) "
                "RETURNING po_id"
            ),
            {
                "sid": random.choice(supplier_ids),
                "pid": random.choice(product_ids),
                "wid": random.choice(warehouse_ids),
                "qty": random.randint(1, 10_000),
                "price": unit_price,
                "odate": order_date,
                "edate": expected_delivery,
                "adate": actual_delivery,
                "status": status,
            },
        )
        ids.append(row.scalar())
    print(f"  Seeded {n} purchase orders")
    return ids


def seed_shipments(conn, po_ids: list[int], po_statuses: dict[int, str]) -> None:
    count = 0
    shipped_statuses = {"shipped", "delivered"}
    for po_id in po_ids:
        if po_statuses.get(po_id) not in shipped_statuses:
            continue
        shipped_at = fake.date_time_between(start_date="-2y", end_date="now")
        delivered_at = None
        if po_statuses[po_id] == "delivered":
            delivered_at = shipped_at + timedelta(days=random.randint(1, 45))
        conn.execute(
            text(
                "INSERT INTO shipments (po_id, shipped_at, delivered_at, carrier, tracking_number) "
                "VALUES (:po, :shipped, :delivered, :carrier, :tracking)"
            ),
            {
                "po": po_id,
                "shipped": shipped_at,
                "delivered": delivered_at,
                "carrier": random.choice(CARRIERS),
                "tracking": fake.bothify("??##########??").upper(),
            },
        )
        count += 1
    print(f"  Seeded {count} shipments")


def main() -> None:
    print(f"Connecting to: {DATABASE_URL[:50]}...")
    engine = create_engine(DATABASE_URL)

    with engine.begin() as conn:
        print("Truncating existing data...")
        conn.execute(text("TRUNCATE shipments, purchase_orders, inventory, warehouses, products, suppliers RESTART IDENTITY CASCADE"))

        print("Seeding data...")
        supplier_ids = seed_suppliers(conn, 100)
        product_ids = seed_products(conn, 300)
        warehouse_ids = seed_warehouses(conn)
        seed_inventory(conn, product_ids, warehouse_ids)
        po_ids = seed_purchase_orders(conn, supplier_ids, product_ids, warehouse_ids, 2000)

        # Fetch statuses for shipment seeding
        result = conn.execute(text("SELECT po_id, status FROM purchase_orders"))
        po_statuses = {row[0]: row[1] for row in result.fetchall()}
        seed_shipments(conn, po_ids, po_statuses)

    print("\nSeed complete!")
    with engine.connect() as conn:
        for tbl in ["suppliers", "products", "warehouses", "inventory", "purchase_orders", "shipments"]:
            n = conn.execute(text(f"SELECT COUNT(*) FROM {tbl}")).scalar()
            print(f"  {tbl}: {n:,} rows")


if __name__ == "__main__":
    main()
