import sys
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, List

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np
import shutil

from fastapi import FastAPI, Request, Depends, HTTPException, Form, UploadFile, File, Body
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sqlalchemy.orm import Session
from sqlalchemy import text
from passlib.hash import bcrypt

from database.connector import DatabaseConnector
from backend.auth import get_db, get_current_user, get_current_user_required, create_access_token
from backend.config import settings
from backend.dependencies import require_admin


app = FastAPI(title=settings.app_name)
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
templates = Jinja2Templates(directory="frontend/templates")


@app.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[dict] = Depends(get_current_user),
):
    total = db.execute(text("SELECT COUNT(*) FROM stations")).scalar() or 0
    eco = db.execute(text("SELECT COUNT(*) FROM stations WHERE eco_status = true")).scalar() or 0
    eco_percentage = round((eco / total * 100) if total > 0 else 0)

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "user": current_user,
            "total_stations": total,
            "eco_stations": eco,
            "eco_percentage": eco_percentage,
            "last_update": datetime.now().strftime("%d.%m.%Y"),
        },
    )


@app.get("/map", response_class=HTMLResponse)
async def map_page(request: Request, current_user: Optional[dict] = Depends(get_current_user)):
    return templates.TemplateResponse("map.html", {"request": request, "user": current_user})


@app.get("/stats", response_class=HTMLResponse)
async def stats_page(request: Request, current_user: Optional[dict] = Depends(get_current_user)):
    return templates.TemplateResponse("stats.html", {"request": request, "user": current_user})


@app.get("/about", response_class=HTMLResponse)
async def about_page(request: Request, current_user: Optional[dict] = Depends(get_current_user)):
    return templates.TemplateResponse("about.html", {"request": request, "user": current_user})


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, current_user: Optional[dict] = Depends(get_current_user)):
    if current_user:
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "user": None})


@app.post("/login")
async def login(email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.execute(
        text("""
            SELECT
                u.id,
                u.hashed_password,
                r.role_name
            FROM users u
            JOIN roles r ON r.role_id = u.role_id
            WHERE u.email = :email
        """),
        {"email": email},
    ).mappings().first()

    if not user or not bcrypt.verify(password[:72], user["hashed_password"]):
        raise HTTPException(status_code=400, detail="Неверный email или пароль")

    access_token = create_access_token({"sub": str(user["id"]), "role": user["role_name"]})
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(key="access_token", value=access_token, httponly=True)
    return response


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, current_user: Optional[dict] = Depends(get_current_user)):
    if current_user:
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse("register.html", {"request": request, "user": None})


@app.post("/register")
async def register(
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    username = (username or "").strip()
    email = (email or "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="username не может быть пустым")
    if not email:
        raise HTTPException(status_code=400, detail="email не может быть пустым")

    exists = db.execute(
        text("SELECT 1 FROM users WHERE email = :email OR username = :username"),
        {"email": email, "username": username},
    ).fetchone()
    if exists:
        raise HTTPException(status_code=400, detail="Email или имя пользователя уже существует")

    user_role_id = db.execute(text("SELECT role_id FROM roles WHERE role_name = 'USER'")).scalar()
    if not user_role_id:
        raise HTTPException(status_code=500, detail="В БД отсутствует роль USER")

    hashed = bcrypt.hash(password)
    db.execute(
        text("""
            INSERT INTO users (username, email, hashed_password, role_id, created_at)
            VALUES (:u, :e, :p, :rid, NOW())
        """),
        {"u": username, "e": email, "p": hashed, "rid": int(user_role_id)},
    )
    db.commit()

    row = db.execute(
        text("""
            SELECT u.id, r.role_name
            FROM users u
            JOIN roles r ON r.role_id = u.role_id
            WHERE u.email = :email
        """),
        {"email": email},
    ).mappings().first()

    access_token = create_access_token({"sub": str(row["id"]), "role": row["role_name"]})
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(key="access_token", value=access_token, httponly=True)
    return response


@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie(key="access_token")
    return response


@app.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_required),
):
    reviews = db.execute(text("""
        SELECT
            r.id AS id,
            r.rating AS rating,
            r.comment AS comment,
            r.created_at AS created_at,
            s.name AS station_name,
            s.id AS station_id
        FROM reviews r
        JOIN stations s ON r.station_id = s.id
        WHERE r.user_id = :uid
        ORDER BY r.created_at DESC
    """), {"uid": current_user["id"]}).mappings().all()

    favorites = db.execute(text("""
        SELECT
            s.id, s.name, s.address, s.district, s.admarea, s.owner, s.test_date, s.eco_status, s.latitude, s.longitude
        FROM favorites f
        JOIN stations s ON s.id = f.station_id
        WHERE f.user_id = :uid
        ORDER BY f.created_at DESC
    """), {"uid": current_user["id"]}).mappings().all()

    msg = request.query_params.get("msg")

    return templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "user": current_user,
            "reviews": reviews,
            "favorites": favorites,
            "is_admin": current_user.get("role") == "ADMIN",
            "msg": msg,
        },
    )


