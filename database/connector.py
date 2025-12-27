import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager

from backend.config import settings

load_dotenv()


class DatabaseConnector:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabaseConnector, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized") and self._initialized:
            return

        self.database_url = os.getenv("DATABASE_URL") or settings.database_url
        self.engine = create_engine(self.database_url)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self._initialized = True

    def get_session(self) -> Session:
        return self.SessionLocal()

    @contextmanager
    def session_scope(self):
        session = self.get_session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def create_tables(self):
        schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
        if not os.path.exists(schema_path):
            raise FileNotFoundError(f"schema.sql not found: {schema_path}")

        with open(schema_path, "r", encoding="utf-8") as f:
            sql = f.read()

        with self.engine.begin() as conn:
            conn.execute(text(sql))

    def drop_tables(self):
        drop_sql = """
        DROP TABLE IF EXISTS review_photos CASCADE;
        DROP TABLE IF EXISTS favorites CASCADE;
        DROP TABLE IF EXISTS reviews CASCADE;
        DROP TABLE IF EXISTS stations CASCADE;
        DROP TABLE IF EXISTS users CASCADE;
        """
        with self.engine.begin() as conn:
            conn.execute(text(drop_sql))
