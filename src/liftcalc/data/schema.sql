-- liftcalc 数据库结构（设计 §6.1）
PRAGMA foreign_keys = ON;

CREATE TABLE meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE crane_model (
  id            INTEGER PRIMARY KEY,
  brand         TEXT NOT NULL,
  model         TEXT NOT NULL,
  tonnage_class REAL NOT NULL,
  crane_type    TEXT NOT NULL CHECK (crane_type IN ('crawler','all_terrain','truck','lattice')),
  counterweight_t REAL,
  hook_main_t   REAL,
  hook_aux_t    REAL,
  max_outrigger_reaction_kN REAL,
  self_weight_t REAL,
  outrigger_lx_m REAL,
  outrigger_ly_m REAL,
  notes         TEXT,
  source_doc    TEXT NOT NULL,
  source_page   TEXT,
  UNIQUE (brand, model)
);

CREATE TABLE crane_config (
  id            INTEGER PRIMARY KEY,
  model_id      INTEGER NOT NULL REFERENCES crane_model(id) ON DELETE CASCADE,
  name          TEXT NOT NULL,
  boom_len      REAL NOT NULL,
  counterweight REAL,
  UNIQUE (model_id, name, boom_len)
);

CREATE TABLE crane_capacity (
  id             INTEGER PRIMARY KEY,
  config_id      INTEGER NOT NULL REFERENCES crane_config(id) ON DELETE CASCADE,
  radius         REAL NOT NULL,
  rated_load     REAL NOT NULL,
  boom_angle_deg REAL,
  lift_height_m  REAL,
  parts_of_line  REAL,
  source_ref     TEXT NOT NULL,
  UNIQUE (config_id, radius)
);
CREATE INDEX idx_capacity ON crane_capacity(config_id, radius);

CREATE TABLE steel_section (
  id          INTEGER PRIMARY KEY,
  family      TEXT NOT NULL,
  designation TEXT NOT NULL,
  standard    TEXT NOT NULL,
  h  REAL, b REAL, tw REAL, tf REAL, r REAL,
  A  REAL, Ix REAL, Iy REAL, Wx REAL, Wy REAL, rx REAL, ry REAL,
  J  REAL,
  source_ref  TEXT NOT NULL,
  UNIQUE (family, designation)
);

CREATE TABLE material (
  id            INTEGER PRIMARY KEY,
  grade         TEXT NOT NULL,
  standard      TEXT NOT NULL,
  fy            REAL,
  fu            REAL,
  E             REAL DEFAULT 206000,
  G             REAL DEFAULT 79000,
  rho           REAL DEFAULT 7850,
  thickness_max REAL,
  source_ref    TEXT NOT NULL,
  UNIQUE (grade, standard, thickness_max)
);

CREATE TABLE code_clause (
  id       INTEGER PRIMARY KEY,
  standard TEXT NOT NULL,
  clause   TEXT NOT NULL,
  title    TEXT NOT NULL,
  text     TEXT,
  UNIQUE (standard, clause)
);
