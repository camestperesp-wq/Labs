# database.py

import sqlite3
import pandas as pd

DB_PATH = 'mi_agenda.db'

def get_connection():
    return sqlite3.connect(DB_PATH)

def ejecutar(query, params=(), fetch=False):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute(query, params)
        if fetch:
            return c.fetchall()
        conn.commit()

def fetch_df(query, params=()):
    with get_connection() as conn:
        return pd.read_sql_query(query, conn, params=params)

def init_db():
    with get_connection() as conn:
        c = conn.cursor()
        
        # Tabla reservas
        c.execute('''CREATE TABLE IF NOT EXISTS reservas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            fecha TEXT, hora TEXT, laboratorio TEXT,
            banco INTEGER, codigo TEXT, nombres TEXT, proyecto TEXT, asiste TEXT,
            observaciones TEXT, multas TEXT, tecnico TEXT, 
            activo INTEGER DEFAULT 1
        )''')
        c.execute("PRAGMA table_info(reservas)")
        cols = [col[1] for col in c.fetchall()]
        if 'activo' not in cols:
            c.execute("ALTER TABLE reservas ADD COLUMN activo INTEGER DEFAULT 1")
        if 'proyecto' not in cols:
            c.execute("ALTER TABLE reservas ADD COLUMN proyecto TEXT")
        
        # Tabla estudiantes
        c.execute('''CREATE TABLE IF NOT EXISTS estudiantes (
            codigo TEXT PRIMARY KEY, nombres TEXT, proyecto TEXT, multas TEXT
        )''')
        
        # Tabla horario_fijo
        c.execute('''CREATE TABLE IF NOT EXISTS horario_fijo (
            dia_semana TEXT,
            hora TEXT,
            laboratorio TEXT,
            asignatura TEXT,
            carrera TEXT,
            monitor TEXT,
            profesor TEXT,
            PRIMARY KEY (dia_semana, hora, laboratorio)
        )''')
        
        # ===== NUEVA TABLA: multas =====
        c.execute('''
            CREATE TABLE IF NOT EXISTS multas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo_estudiante TEXT,
                fecha_multa TEXT,
                fecha_pago TEXT,
                motivo TEXT,
                sancion TEXT,
                tecnico_asigna TEXT,
                tecnico_recibe TEXT,
                pagado TEXT CHECK(pagado IN ('SI', 'NO'))
            )
        ''')
        
        # Verificar columnas de la tabla multas
        c.execute("PRAGMA table_info(multas)")
        columnas_multas = [col[1] for col in c.fetchall()]
        columnas_requeridas = ['codigo_estudiante', 'fecha_multa', 'fecha_pago', 'motivo', 
                              'sancion', 'tecnico_asigna', 'tecnico_recibe', 'pagado']
        for col in columnas_requeridas:
            if col not in columnas_multas:
                c.execute(f"ALTER TABLE multas ADD COLUMN {col} TEXT")
        
        conn.commit()