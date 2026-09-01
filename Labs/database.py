# database.py
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import sqlite3

import pandas as pd
import streamlit as st

DB_PATH = Path(__file__).resolve().with_name("mi_agenda.db")
_BACKGROUND_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="labs-db")


class _ClosingConnection(sqlite3.Connection):
    """Transacción contextual que además libera el archivo al salir."""

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def limpiar_bloques_impares_duplicados(conn):
    """Elimina un bloque impar solo si existe su bloque par equivalente."""
    cursor = conn.execute(
        """
        DELETE FROM horario_fijo AS impar
        WHERE CAST(substr(impar.hora, 1, 2) AS INTEGER) % 2 = 1
          AND EXISTS (
              SELECT 1
              FROM horario_fijo AS par
              WHERE par.dia_semana = impar.dia_semana
                AND lower(trim(par.laboratorio)) = lower(trim(impar.laboratorio))
                AND lower(trim(par.asignatura)) = lower(trim(impar.asignatura))
                AND CAST(substr(par.hora, 1, 2) AS INTEGER) % 2 = 0
                AND CAST(substr(par.hora, 1, 2) AS INTEGER) < CAST(substr(impar.hora, 7, 2) AS INTEGER)
                AND CAST(substr(impar.hora, 1, 2) AS INTEGER) < CAST(substr(par.hora, 7, 2) AS INTEGER)
          )
        """
    )
    reservas = conn.execute(
        """
        DELETE FROM reservas AS impar
        WHERE CAST(substr(impar.hora, 1, 2) AS INTEGER) % 2 = 1
          AND EXISTS (
              SELECT 1
              FROM reservas AS par
              WHERE par.fecha = impar.fecha
                AND lower(trim(par.laboratorio)) = lower(trim(impar.laboratorio))
                AND coalesce(par.codigo, '') = coalesce(impar.codigo, '')
                AND coalesce(par.proyecto, '') = coalesce(impar.proyecto, '')
                AND CAST(substr(par.hora, 1, 2) AS INTEGER) % 2 = 0
                AND CAST(substr(par.hora, 1, 2) AS INTEGER) < CAST(substr(impar.hora, 7, 2) AS INTEGER)
                AND CAST(substr(impar.hora, 1, 2) AS INTEGER) < CAST(substr(par.hora, 7, 2) AS INTEGER)
          )
        """
    )
    return cursor.rowcount + reservas.rowcount


def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10, factory=_ClosingConnection)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA temp_store = MEMORY")
    return conn


def ejecutar_en_segundo_plano(funcion, *args, **kwargs):
    """Ejecuta trabajo puro sin bloquear el render de Streamlit.

    La función no debe llamar APIs de Streamlit ni modificar session_state. Cada
    operación SQLite debe abrir su propia conexión mediante get_connection().
    """
    return _BACKGROUND_EXECUTOR.submit(funcion, *args, **kwargs)


def limpiar_respaldos_antiguos(dias=30, conservar=3):
    """Borra solo respaldos administrados antiguos y conserva los más recientes."""
    limite = datetime.now() - timedelta(days=dias)
    respaldos = sorted(
        DB_PATH.parent.glob("*_backup_*.db"),
        key=lambda ruta: ruta.stat().st_mtime,
        reverse=True,
    )
    eliminados = 0
    for ruta in respaldos[conservar:]:
        if datetime.fromtimestamp(ruta.stat().st_mtime) < limite:
            ruta.unlink(missing_ok=True)
            eliminados += 1
    return eliminados


def ejecutar(query, params=(), fetch=False):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute(query, params)
        if fetch:
            return c.fetchall()
        conn.commit()
        fetch_df_cached.clear()


@st.cache_data(ttl=300)
def fetch_df_cached(query, params=()):
    with get_connection() as conn:
        return pd.read_sql_query(query, conn, params=params)


def fetch_df(query, params=()):
    return fetch_df_cached(query, params)


def clear_cache():
    fetch_df_cached.clear()


def init_db():
    with get_connection() as conn:
        c = conn.cursor()

        # WAL permite lectores simultáneos mientras otra operación escribe.
        c.execute("PRAGMA journal_mode = WAL")

        c.execute("""CREATE TABLE IF NOT EXISTS reservas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            hora TEXT,
            laboratorio TEXT,
            banco INTEGER,
            codigo TEXT,
            nombres TEXT,
            proyecto TEXT,
            asiste TEXT,
            observaciones TEXT,
            multas TEXT,
            tecnico TEXT,
            activo INTEGER DEFAULT 1
        )""")

        c.execute("PRAGMA table_info(reservas)")
        columnas_reservas = [col[1] for col in c.fetchall()]
        if "activo" not in columnas_reservas:
            c.execute("ALTER TABLE reservas ADD COLUMN activo INTEGER DEFAULT 1")
        if "proyecto" not in columnas_reservas:
            c.execute("ALTER TABLE reservas ADD COLUMN proyecto TEXT")

        c.execute("""CREATE TABLE IF NOT EXISTS estudiantes (
            codigo TEXT PRIMARY KEY,
            nombres TEXT,
            proyecto TEXT,
            multas TEXT
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS horario_fijo (
            dia_semana TEXT,
            hora TEXT,
            laboratorio TEXT,
            asignatura TEXT,
            carrera TEXT,
            monitor TEXT,
            profesor TEXT,
            PRIMARY KEY (dia_semana, hora, laboratorio)
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS multas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo_estudiante TEXT,
            fecha_multa TEXT,
            fecha_pago TEXT,
            motivo TEXT,
            sancion TEXT,
            tecnico_asigna TEXT,
            tecnico_recibe TEXT,
            pagado TEXT CHECK(pagado IN ('SI', 'NO'))
        )""")

        c.execute("PRAGMA table_info(multas)")
        columnas_multas = [col[1] for col in c.fetchall()]
        columnas_requeridas = [
            "codigo_estudiante",
            "fecha_multa",
            "fecha_pago",
            "motivo",
            "sancion",
            "tecnico_asigna",
            "tecnico_recibe",
            "pagado",
        ]
        for columna in columnas_requeridas:
            if columna not in columnas_multas:
                c.execute(f"ALTER TABLE multas ADD COLUMN {columna} TEXT")

        c.execute("CREATE INDEX IF NOT EXISTS idx_reservas_fecha_lab_hora_activo ON reservas(fecha, laboratorio, hora, activo)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_reservas_codigo_fecha_activo ON reservas(codigo, fecha, activo)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_reservas_pendientes_fecha_activo_asiste ON reservas(fecha, activo, asiste, codigo, hora)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_reservas_banco_disponible ON reservas(fecha, laboratorio, hora, banco, activo)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_multas_codigo_pagado ON multas(codigo_estudiante, pagado)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_multas_pagado_codigo ON multas(pagado, codigo_estudiante)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_multas_fecha ON multas(fecha_multa)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_horario_dia_hora_lab ON horario_fijo(dia_semana, hora, laboratorio)")

        limpiar_bloques_impares_duplicados(conn)

        # Actualiza estadísticas para que SQLite elija el mejor índice.
        c.execute("ANALYZE")
        c.execute("PRAGMA optimize")

        conn.commit()

    limpiar_respaldos_antiguos()