@app.get("/profile/edit", response_class=HTMLResponse)
async def edit_profile_page(request: Request, current_user=Depends(get_current_user_required)):
    return templates.TemplateResponse("edit_profile.html", {"request": request, "user": current_user})


@app.post("/profile/edit")
async def update_profile(
    username: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    password: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_required),
):
    if username is not None:
        v = (username or "").strip()
        if not v:
            raise HTTPException(status_code=400, detail="username не может быть пустым")
        db.execute(text("UPDATE users SET username = :u WHERE id = :id"), {"u": v, "id": current_user["id"]})

    if email is not None:
        v = (email or "").strip()
        if not v:
            raise HTTPException(status_code=400, detail="email не может быть пустым")
        db.execute(text("UPDATE users SET email = :e WHERE id = :id"), {"e": v, "id": current_user["id"]})

    if password:
        hashed = bcrypt.hash(password)
        db.execute(
            text("UPDATE users SET hashed_password = :p WHERE id = :id"),
            {"p": hashed, "id": current_user["id"]},
        )

    db.commit()
    return RedirectResponse(url="/profile?msg=profile_saved", status_code=302)


@app.post("/station/{station_id}/favorite")
async def add_favorite(
    station_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_required),
):
    db.execute(text("""
        INSERT INTO favorites (user_id, station_id)
        VALUES (:u, :s)
        ON CONFLICT (user_id, station_id) DO NOTHING
    """), {"u": current_user["id"], "s": station_id})
    db.commit()
    return RedirectResponse(url=f"/station/{station_id}?msg=fav_added", status_code=302)


@app.post("/station/{station_id}/unfavorite")
async def remove_favorite(
    station_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_required),
):
    db.execute(
        text("DELETE FROM favorites WHERE user_id = :u AND station_id = :s"),
        {"u": current_user["id"], "s": station_id},
    )
    db.commit()
    return RedirectResponse(url=f"/station/{station_id}?msg=fav_removed", status_code=302)


@app.post("/station/{station_id}/review")
async def add_review(
    station_id: int,
    rating: int = Form(...),
    comment: str = Form(""),
    images: List[UploadFile] = File(default_factory=list),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_required),
):
    if rating < 1 or rating > 5:
        raise HTTPException(status_code=400, detail="Оценка должна быть от 1 до 5")

    review_id = db.execute(
        text("""
            INSERT INTO reviews (user_id, station_id, rating, comment, created_at)
            VALUES (:u, :s, :r, :c, NOW())
            RETURNING id
        """),
        {"u": current_user["id"], "s": station_id, "r": rating, "c": comment},
    ).scalar()

    upload_dir = Path("uploads")
    upload_dir.mkdir(exist_ok=True)

    for img in images:
        if not img or not img.filename:
            continue

        ext = img.filename.rsplit(".", 1)[-1].lower()
        filename = f"rev_{int(review_id)}_{int(datetime.now().timestamp())}_{os.urandom(4).hex()}.{ext}"
        file_path = upload_dir / filename

        with file_path.open("wb") as buffer:
            shutil.copyfileobj(img.file, buffer)

        url_value = f"/uploads/{filename}"
        if not url_value.strip():
            raise HTTPException(status_code=400, detail="url фото не может быть пустым")

        db.execute(
            text("INSERT INTO review_photos (review_id, url, created_at) VALUES (:rid, :url, NOW())"),
            {"rid": int(review_id), "url": url_value},
        )

    db.commit()
    return RedirectResponse(url=f"/station/{station_id}?msg=review_added", status_code=302)


