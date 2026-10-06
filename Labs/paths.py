"""Rutas compartidas; LABS_DATA_DIR permite persistir SQLite fuera del código."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
# Conserva las bases existentes en instalaciones locales.
DATA_DIR = Path(os.environ.get("LABS_DATA_DIR", str(BASE_DIR))).expanduser().resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "mi_agenda.db"
AUTH_DB = DATA_DIR / "auth.db"
