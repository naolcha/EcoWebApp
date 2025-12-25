from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import bcrypt
from sqlalchemy import text
from sqlalchemy.orm import Session


class UserCRUD:
    @staticmethod
    def create_user(db: Session, username: str, email: str, password: str, role_id: int = 1) -> Dict[str, Any]:
        hashed_password = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        db.execute(
            text("""
                INSERT INTO users (username, email, hashed_password, role_id, created_at, updated_at)
                VALUES (:username, :email, :hashed_password, :role_id, NOW(), NOW())
            """),
            {"username": username, "email": email, "hashed_password": hashed_password, "role_id": role_id},
        )
        db.commit()
        return db.execute(
            text("SELECT id, username, email, role_id, created_at, updated_at FROM users WHERE email = :email"),
            {"email": email},
        ).mappings().first()

    @staticmethod
    def get_user_by_id(db: Session, user_id: int) -> Optional[Dict[str, Any]]:
        return db.execute(text("SELECT * FROM users WHERE id = :id"), {"id": user_id}).mappings().first()

    @staticmethod
    def get_user_by_email(db: Session, email: str) -> Optional[Dict[str, Any]]:
        return db.execute(text("SELECT * FROM users WHERE email = :email"), {"email": email}).mappings().first()

    @staticmethod
    def get_user_by_username(db: Session, username: str) -> Optional[Dict[str, Any]]:
        return db.execute(text("SELECT * FROM users WHERE username = :username"), {"username": username}).mappings().first()

    @staticmethod
    def list_users(db: Session, limit: int = 200, offset: int = 0) -> List[Dict[str, Any]]:
        return db.execute(
            text("""
                SELECT u.*, r.role_name
                FROM users u
                LEFT JOIN roles r ON r.role_id = u.role_id
                ORDER BY u.id DESC
                LIMIT :limit OFFSET :offset
            """),
            {"limit": limit, "offset": offset},
        ).mappings().all()

    @staticmethod
    def update_user(
        db: Session,
        user_id: int,
        username: Optional[str] = None,
        email: Optional[str] = None,
        role_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        db.execute(
            text("""
                UPDATE users
                SET
                    username = COALESCE(:username, username),
                    email    = COALESCE(:email, email),
                    role_id  = COALESCE(:role_id, role_id),
                    updated_at = NOW()
                WHERE id = :id
            """),
            {"id": user_id, "username": username, "email": email, "role_id": role_id},
        )
        db.commit()
        return UserCRUD.get_user_by_id(db, user_id)

    @staticmethod
    def set_password(db: Session, user_id: int, new_password: str) -> None:
        hashed_password = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        db.execute(
            text("UPDATE users SET hashed_password = :hp, updated_at = NOW() WHERE id = :id"),
            {"hp": hashed_password, "id": user_id},
        )
        db.commit()

    @staticmethod
    def delete_user(db: Session, user_id: int) -> None:
        db.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
        db.commit()

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


class RoleCRUD:
    @staticmethod
    def create_role(db: Session, role_name: str) -> Dict[str, Any]:
        db.execute(text("INSERT INTO roles (role_name) VALUES (:role_name)"), {"role_name": role_name})
        db.commit()
        return db.execute(text("SELECT * FROM roles WHERE role_name = :role_name"), {"role_name": role_name}).mappings().first()

    @staticmethod
    def get_role_by_id(db: Session, role_id: int) -> Optional[Dict[str, Any]]:
        return db.execute(text("SELECT * FROM roles WHERE role_id = :id"), {"id": role_id}).mappings().first()

    @staticmethod
    def get_role_by_name(db: Session, role_name: str) -> Optional[Dict[str, Any]]:
        return db.execute(text("SELECT * FROM roles WHERE role_name = :name"), {"name": role_name}).mappings().first()

    @staticmethod
    def list_roles(db: Session) -> List[Dict[str, Any]]:
        return db.execute(text("SELECT * FROM roles ORDER BY role_id")).mappings().all()

    @staticmethod
    def update_role(db: Session, role_id: int, role_name: str) -> Optional[Dict[str, Any]]:
        db.execute(text("UPDATE roles SET role_name = :name WHERE role_id = :id"), {"id": role_id, "name": role_name})
        db.commit()
        return RoleCRUD.get_role_by_id(db, role_id)

    @staticmethod
    def delete_role(db: Session, role_id: int) -> None:
        db.execute(text("DELETE FROM roles WHERE role_id = :id"), {"id": role_id})
        db.commit()


class StationCRUD:
    @staticmethod
    def create_station(db: Session, **kwargs) -> Dict[str, Any]:
        columns = ", ".join(kwargs.keys())
        values = ", ".join([f":{k}" for k in kwargs.keys()])
        db.execute(text(f"INSERT INTO stations ({columns}) VALUES ({values})"), kwargs)
        db.commit()
        return db.execute(text("SELECT * FROM stations ORDER BY id DESC LIMIT 1")).mappings().first()

    @staticmethod
    def get_station_by_id(db: Session, station_id: int) -> Optional[Dict[str, Any]]:
        return db.execute(text("SELECT * FROM stations WHERE id = :id"), {"id": station_id}).mappings().first()

    @staticmethod
    def list_stations(
        db: Session,
        eco_status: Optional[bool] = None,
        admarea: Optional[str] = None,
        limit: int = 5000,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM stations WHERE 1=1"
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if eco_status is not None:
            query += " AND eco_status = :eco_status"
            params["eco_status"] = eco_status
        if admarea:
            query += " AND admarea = :admarea"
            params["admarea"] = admarea
        query += " ORDER BY id ASC LIMIT :limit OFFSET :offset"
        return db.execute(text(query), params).mappings().all()

    @staticmethod
    def search_stations(db: Session, query: str, limit: int = 200) -> List[Dict[str, Any]]:
        pattern = f"%{query}%"
        return db.execute(
            text("""
                SELECT * FROM stations
                WHERE name ILIKE :p OR address ILIKE :p OR owner ILIKE :p
                ORDER BY id ASC
                LIMIT :limit
            """),
            {"p": pattern, "limit": limit},
        ).mappings().all()

    @staticmethod
    def update_station(db: Session, station_id: int, **kwargs) -> Optional[Dict[str, Any]]:
        if not kwargs:
            return StationCRUD.get_station_by_id(db, station_id)
        set_clause = ", ".join([f"{k} = :{k}" for k in kwargs.keys()])
        params = dict(kwargs)
        params["id"] = station_id
        db.execute(text(f"UPDATE stations SET {set_clause} WHERE id = :id"), params)
        db.commit()
        return StationCRUD.get_station_by_id(db, station_id)

    @staticmethod
    def delete_station(db: Session, station_id: int) -> None:
        db.execute(text("DELETE FROM stations WHERE id = :id"), {"id": station_id})
        db.commit()

    @staticmethod
    def get_station_count(db: Session) -> int:
        return int(db.execute(text("SELECT COUNT(*) FROM stations")).scalar() or 0)

    @staticmethod
    def get_eco_station_count(db: Session) -> int:
        return int(db.execute(text("SELECT COUNT(*) FROM stations WHERE eco_status = TRUE")).scalar() or 0)

    @staticmethod
    def get_stations_by_district(db: Session) -> Dict[str, int]:
        rows = db.execute(
            text("""
                SELECT admarea, COUNT(id) AS count
                FROM stations
                WHERE admarea IS NOT NULL
                GROUP BY admarea
                ORDER BY count DESC
            """)
        ).fetchall()
        return {str(r[0]): int(r[1]) for r in rows}

    @staticmethod
    def get_eco_vs_non_eco(db: Session) -> Dict[str, int]:
        rows = db.execute(text("SELECT eco_status, COUNT(*) AS count FROM stations GROUP BY eco_status")).fetchall()
        eco = sum(int(r[1]) for r in rows if r[0] is True)
        non_eco = sum(int(r[1]) for r in rows if r[0] is False)
        return {"eco": eco, "non_eco": non_eco}


class ReviewCRUD:
    @staticmethod
    def create_review(
        db: Session,
        user_id: int,
        station_id: int,
        rating: int,
        comment: Optional[str] = None,
        image_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        db.execute(
            text("""
                INSERT INTO reviews (user_id, station_id, rating, comment, image_url, created_at)
                VALUES (:user_id, :station_id, :rating, :comment, :image_url, NOW())
            """),
            {"user_id": user_id, "station_id": station_id, "rating": rating, "comment": comment, "image_url": image_url},
        )
        db.commit()
        return db.execute(text("SELECT * FROM reviews ORDER BY id DESC LIMIT 1")).mappings().first()

    @staticmethod
    def get_review_by_id(db: Session, review_id: int) -> Optional[Dict[str, Any]]:
        return db.execute(text("SELECT * FROM reviews WHERE id = :id"), {"id": review_id}).mappings().first()

    @staticmethod
    def list_reviews(db: Session, limit: int = 500, offset: int = 0) -> List[Dict[str, Any]]:
        return db.execute(
            text("""
                SELECT r.*, u.username, s.name AS station_name
                FROM reviews r
                JOIN users u ON u.id = r.user_id
                JOIN stations s ON s.id = r.station_id
                ORDER BY r.created_at DESC
                LIMIT :limit OFFSET :offset
            """),
            {"limit": limit, "offset": offset},
        ).mappings().all()

    @staticmethod
    def get_reviews_by_station(db: Session, station_id: int) -> List[Dict[str, Any]]:
        return db.execute(
            text("""
                SELECT r.*, u.username
                FROM reviews r
                JOIN users u ON u.id = r.user_id
                WHERE r.station_id = :station_id
                ORDER BY r.created_at DESC
            """),
            {"station_id": station_id},
        ).mappings().all()

    @staticmethod
    def get_reviews_by_user(db: Session, user_id: int) -> List[Dict[str, Any]]:
        return db.execute(
            text("""
                SELECT r.*, s.name AS station_name
                FROM reviews r
                JOIN stations s ON s.id = r.station_id
                WHERE r.user_id = :user_id
                ORDER BY r.created_at DESC
            """),
            {"user_id": user_id},
        ).mappings().all()

    @staticmethod
    def update_review(
        db: Session,
        review_id: int,
        rating: Optional[int] = None,
        comment: Optional[str] = None,
        image_url: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        db.execute(
            text("""
                UPDATE reviews
                SET
                    rating = COALESCE(:rating, rating),
                    comment = COALESCE(:comment, comment),
                    image_url = COALESCE(:image_url, image_url)
                WHERE id = :id
            """),
            {"id": review_id, "rating": rating, "comment": comment, "image_url": image_url},
        )
        db.commit()
        return ReviewCRUD.get_review_by_id(db, review_id)

    @staticmethod
    def delete_review(db: Session, review_id: int) -> None:
        db.execute(text("DELETE FROM reviews WHERE id = :id"), {"id": review_id})
        db.commit()

    @staticmethod
    def get_average_rating(db: Session, station_id: int) -> float:
        val = db.execute(
            text("SELECT COALESCE(AVG(rating), 0) FROM reviews WHERE station_id = :id"),
            {"id": station_id},
        ).scalar()
        return round(float(val or 0.0), 1)

    @staticmethod
    def get_review_count_by_month(db: Session, months: int = 6) -> Dict[str, int]:
        cutoff_date = datetime.utcnow() - timedelta(days=months * 30)
        rows = db.execute(
            text("""
                SELECT EXTRACT(YEAR FROM created_at) AS year,
                       EXTRACT(MONTH FROM created_at) AS month,
                       COUNT(id) AS count
                FROM reviews
                WHERE created_at >= :cutoff
                GROUP BY year, month
                ORDER BY year, month
            """),
            {"cutoff": cutoff_date},
        ).fetchall()
        return {f"{int(r[0])}-{int(r[1]):02d}": int(r[2]) for r in rows}

    @staticmethod
    def get_average_rating_by_eco_status(db: Session) -> Dict[str, float]:
        overall = db.execute(text("SELECT COALESCE(AVG(rating), 0) FROM reviews")).scalar()
        eco = db.execute(text("""
            SELECT COALESCE(AVG(r.rating), 0)
            FROM reviews r
            JOIN stations s ON s.id = r.station_id
            WHERE s.eco_status = TRUE
        """)).scalar()
        non_eco = db.execute(text("""
            SELECT COALESCE(AVG(r.rating), 0)
            FROM reviews r
            JOIN stations s ON s.id = r.station_id
            WHERE s.eco_status = FALSE
        """)).scalar()
        return {
            "overall": round(float(overall or 0), 1),
            "eco": round(float(eco or 0), 1),
            "non_eco": round(float(non_eco or 0), 1),
        }


class FavoriteCRUD:
    @staticmethod
    def add_favorite(db: Session, user_id: int, station_id: int) -> None:
        db.execute(
            text("""
                INSERT INTO favorites (user_id, station_id, created_at)
                VALUES (:user_id, :station_id, NOW())
                ON CONFLICT (user_id, station_id) DO NOTHING
            """),
            {"user_id": user_id, "station_id": station_id},
        )
        db.commit()

    @staticmethod
    def remove_favorite(db: Session, user_id: int, station_id: int) -> None:
        db.execute(
            text("DELETE FROM favorites WHERE user_id = :user_id AND station_id = :station_id"),
            {"user_id": user_id, "station_id": station_id},
        )
        db.commit()

    @staticmethod
    def is_favorite(db: Session, user_id: int, station_id: int) -> bool:
        row = db.execute(
            text("""
                SELECT 1
                FROM favorites
                WHERE user_id = :user_id AND station_id = :station_id
                LIMIT 1
            """),
            {"user_id": user_id, "station_id": station_id},
        ).first()
        return row is not None

    @staticmethod
    def list_favorites_by_user(db: Session, user_id: int) -> List[Dict[str, Any]]:
        return db.execute(
            text("""
                SELECT s.*
                FROM favorites f
                JOIN stations s ON s.id = f.station_id
                WHERE f.user_id = :user_id
                ORDER BY f.created_at DESC
            """),
            {"user_id": user_id},
        ).mappings().all()

    @staticmethod
    def count_favorites_by_user(db: Session, user_id: int) -> int:
        val = db.execute(text("SELECT COUNT(*) FROM favorites WHERE user_id = :user_id"), {"user_id": user_id}).scalar()
        return int(val or 0)