@app.get("/api/stations")
async def api_get_stations(db: Session = Depends(get_db)):
    stations = db.execute(text("""
        SELECT id, name, address, district, admarea, owner, test_date, eco_status, latitude, longitude
        FROM stations
    """)).fetchall()

    result = []
    for s in stations:
        avg = db.execute(
            text("SELECT COALESCE(AVG(rating),0) FROM reviews WHERE station_id = :id"),
            {"id": s.id},
        ).scalar()

        result.append({
            "id": s.id,
            "name": s.name,
            "address": s.address,
            "district": s.district,
            "admarea": s.admarea,
            "owner": s.owner,
            "test_date": s.test_date.isoformat() if s.test_date else None,
            "eco_status": s.eco_status,
            "latitude": s.latitude,
            "longitude": s.longitude,
            "average_rating": round(float(avg or 0), 1),
        })
    return result


@app.get("/station/{station_id}", response_class=HTMLResponse)
async def station_page(
    request: Request,
    station_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[dict] = Depends(get_current_user),
):
    station = db.execute(text("""
        SELECT id, name, address, district, admarea, owner, test_date, eco_status, latitude, longitude
        FROM stations
        WHERE id = :id
    """), {"id": station_id}).mappings().first()

    if not station:
        raise HTTPException(status_code=404, detail="Станция не найдена")

    reviews = db.execute(text("""
        SELECT
            r.id,
            r.rating,
            r.comment,
            r.created_at,
            u.username
        FROM reviews r
        JOIN users u ON r.user_id = u.id
        WHERE r.station_id = :id
        ORDER BY r.created_at DESC
    """), {"id": station_id}).mappings().all()

    avg_rating = db.execute(
        text("SELECT ROUND(AVG(rating), 1) FROM reviews WHERE station_id = :id"),
        {"id": station_id},
    ).scalar() or 0

    review_ids = [r["id"] for r in reviews]
    photos_map: dict[int, list[str]] = {}

    if review_ids:
        photos = db.execute(
            text("""
                SELECT review_id, url
                FROM review_photos
                WHERE review_id = ANY(:ids)
                ORDER BY created_at ASC
            """),
            {"ids": review_ids},
        ).mappings().all()

        for p in photos:
            photos_map.setdefault(p["review_id"], []).append(p["url"])

    reviews = [dict(r, photos=photos_map.get(r["id"], [])) for r in reviews]

    is_favorite = False
    if current_user:
        fav = db.execute(
            text("SELECT 1 FROM favorites WHERE user_id = :u AND station_id = :s"),
            {"u": current_user["id"], "s": station_id},
        ).fetchone()
        is_favorite = bool(fav)

    msg = request.query_params.get("msg")

    return templates.TemplateResponse(
        "station.html",
        {
            "request": request,
            "user": current_user,
            "station": station,
            "reviews": reviews,
            "avg_rating": avg_rating,
            "is_favorite": is_favorite,
            "msg": msg,
        },
    )


def simple_kmeans(points, k=3, max_iters=100):
    if len(points) < k:
        return np.zeros(len(points), dtype=int)

    np.random.seed(42)
    centroids = points[np.random.choice(len(points), k, replace=False)]

    for _ in range(max_iters):
        distances = np.sqrt(((points[:, np.newaxis] - centroids) ** 2).sum(axis=2))
        labels = np.argmin(distances, axis=1)

        new_centroids = np.array([
            points[labels == i].mean(axis=0) if np.any(labels == i) else centroids[i]
            for i in range(k)
        ])

        if np.allclose(centroids, new_centroids):
            break
        centroids = new_centroids

    return labels


@app.get("/api/stats")
async def api_get_stats(db: Session = Depends(get_db)):
    by_district_rows = db.execute(text("""
        SELECT admarea, COUNT(*)
        FROM stations
        WHERE admarea IS NOT NULL
        GROUP BY admarea
        ORDER BY COUNT(*) DESC
    """)).fetchall()

    by_district = {r[0]: int(r[1]) for r in by_district_rows}

    stations_rows = db.execute(text("""
        SELECT latitude, longitude, eco_status::int
        FROM stations
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL
    """)).fetchall()

    points = [{"lat": float(r[0]), "lon": float(r[1]), "eco": int(r[2])} for r in stations_rows]
    clusters_scatter = {"k": 3, "points": []}

    if len(points) >= 3:
        coords = np.array([[p["lat"], p["lon"]] for p in points], dtype=float)
        labels = simple_kmeans(coords, k=3)
        clusters_scatter["points"] = [
            {"lat": points[i]["lat"], "lon": points[i]["lon"], "eco": points[i]["eco"], "cluster": int(labels[i])}
            for i in range(len(points))
        ]
    else:
        clusters_scatter["points"] = [{"lat": p["lat"], "lon": p["lon"], "eco": p["eco"], "cluster": 0} for p in points]
        clusters_scatter["k"] = 1

    return {"by_district": by_district, "clusters_scatter": clusters_scatter}


