# estudiantes.py

import pandas as pd
import database as db
from datetime import datetime, timedelta
def buscar_estudiante(codigo):
    r = db.ejecutar("SELECT codigo, nombres, proyecto FROM estudiantes WHERE codigo=?", (codigo,), fetch=True)
    return r[0] if r else None

def contar_reservas_hoy(codigo):
    hoy = datetime.now().date().strftime("%Y-%m-%d")
    r = db.ejecutar("""SELECT COUNT(*) FROM reservas 
                        WHERE codigo=? AND fecha=? AND activo=1""", 
                     (codigo, hoy), fetch=True)
    return r[0][0] if r else 0

def cargar_estudiantes(archivo):
    try:
        nombre = archivo.name.lower()
        df = pd.read_excel(archivo) if nombre.endswith(('.xlsx', '.xls')) else pd.read_csv(archivo, encoding='utf-8')
        df = df[['codigo', 'nombres', 'proyecto', 'multas']].dropna(subset=['codigo'])
        df['codigo'] = df['codigo'].astype(str).str.strip()
        df = df[(df['codigo'] != '')].drop_duplicates(subset=['codigo'])
        with db.get_connection() as conn:
            c = conn.cursor()
            c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_codigo ON estudiantes(codigo)")
            datos = df.to_records(index=False).tolist()
            c.executemany("""
                INSERT OR REPLACE INTO estudiantes (codigo, nombres, proyecto, multas)
                VALUES (?, ?, ?, ?)
            """, datos)
            conn.commit()
        return len(df)
    except Exception as e:
        raise e