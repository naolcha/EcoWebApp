import sys
import os
import re
from pathlib import Path
import requests
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from dotenv import load_dotenv

sys.path.append(str(Path(__file__).resolve().parent.parent))

from database.connector import DatabaseConnector

load_dotenv()

API_KEY = "96f069b6-b53f-44f4-a267-0bdda015fae7"

URLS = {
    "eco": "https://apidata.mos.ru/v1/datasets/753/rows",
    "non_eco": "https://apidata.mos.ru/v1/datasets/754/rows",
}

def load_dataset(url):
    params = {"api_key": API_KEY}
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def safe_parse_date(date_str):
    if not date_str:
        return None
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except Exception:
            continue
    return None

def extract_coordinates(value):
    if not value:
        return None, None
    if isinstance(value, dict) and "coordinates" in value:
        coords = value["coordinates"]
        if isinstance(coords, list) and len(coords) >= 2:
            return coords[1], coords[0]
    if isinstance(value, str):
        nums = re.findall(r"[-+]?\d*\.\d+|\d+", value)
        if len(nums) >= 2:
            lon, lat = map(float, nums[:2])
            return lat, lon
    return None, None

def import_data():
    print("Инициализация базы данных и автообновление данных с data.mos.ru...")
    db = DatabaseConnector()
    db.create_tables()
    engine = db.engine

    with engine.begin() as conn:
        conn.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'reviews_station_id_fkey'
                ) THEN
                    ALTER TABLE reviews
                    ADD CONSTRAINT reviews_station_id_fkey
                        FOREIGN KEY (station_id)
                        REFERENCES stations (id)
                        ON DELETE CASCADE;
                ELSE
                    ALTER TABLE reviews
                    DROP CONSTRAINT reviews_station_id_fkey,
                    ADD CONSTRAINT reviews_station_id_fkey
                        FOREIGN KEY (station_id)
                        REFERENCES stations (id)
                        ON DELETE CASCADE;
                END IF;
            END $$;
        """))

        conn.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM   pg_indexes
                    WHERE  schemaname = ANY (current_schemas(true))
                    AND    indexname  = 'uq_stations_name_address'
                ) THEN
                    CREATE UNIQUE INDEX uq_stations_name_address
                        ON stations (name, address);
                END IF;
            END $$;
        """))

    Session = sessionmaker(bind=engine)
    session = Session()

    print("Обновление данных станций без удаления отзывов...")

    upsert_sql = text("""
    INSERT INTO stations
        (name, admarea, district, address, owner, test_date, eco_status, latitude, longitude, created_at, updated_at)
    VALUES
        (:name, :admarea, :district, :address, :owner, :test_date, :eco_status, :latitude, :longitude, NOW(), NOW())
    ON CONFLICT (name, address) DO UPDATE
    SET
        admarea   = EXCLUDED.admarea,
        district  = EXCLUDED.district,
        owner     = EXCLUDED.owner,
        test_date = EXCLUDED.test_date,
        eco_status= EXCLUDED.eco_status,
        latitude  = EXCLUDED.latitude,
        longitude = EXCLUDED.longitude,
        updated_at = NOW()
    """)


    added_total, updated_total = 0, 0

    with engine.begin() as conn:
        for key, url in URLS.items():
            print(f"Загрузка данных: {key}")
            try:
                data = load_dataset(url)
            except Exception as e:
                print(f"Ошибка загрузки {url}: {e}")
                continue

            added, updated = 0, 0
            for item in data:
                cells = item.get("Cells", {})
                name = cells.get("FullName")
                address = cells.get("Address")
                if not name or not address:
                    continue

                lat, lon = extract_coordinates(cells.get("geoData"))
                test_date = safe_parse_date(cells.get("TestDate"))

                params = {
                    "name": name,
                    "admarea": cells.get("AdmArea"),
                    "district": cells.get("District"),
                    "address": address,
                    "owner": cells.get("Owner"),
                    "test_date": test_date,
                    "eco_status": (key == "eco"),
                    "latitude": lat,
                    "longitude": lon,
                }

                before = conn.execute(text("""
                    SELECT 1 FROM stations WHERE name = :name AND address = :address
                """), {"name": name, "address": address}).first()

                conn.execute(upsert_sql, params)

                if before:
                    updated += 1
                else:
                    added += 1

            print(f"Импорт завершён: {added} новых, {updated} обновлено для набора '{key}'")
            added_total += added
            updated_total += updated

    session.close()
    print(f"Итого: добавлено {added_total}, обновлено {updated_total}. Импорт данных завершён без потери отзывов.")

if __name__ == "__main__":
    import_data()