@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    users = db.execute(text("""
        SELECT u.*, r.role_name
        FROM users u
        JOIN roles r ON r.role_id = u.role_id
        ORDER BY u.created_at DESC
    """)).mappings().all()

    roles = db.execute(text("SELECT * FROM roles ORDER BY role_id ASC")).mappings().all()

    stations = db.execute(text("SELECT * FROM stations ORDER BY id ASC")).mappings().all()

    reviews = db.execute(text("""
        SELECT
            r.id,
            r.rating,
            r.comment,
            r.created_at,
            u.username as user_username,
            u.id as user_id,
            s.name as station_name,
            s.id as station_id
        FROM reviews r
        LEFT JOIN users u ON r.user_id = u.id
        LEFT JOIN stations s ON r.station_id = s.id
        ORDER BY r.created_at DESC
    """)).mappings().all()

    review_photos = db.execute(text("""
        SELECT
            p.id,
            p.review_id,
            p.url,
            p.created_at
        FROM review_photos p
        ORDER BY p.created_at DESC
    """)).mappings().all()

    favorites = db.execute(text("""
        SELECT
            f.user_id,
            f.station_id,
            f.created_at,
            u.username,
            s.name as station_name
        FROM favorites f
        JOIN users u ON u.id = f.user_id
        JOIN stations s ON s.id = f.station_id
        ORDER BY f.created_at DESC
    """)).mappings().all()

    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "user": current_user,
            "users": users,
            "roles": roles,
            "stations": stations,
            "reviews": reviews,
            "review_photos": review_photos,
            "favorites": favorites,
        },
    )


@app.on_event("startup")
async def startup_event():
    db_connector = DatabaseConnector()
    try:
        db_connector.create_tables()
    except Exception as e:
        print(f"create_tables пропущен: {e}")

    db = next(get_db())

    try:
        admin_exists = db.execute(text("SELECT 1 FROM users WHERE email = 'admin@example.com'")).fetchone()
        if not admin_exists:
            admin_role_id = db.execute(text("SELECT role_id FROM roles WHERE role_name = 'ADMIN'")).scalar()
            if not admin_role_id:
                raise RuntimeError("Роль ADMIN не найдена в таблице roles")

            hashed_password = bcrypt.hash("admin123")
            db.execute(text("""
                INSERT INTO users (username, email, hashed_password, role_id, created_at)
                VALUES (:u, :e, :p, :rid, NOW())
            """), {"u": "superadmin", "e": "admin@example.com", "p": hashed_password, "rid": int(admin_role_id)})
            db.commit()
    except Exception as e:
        print(f"Ошибка при создании администратора: {e}")

    try:
        from database.stored_procedures import create_stored_procedures
        create_stored_procedures()
    except Exception as e:
        print(f"Ошибка при создании хранимых процедур: {e}")

    try:
        from database.import_data import import_data
        import_data()
    except Exception as e:
        print(f"Ошибка при автообновлении данных: {e}")


def _to_float_or_none(v):
    if v is None:
        return None
    s = str(v).strip()
    if s == "":
        return None
    return float(s)


