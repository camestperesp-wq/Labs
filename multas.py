# multas.py

import database as db
from datetime import datetime
import pandas as pd

# ============================================================
#  FUNCIONES PARA LA GESTIÓN DE MULTAS
# ============================================================

def obtener_deudores():
    """
    Retorna un DataFrame con estudiantes que tienen multas activas (pagado = 'NO').
    Útil para la tabla principal de la pestaña "Deudores".
    """
    query = """
        SELECT 
            m.codigo_estudiante,
            e.nombres,
            e.proyecto as carrera,
            COUNT(m.id) as numero_multas,
            GROUP_CONCAT(m.motivo, ' | ') as motivos
        FROM multas m
        LEFT JOIN estudiantes e ON m.codigo_estudiante = e.codigo
        WHERE m.pagado = 'NO'
        GROUP BY m.codigo_estudiante
        ORDER BY e.nombres
    """
    return db.fetch_df(query)


def obtener_multas_estudiante(codigo):
    """
    Retorna un DataFrame con todas las multas de un estudiante (activas e históricas).
    """
    query = """
        SELECT id, fecha_multa, fecha_pago, motivo, sancion, 
               tecnico_asigna, tecnico_recibe, pagado
        FROM multas
        WHERE codigo_estudiante = ?
        ORDER BY fecha_multa DESC
    """
    return db.fetch_df(query, (codigo,))


def obtener_multas_activas_estudiante(codigo):
    """
    Retorna un DataFrame con las multas activas (pagado = 'NO') de un estudiante.
    """
    query = """
        SELECT id, fecha_multa, motivo, sancion, tecnico_asigna
        FROM multas
        WHERE codigo_estudiante = ? AND pagado = 'NO'
        ORDER BY fecha_multa DESC
    """
    return db.fetch_df(query, (codigo,))


def obtener_texto_multas_activas(codigo):
    """
    Retorna un string formateado con las multas activas de un estudiante.
    Útil para mostrar en mensajes de advertencia (ej. en reservas).
    """
    rows = db.ejecutar("""
        SELECT motivo, fecha_multa, sancion 
        FROM multas 
        WHERE codigo_estudiante = ? AND pagado = 'NO'
    """, (codigo,), fetch=True)
    if rows:
        return "\n".join([f"• {row[0]} ({row[1]}) - Sanción: {row[2]}" for row in rows])
    return ""


def buscar_estudiantes(termino):
    """
    Busca estudiantes en la tabla 'estudiantes' por código o nombre.
    Retorna un DataFrame con código, nombres, proyecto y número de multas activas.
    Útil para encontrar estudiantes sin multas activas y asignarles una.
    """
    query = """
        SELECT 
            codigo,
            nombres,
            proyecto as carrera,
            (SELECT COUNT(*) FROM multas WHERE codigo_estudiante = estudiantes.codigo AND pagado = 'NO') as multas_activas
        FROM estudiantes
        WHERE codigo LIKE ? OR nombres LIKE ?
        ORDER BY nombres
    """
    return db.fetch_df(query, (f'%{termino}%', f'%{termino}%'))


def agregar_multa(codigo, fecha_multa, motivo, sancion, tecnico_asigna):
    """
    Agrega una nueva multa para un estudiante.
    La multa se crea con estado 'pagado = NO' (activa).
    """
    query = """
        INSERT INTO multas 
        (codigo_estudiante, fecha_multa, motivo, sancion, tecnico_asigna, pagado)
        VALUES (?, ?, ?, ?, ?, 'NO')
    """
    db.ejecutar(query, (codigo, fecha_multa, motivo, sancion, tecnico_asigna))


def pagar_multa(id_multa, tecnico_recibe):
    """
    Marca una multa como pagada y registra la fecha actual.
    También guarda el técnico que recibió el pago.
    """
    fecha_hoy = datetime.now().date().strftime("%Y-%m-%d")
    query = """
        UPDATE multas 
        SET pagado = 'SI', fecha_pago = ?, tecnico_recibe = ?
        WHERE id = ?
    """
    db.ejecutar(query, (fecha_hoy, tecnico_recibe, id_multa))


def eliminar_multa(id_multa):
    """
    Elimina físicamente una multa de la base de datos.
    """
    db.ejecutar("DELETE FROM multas WHERE id = ?", (id_multa,))


def tiene_multas_activas(codigo):
    """
    Verifica si un estudiante tiene multas activas (pagado = 'NO').
    Retorna True si tiene al menos una, False en caso contrario.
    """
    query = "SELECT COUNT(*) FROM multas WHERE codigo_estudiante = ? AND pagado = 'NO'"
    result = db.ejecutar(query, (codigo,), fetch=True)
    return result[0][0] > 0 if result else False