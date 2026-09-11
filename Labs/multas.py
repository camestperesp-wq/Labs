# multas.py

import database as db
from datetime import datetime
import pandas as pd

MOTIVOS_ESTANDAR = (
    "ABANDONO O NO DEVOLUCIÓN DE EQUIPOS",
    "AGRESIÓN AL PERSONAL O USUARIOS",
    "ALTERACIÓN DE EQUIPOS O ELEMENTOS",
    "CONSUMO DE ALIMENTOS O BEBIDAS",
    "ACTIVIDADES O EQUIPOS NO AUTORIZADOS",
    "USO DE ELEMENTOS DE DISTRACCIÓN",
    "FUMAR EN LABORATORIOS",
    "USO NO AUTORIZADO DE EQUIPOS",
    "INGRESO BAJO EFECTOS DE SUSTANCIAS",
    "SIN ELEMENTOS DE SEGURIDAD",
    "INGRESO DE NIÑOS O MASCOTAS",
    "TRASLADO NO AUTORIZADO DE EQUIPOS",
    "DOCUMENTOS FALSOS O SUPLANTACIÓN",
)

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


def obtener_motivos_registrados():
    """Conceptos existentes; no inventa lineamientos institucionales."""
    return [row[0] for row in db.ejecutar(
        "SELECT DISTINCT trim(motivo) FROM multas WHERE trim(coalesce(motivo,'')) != '' ORDER BY 1",
        fetch=True) if row[0] != "Otras"]


def detalles_multas_activas():
    detalles = {}
    for codigo, fecha, motivo in db.ejecutar(
        "SELECT codigo_estudiante,fecha_multa,motivo FROM multas WHERE pagado='NO' ORDER BY fecha_multa,id",
        fetch=True,
    ):
        detalles.setdefault(str(codigo).strip(), []).append(f"{fecha or 'Sin fecha'}: {motivo or 'Sin concepto registrado'}")
    return {codigo: "\n".join(filas) for codigo, filas in detalles.items()}


def obtener_multas_estudiante(codigo):
    """
    Retorna un DataFrame con todas las multas de un estudiante (activas e históricas).
    """
    query = """
        SELECT id, fecha_multa, fecha_pago, motivo, sancion, 
               tecnico_asigna, tecnico_recibe, pagado, correo_usuario, observaciones
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


def contar_multas_activas(codigo):
    """Retorna el total de multas activas con una consulta escalar indexada."""
    resultado = db.ejecutar(
        "SELECT COUNT(*) FROM multas WHERE codigo_estudiante = ? AND pagado = 'NO'",
        (str(codigo).strip(),),
        fetch=True,
    )
    return int(resultado[0][0]) if resultado else 0


def tiene_bloqueo_critico(codigo):
    """La política exige autorización manual cuando hay más de tres multas."""
    return contar_multas_activas(codigo) > 3

def tiene_multas_activas(codigo):
    """
    Verifica si un estudiante tiene multas activas (pagado = 'NO').
    Retorna True si tiene al menos una, False en caso contrario.
    """
    query = "SELECT COUNT(*) FROM multas WHERE codigo_estudiante = ? AND pagado = 'NO'"
    result = db.ejecutar(query, (codigo,), fetch=True)
    return result[0][0] > 0 if result else False