@app.put("/admin/users/{user_id}")
async def admin_update_user(
    user_id: int,
    data: dict = Body(...),
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    user = db.execute(text("SELECT * FROM users WHERE id = :id"), {"id": user_id}).mappings().first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    if "username" in data:
        v = str(data["username"]).strip()
        if not v:
            raise HTTPException(status_code=400, detail="username не может быть пустым")
        db.execute(text("UPDATE users SET username = :u WHERE id = :id"), {"u": v, "id": user_id})

    if "email" in data:
        v = str(data["email"]).strip()
        if not v:
            raise HTTPException(status_code=400, detail="email не может быть пустым")
        db.execute(text("UPDATE users SET email = :e WHERE id = :id"), {"e": v, "id": user_id})

    if "role" in data and str(data["role"]).strip():
        role_name = str(data["role"]).strip().upper()
        role_id = db.execute(text("SELECT role_id FROM roles WHERE role_name = :rn"), {"rn": role_name}).scalar()
        if not role_id:
            raise HTTPException(status_code=400, detail="Такой роли нет в таблице roles")
        db.execute(text("UPDATE users SET role_id = :rid WHERE id = :id"), {"rid": int(role_id), "id": user_id})

    if "password" in data and str(data["password"]).strip():
        hashed = bcrypt.hash(str(data["password"]))
        db.execute(text("UPDATE users SET hashed_password = :p WHERE id = :id"), {"p": hashed, "id": user_id})

    db.commit()
    return {"success": True}


@app.put("/admin/stations/{station_id}")
async def admin_update_station(
    station_id: int,
    data: dict = Body(...),
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    station = db.execute(text("SELECT * FROM stations WHERE id = :id"), {"id": station_id}).mappings().first()
    if not station:
        raise HTTPException(status_code=404, detail="Станция не найдена")

    allowed_fields = {"name", "address", "district", "admarea", "owner", "eco_status", "latitude", "longitude", "test_date"}

    if "eco_status" in data:
        v = str(data["eco_status"]).strip().lower()
        data["eco_status"] = v in ("1", "true", "yes", "y")

    if "latitude" in data:
        lat = _to_float_or_none(data["latitude"])
        if lat is not None and not (-90 <= lat <= 90):
            raise HTTPException(status_code=400, detail="latitude должна быть в диапазоне -90..90")
        data["latitude"] = lat

    if "longitude" in data:
        lon = _to_float_or_none(data["longitude"])
        if lon is not None and not (-180 <= lon <= 180):
            raise HTTPException(status_code=400, detail="longitude должна быть в диапазоне -180..180")
        data["longitude"] = lon

    for field, value in data.items():
        if field in allowed_fields:
            db.execute(text(f"UPDATE stations SET {field} = :v WHERE id = :id"), {"v": value, "id": station_id})

    db.commit()
    return {"success": True}


@app.put("/admin/reviews/{review_id}")
async def admin_update_review(
    review_id: int,
    data: dict = Body(...),
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    review = db.execute(text("SELECT * FROM reviews WHERE id = :id"), {"id": review_id}).mappings().first()
    if not review:
        raise HTTPException(status_code=404, detail="Отзыв не найден")

    if "rating" in data:
        r = int(data["rating"])
        if r < 1 or r > 5:
            raise HTTPException(status_code=400, detail="rating должен быть от 1 до 5")
        db.execute(text("UPDATE reviews SET rating = :r WHERE id = :id"), {"r": r, "id": review_id})

    if "comment" in data:
        db.execute(text("UPDATE reviews SET comment = :c WHERE id = :id"), {"c": data["comment"], "id": review_id})

    db.commit()
    return {"success": True}


@app.post("/admin/users")
async def admin_create_user(
    data: dict = Body(...),
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip()
    role_name = (data.get("role") or "USER").strip().upper()
    password = (data.get("password") or "").strip()

    if not username:
        raise HTTPException(status_code=400, detail="username не может быть пустым")
    if not email:
        raise HTTPException(status_code=400, detail="email не может быть пустым")
    if not password:
        raise HTTPException(status_code=400, detail="password обязателен")

    exists = db.execute(
        text("SELECT 1 FROM users WHERE email = :e OR username = :u"),
        {"e": email, "u": username},
    ).fetchone()
    if exists:
        raise HTTPException(status_code=400, detail="Email или имя пользователя уже существует")

    role_id = db.execute(text("SELECT role_id FROM roles WHERE role_name = :rn"), {"rn": role_name}).scalar()
    if not role_id:
        raise HTTPException(status_code=400, detail="Такой роли нет в таблице roles")

    hashed = bcrypt.hash(password)
    db.execute(text("""
        INSERT INTO users (username, email, hashed_password, role_id, created_at)
        VALUES (:u, :e, :p, :rid, NOW())
    """), {"u": username, "e": email, "p": hashed, "rid": int(role_id)})

    db.commit()
    return {"success": True}


@app.post("/admin/stations")
async def admin_create_station(
    data: dict = Body(...),
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name обязателен")

    eco_raw = str(data.get("eco_status", "0")).strip().lower()
    eco_status = eco_raw in ("1", "true", "yes", "y")

    lat = _to_float_or_none(data.get("latitude"))
    lon = _to_float_or_none(data.get("longitude"))
    if lat is not None and not (-90 <= lat <= 90):
        raise HTTPException(status_code=400, detail="latitude должна быть в диапазоне -90..90")
    if lon is not None and not (-180 <= lon <= 180):
        raise HTTPException(status_code=400, detail="longitude должна быть в диапазоне -180..180")

    db.execute(text("""
        INSERT INTO stations (name, address, district, admarea, owner, eco_status, latitude, longitude, test_date)
        VALUES (:name, :address, :district, :admarea, :owner, :eco_status, :lat, :lon, :test_date)
    """), {
        "name": name,
        "address": (data.get("address") or "").strip() or None,
        "district": (data.get("district") or "").strip() or None,
        "admarea": (data.get("admarea") or "").strip() or None,
        "owner": (data.get("owner") or "").strip() or None,
        "eco_status": eco_status,
        "lat": lat,
        "lon": lon,
        "test_date": (data.get("test_date") or "").strip() or None,
    })
    db.commit()
    return {"success": True}


@app.post("/admin/reviews")
async def admin_create_review(
    data: dict = Body(...),
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    try:
        user_id = int(data.get("user_id"))
        station_id = int(data.get("station_id"))
        rating = int(data.get("rating"))
    except Exception:
        raise HTTPException(status_code=400, detail="user_id, station_id и rating обязательны и должны быть числами")

    if rating < 1 or rating > 5:
        raise HTTPException(status_code=400, detail="rating должен быть от 1 до 5")

    comment = (data.get("comment") or "").strip()

    db.execute(text("""
        INSERT INTO reviews (user_id, station_id, rating, comment, created_at)
        VALUES (:u, :s, :r, :c, NOW())
    """), {"u": user_id, "s": station_id, "r": rating, "c": comment})

    db.commit()
    return {"success": True}


@app.delete("/admin/users/{user_id}")
async def admin_delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Нельзя удалить самого себя")

    db.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
    db.commit()
    return {"success": True}


@app.delete("/admin/stations/{station_id}")
async def admin_delete_station(
    station_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    db.execute(text("DELETE FROM stations WHERE id = :id"), {"id": station_id})
    db.commit()
    return {"success": True}


@app.delete("/admin/reviews/{review_id}")
async def admin_delete_review(
    review_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    db.execute(text("DELETE FROM reviews WHERE id = :id"), {"id": review_id})
    db.commit()
    return {"success": True}


@app.post("/admin/roles")
async def admin_create_role(
    data: dict = Body(...),
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    role_name = (data.get("role_name") or "").strip().upper()
    if not role_name:
        raise HTTPException(status_code=400, detail="role_name обязателен")

    exists = db.execute(text("SELECT 1 FROM roles WHERE role_name = :rn"), {"rn": role_name}).fetchone()
    if exists:
        raise HTTPException(status_code=400, detail="Такая роль уже существует")

    db.execute(text("INSERT INTO roles (role_name) VALUES (:rn)"), {"rn": role_name})
    db.commit()
    return {"success": True}


@app.delete("/admin/roles/{role_id}")
async def admin_delete_role(
    role_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    used = db.execute(text("SELECT 1 FROM users WHERE role_id = :rid"), {"rid": role_id}).fetchone()
    if used:
        raise HTTPException(status_code=400, detail="Нельзя удалить роль: она используется пользователями")

    db.execute(text("DELETE FROM roles WHERE role_id = :rid"), {"rid": role_id})
    db.commit()
    return {"success": True}


@app.delete("/admin/review-photos/{photo_id}")
async def admin_delete_review_photo(
    photo_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    db.execute(text("DELETE FROM review_photos WHERE id = :id"), {"id": photo_id})
    db.commit()
    return {"success": True}


@app.delete("/admin/favorites/{user_id}/{station_id}")
async def admin_delete_favorite(
    user_id: int,
    station_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    db.execute(
        text("DELETE FROM favorites WHERE user_id = :u AND station_id = :s"),
        {"u": user_id, "s": station_id},
    )
    db.commit()
    return {"success": True}