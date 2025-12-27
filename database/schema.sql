BEGIN;

CREATE TABLE IF NOT EXISTS roles (
  role_id     SERIAL PRIMARY KEY,
  role_name   VARCHAR(50) NOT NULL UNIQUE
);

INSERT INTO roles(role_name)
VALUES ('ADMIN'), ('USER')
ON CONFLICT (role_name) DO NOTHING;

CREATE TABLE IF NOT EXISTS users (
  id              SERIAL PRIMARY KEY,
  username        VARCHAR(100) NOT NULL UNIQUE,
  email           VARCHAR(255) NOT NULL UNIQUE,
  hashed_password VARCHAR(255) NOT NULL,
  role_id         INT NOT NULL DEFAULT 2,
  created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMP NOT NULL DEFAULT NOW(),

  CONSTRAINT fk_users_role
    FOREIGN KEY (role_id) REFERENCES roles(role_id)
    ON UPDATE CASCADE
    ON DELETE RESTRICT,

  CONSTRAINT chk_users_username_not_blank
    CHECK (btrim(username) <> ''),

  CONSTRAINT chk_users_email_not_blank
    CHECK (btrim(email) <> '')
);

CREATE TABLE IF NOT EXISTS stations (
  id          SERIAL PRIMARY KEY,
  global_id   VARCHAR(100) UNIQUE,
  name        VARCHAR(255) NOT NULL,
  address     VARCHAR(500) NOT NULL,
  district    VARCHAR(255),
  admarea     VARCHAR(255),
  owner       VARCHAR(255),
  test_date   TIMESTAMP NULL,
  eco_status  BOOLEAN NOT NULL DEFAULT FALSE,
  latitude    DOUBLE PRECISION NULL,
  longitude   DOUBLE PRECISION NULL,
  created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMP NOT NULL DEFAULT NOW(),

  CONSTRAINT chk_stations_latitude_range
    CHECK (latitude IS NULL OR (latitude BETWEEN -90 AND 90)),

  CONSTRAINT chk_stations_longitude_range
    CHECK (longitude IS NULL OR (longitude BETWEEN -180 AND 180))
);

CREATE INDEX IF NOT EXISTS idx_stations_admarea ON stations(admarea);
CREATE INDEX IF NOT EXISTS idx_stations_eco_status ON stations(eco_status);
CREATE INDEX IF NOT EXISTS idx_stations_coords ON stations(latitude, longitude);

CREATE TABLE IF NOT EXISTS reviews (
  id         SERIAL PRIMARY KEY,
  station_id INT NOT NULL,
  user_id    INT NOT NULL,
  rating     INT NOT NULL,
  comment    TEXT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),

  CONSTRAINT chk_reviews_rating_1_5
    CHECK (rating BETWEEN 1 AND 5),

  CONSTRAINT fk_reviews_station
    FOREIGN KEY (station_id) REFERENCES stations(id)
    ON UPDATE CASCADE
    ON DELETE CASCADE,

  CONSTRAINT fk_reviews_user
    FOREIGN KEY (user_id) REFERENCES users(id)
    ON UPDATE CASCADE
    ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_reviews_station ON reviews(station_id);
CREATE INDEX IF NOT EXISTS idx_reviews_user ON reviews(user_id);

CREATE TABLE IF NOT EXISTS review_photos (
  id         SERIAL PRIMARY KEY,
  review_id  INT NOT NULL,
  url        VARCHAR(500) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),

  CONSTRAINT fk_review_photos_review
    FOREIGN KEY (review_id) REFERENCES reviews(id)
    ON UPDATE CASCADE
    ON DELETE CASCADE,

  CONSTRAINT chk_review_photos_url_not_blank
    CHECK (btrim(url) <> '')
);

CREATE INDEX IF NOT EXISTS idx_review_photos_review ON review_photos(review_id);

CREATE TABLE IF NOT EXISTS favorites (
  user_id    INT NOT NULL,
  station_id INT NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  PRIMARY KEY (user_id, station_id),

  CONSTRAINT fk_favorites_user
    FOREIGN KEY (user_id) REFERENCES users(id)
    ON UPDATE CASCADE
    ON DELETE CASCADE,

  CONSTRAINT fk_favorites_station
    FOREIGN KEY (station_id) REFERENCES stations(id)
    ON UPDATE CASCADE
    ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_favorites_station ON favorites(station_id);

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'set_updated_at') THEN
    CREATE OR REPLACE FUNCTION set_updated_at()
    RETURNS TRIGGER AS $fn$
    BEGIN
      NEW.updated_at = NOW();
      RETURN NEW;
    END;
    $fn$ LANGUAGE plpgsql;
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_users_updated_at') THEN
    CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_stations_updated_at') THEN
    CREATE TRIGGER trg_stations_updated_at
    BEFORE UPDATE ON stations
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();
  END IF;
END $$;

COMMIT;
