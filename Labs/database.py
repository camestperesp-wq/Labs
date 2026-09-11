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
            "correo_usuario",
            "observaciones",
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

        # No elimina reportes históricos: impide nuevas colisiones por código/día.
        for operacion in ("INSERT", "UPDATE"):
            excluir = "AND id != OLD.id" if operacion == "UPDATE" else ""
            c.execute(f"""CREATE TRIGGER IF NOT EXISTS multas_clave_{operacion.lower()}
                BEFORE {operacion} ON multas
                WHEN EXISTS (SELECT 1 FROM multas
                    WHERE trim(codigo_estudiante)=trim(NEW.codigo_estudiante)
                    AND substr(fecha_multa,1,10)=substr(NEW.fecha_multa,1,10) {excluir})
                BEGIN SELECT RAISE(ABORT, 'Ya existe una multa para ese código y fecha'); END""")

        c.execute("CREATE INDEX IF NOT EXISTS idx_reservas_fecha_lab_hora_activo ON reservas(fecha, laboratorio, hora, activo)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_reservas_codigo_fecha_activo ON reservas(codigo, fecha, activo)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_reservas_pendientes_fecha_activo_asiste ON reservas(fecha, activo, asiste, codigo, hora)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_reservas_banco_disponible ON reservas(fecha, laboratorio, hora, banco, activo)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_multas_codigo_pagado ON multas(codigo_estudiante, pagado)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_multas_pagado_codigo ON multas(pagado, codigo_estudiante)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_multas_fecha ON multas(fecha_multa)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_horario_dia_hora_lab ON horario_fijo(dia_semana, hora, laboratorio)")

        # Inventario y préstamos de equipos de pasillo. La cabecera conserva los
        # datos de salida/entrada y la tabla puente permite varios equipos por
        # una misma transacción.
        c.execute("""CREATE TABLE IF NOT EXISTS equipos_pasillo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            placa TEXT UNIQUE,
            nombre TEXT NOT NULL,
            numero_interno TEXT NOT NULL UNIQUE,
            activo INTEGER NOT NULL DEFAULT 1 CHECK(activo IN (0, 1)),
            creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        columnas_equipos = {fila[1]: fila for fila in c.execute("PRAGMA table_info(equipos_pasillo)")}
        if columnas_equipos.get("placa", (None, None, None, 0))[3]:
            # Migración de instalaciones que crearon placa como NOT NULL.
            # SQLite requiere reconstruir la tabla para retirar la restricción.
            conn.commit()
            conn.execute("PRAGMA foreign_keys = OFF")
            try:
                conn.execute("BEGIN")
                conn.execute("""CREATE TABLE equipos_pasillo_nueva (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    placa TEXT UNIQUE,
                    nombre TEXT NOT NULL,
                    numero_interno TEXT NOT NULL UNIQUE,
                    activo INTEGER NOT NULL DEFAULT 1 CHECK(activo IN (0, 1)),
                    creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )""")
                conn.execute("""INSERT INTO equipos_pasillo_nueva
                    (id, placa, nombre, numero_interno, activo, creado_en)
                    SELECT id, NULLIF(trim(placa), ''), nombre, numero_interno, activo, creado_en
                    FROM equipos_pasillo""")
                conn.execute("DROP TABLE equipos_pasillo")
                conn.execute("ALTER TABLE equipos_pasillo_nueva RENAME TO equipos_pasillo")
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.execute("PRAGMA foreign_keys = ON")
        c.execute("""CREATE TABLE IF NOT EXISTS prestamos_pasillo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            solicitante TEXT NOT NULL,
            tecnico_entrega TEXT NOT NULL,
            fecha_salida TEXT NOT NULL,
            observaciones_salida TEXT,
            receptor TEXT,
            fecha_retorno TEXT,
            observaciones_entrada TEXT,
            estado TEXT NOT NULL DEFAULT 'PRESTADO'
                CHECK(estado IN ('PRESTADO', 'DEVUELTO'))
        )""")
        columnas_prestamos = {fila[1] for fila in c.execute("PRAGMA table_info(prestamos_pasillo)")}
        for columna, definicion in {
            "limite_fpga": "TEXT",
            "ultima_renovacion": "TEXT",
        }.items():
            if columna not in columnas_prestamos:
                c.execute(f"ALTER TABLE prestamos_pasillo ADD COLUMN {columna} {definicion}")
        c.execute("""CREATE TABLE IF NOT EXISTS prestamos_pasillo_equipos (
            prestamo_id INTEGER NOT NULL,
            equipo_id INTEGER NOT NULL,
            PRIMARY KEY (prestamo_id, equipo_id),
            FOREIGN KEY (prestamo_id) REFERENCES prestamos_pasillo(id) ON DELETE CASCADE,
            FOREIGN KEY (equipo_id) REFERENCES equipos_pasillo(id)
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS multas_prestamos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prestamo_id INTEGER NOT NULL,
            codigo_estudiante TEXT NOT NULL,
            tipo TEXT NOT NULL CHECK(tipo IN ('FPGA_RETRASO', 'DEVOLUCION_DIA_SIGUIENTE')),
            motivo TEXT NOT NULL,
            fecha_incidente TEXT NOT NULL,
            fecha_limite_referencia TEXT NOT NULL,
            retraso_minutos INTEGER NOT NULL DEFAULT 0,
            monto_pago REAL NOT NULL DEFAULT 0,
            tecnico_responsable TEXT,
            estado TEXT NOT NULL DEFAULT 'PENDIENTE' CHECK(estado IN ('PENDIENTE', 'PAGADA')),
            fecha_pago TEXT,
            UNIQUE(prestamo_id, tipo, fecha_limite_referencia),
            FOREIGN KEY (prestamo_id) REFERENCES prestamos_pasillo(id)
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_prestamos_pasillo_estado ON prestamos_pasillo(estado, fecha_salida)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_prestamos_pasillo_equipo ON prestamos_pasillo_equipos(equipo_id, prestamo_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_multas_prestamos_codigo_estado ON multas_prestamos(codigo_estudiante, estado)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_multas_prestamos_prestamo ON multas_prestamos(prestamo_id)")

        limpiar_bloques_impares_duplicados(conn)

        # Actualiza estadísticas para que SQLite elija el mejor índice.
        c.execute("ANALYZE")
        c.execute("PRAGMA optimize")

        conn.commit()

    limpiar_respaldos_antiguos()
