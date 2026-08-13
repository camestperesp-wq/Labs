# reservas.py

import database as db
from utils import generar_multa
from constants import LABORATORIOS, LABS_NAMES
import streamlit as st

# ============================================================
#  FUNCIONES DE VERIFICACIÓN Y GUARDADO
# ============================================================

def verificar_reserva_existente(codigo, fecha, hora, laboratorio=None):
    if laboratorio:
        query = """
            SELECT COUNT(*) FROM reservas 
            WHERE codigo=? AND fecha=? AND hora=? 
            AND laboratorio=? AND activo=1 
            AND (asiste != 'No' OR asiste IS NULL OR asiste = '')
        """
        params = (codigo, fecha, hora, laboratorio)
    else:
        query = """
            SELECT COUNT(*) FROM reservas 
            WHERE codigo=? AND fecha=? AND hora=? 
            AND activo=1 
            AND (asiste != 'No' OR asiste IS NULL OR asiste = '')
        """
        params = (codigo, fecha, hora)
    
    r = db.ejecutar(query, params, fetch=True)
    return r[0][0] > 0

def guardar_reserva(data):
    """
    Guarda una reserva individual (estudiante).
    """
    codigo = data[4]
    fecha = data[0]
    hora = data[1]
    laboratorio = data[2]
    banco = data[3]
    
    # 1. Verificar que el estudiante no tenga reserva en este horario (cualquier laboratorio)
    if verificar_reserva_existente(codigo, fecha, hora, None):
        st.error("❌ Ya tienes una reserva activa en esta fecha y hora. No puedes reservar en dos laboratorios al mismo tiempo.")
        return False
    
    # 2. NUEVO: Verificar que el banco esté disponible en este laboratorio, fecha y hora
    r = db.ejecutar("""SELECT COUNT(*) FROM reservas 
                        WHERE laboratorio=? AND fecha=? AND hora=? 
                        AND banco=? 
                        AND activo=1 
                        AND (asiste != 'No' OR asiste IS NULL OR asiste = '')""", 
                     (laboratorio, fecha, hora, banco), fetch=True)
    banco_ocupado = r[0][0] > 0 if r else False
    
    if banco_ocupado:
        st.error(f"❌ El banco {banco} ya está ocupado en este laboratorio y horario.")
        return False
    
    # 3. Verificar reserva completa (profesor) en este laboratorio
    r_completa = db.ejecutar("""SELECT COUNT(*) FROM reservas 
                                WHERE laboratorio=? AND fecha=? AND hora=? 
                                AND banco = 0 
                                AND activo=1 
                                AND (asiste != 'No' OR asiste IS NULL OR asiste = '')""", 
                             (laboratorio, fecha, hora), fetch=True)
    tiene_reserva_completa = r_completa[0][0] > 0 if r_completa else False
    
    if tiene_reserva_completa:
        st.error(f"❌ El laboratorio está reservado completo en este horario.")
        return False
    
    # 4. Si todo está bien, guardar
    query = """INSERT INTO reservas 
                (fecha, hora, laboratorio, banco, codigo, nombres, proyecto, asiste, observaciones, tecnico, activo) 
                VALUES (?,?,?,?,?,?,?,?,?,?,1)"""
    db.ejecutar(query, data)
    return True
def guardar_reserva_profesor(fecha, hora, laboratorio, motivo, nombre_profesor, tecnico):
    """
    Guarda una reserva de profesor para TODO el laboratorio.
    Crea un único registro con banco = 0 (sala completa).
    SOLO verifica que no haya reservas ACTIVAS en ESE laboratorio específico.
    NO bloquea por reservas en otros laboratorios (los profesores pueden reservar en diferentes labs).
    """
    total_bancos = LABORATORIOS.get(laboratorio, 0)
    if total_bancos == 0:
        return False
    
    # ===== SOLO VERIFICAR EN ESTE LABORATORIO =====
    # Verificar si ya hay reservas activas en ESTE laboratorio (cualquier tipo)
    r = db.ejecutar("""SELECT COUNT(*) FROM reservas 
                        WHERE laboratorio=? AND fecha=? AND hora=? 
                        AND activo=1 
                        AND (asiste != 'No' OR asiste IS NULL OR asiste = '')""", 
                     (laboratorio, fecha, hora), fetch=True)
    reservas_activas = r[0][0]
    
    if reservas_activas > 0:
        st.error(f"❌ El laboratorio {LABS_NAMES.get(laboratorio, laboratorio)} ya tiene reservas en este bloque.")
        return False
    
    # Crear UN SOLO registro con banco = 0 (sala completa)
    datos = (
        fecha,           # fecha
        hora,            # hora
        laboratorio,     # laboratorio
        0,               # banco = 0 (sala completa)
        "PROFESOR",      # codigo
        nombre_profesor, # nombres (nombre del profesor)
        motivo,          # proyecto (motivo de la reserva)
        "",              # asiste (pendiente)
        f"Reserva de profesor: {motivo}",  # observaciones
        tecnico          # tecnico
    )
    db.ejecutar("""INSERT INTO reservas 
                (fecha, hora, laboratorio, banco, codigo, nombres, proyecto, asiste, observaciones, tecnico, activo) 
                VALUES (?,?,?,?,?,?,?,?,?,?,1)""", datos)
    
    return True
def registrar_asistencia_docente(fecha, hora, laboratorio, nombre_docente, asignatura, estado, tecnico):
    """
    Registra la asistencia de un docente para un bloque de horario fijo.
    Crea un registro en reservas con banco = 0.
    """
    datos = (
        fecha,           # fecha
        hora,            # hora
        laboratorio,     # laboratorio
        0,               # banco = 0 (sala completa)
        "PROFESOR",      # codigo
        nombre_docente,  # nombres (nombre del docente)
        asignatura,      # proyecto (asignatura del horario fijo)
        estado,          # asiste ("Si" o "No")
        f"Asistencia docente: {asignatura}",  # observaciones
        tecnico          # tecnico
    )
    db.ejecutar("""INSERT INTO reservas 
                (fecha, hora, laboratorio, banco, codigo, nombres, proyecto, asiste, observaciones, tecnico, activo) 
                VALUES (?,?,?,?,?,?,?,?,?,?,1)""", datos)
    return True

# ============================================================
#  ACTUALIZACIÓN DE ASISTENCIA
# ============================================================

def actualizar_asiste(id_res, estado, tecnico=None):
    r = db.ejecutar("SELECT laboratorio, fecha, hora, codigo FROM reservas WHERE id=?", (id_res,), fetch=True)
    if not r:
        return
    
    lab, fecha, hora, codigo = r[0]
    
    # Actualizar el estado en la reserva
    db.ejecutar("UPDATE reservas SET asiste=? WHERE id=?", (estado, id_res))
    
    # Si es profesor, NO generar multa (solo actualizar estado)
    if codigo == "PROFESOR":
        return
    
    # Si es estudiante y estado es 'No', generar multa
    if estado == "No":
        from datetime import datetime
        fecha_hoy = datetime.now().date().strftime("%Y-%m-%d")
        motivo = f"No asistió a {lab} - {fecha} {hora}"
        
        estudiante = db.ejecutar("SELECT nombres FROM estudiantes WHERE codigo=?", (codigo,), fetch=True)
        if estudiante:
            tecnico_asigna = tecnico if tecnico else "Sistema"
            db.ejecutar("""
                INSERT INTO multas 
                (codigo_estudiante, fecha_multa, motivo, sancion, tecnico_asigna, pagado)
                VALUES (?, ?, ?, ?, ?, 'NO')
            """, (codigo, fecha_hoy, motivo, "", tecnico_asigna))
# ============================================================
#  ELIMINACIÓN
# ============================================================

def eliminar_reserva(id_res):
    """
    Elimina físicamente una reserva de la base de datos.
    """
    db.ejecutar("DELETE FROM reservas WHERE id=?", (id_res,))

# ============================================================
#  CONSULTAS
# ============================================================

def get_reservas_fecha_lab(fecha, lab):
    """
    Obtiene todas las reservas de un laboratorio en una fecha específica.
    """
    return db.fetch_df("""SELECT id, fecha, hora, laboratorio, banco, codigo, nombres, proyecto, asiste, observaciones, tecnico 
                       FROM reservas WHERE fecha=? AND laboratorio=? AND activo=1 ORDER BY hora""", 
                    (fecha, lab))

def get_reservas_fecha_lab_hora(fecha, lab, hora):
    """
    Obtiene las reservas de un laboratorio en una fecha y hora específica.
    """
    return db.fetch_df("""SELECT id, fecha, hora, laboratorio, banco, codigo, nombres, proyecto, asiste, observaciones, tecnico 
                       FROM reservas WHERE fecha=? AND laboratorio=? AND hora=? AND activo=1 ORDER BY hora""", 
                    (fecha, lab, hora))

def buscar_reservas_persona(termino):
    """
    Busca reservas de una persona por su código (parcial).
    """
    return db.fetch_df("""SELECT id, fecha, hora, laboratorio, banco, codigo, nombres, proyecto, asiste, observaciones, tecnico
                       FROM reservas WHERE codigo LIKE ? AND activo=1 ORDER BY fecha DESC, hora ASC""",
                    (f'%{termino}%',))

def get_reporte_completo(fecha_desde, fecha_hasta):
    """
    Obtiene un reporte completo de reservas en un rango de fechas.
    """
    return db.fetch_df("""
        SELECT fecha, hora, laboratorio, banco, codigo, nombres, proyecto, observaciones, tecnico,
               CASE WHEN asiste='Si' THEN 'Asistio' WHEN asiste='No' THEN 'No asistio' ELSE 'Pendiente' END as estado
        FROM reservas WHERE fecha BETWEEN ? AND ? AND activo=1
        ORDER BY laboratorio, fecha, hora
    """, (fecha_desde, fecha_hasta))

def get_reporte_docentes(fecha_desde, fecha_hasta):
    """
    Obtiene un reporte específico de asistencia de docentes (banco = 0, codigo = 'PROFESOR').
    """
    return db.fetch_df("""
        SELECT fecha, hora, laboratorio, banco, codigo, nombres, proyecto, asiste, observaciones, tecnico
        FROM reservas 
        WHERE fecha BETWEEN ? AND ? 
        AND banco = 0 
        AND codigo = 'PROFESOR'
        ORDER BY laboratorio, fecha, hora
    """, (fecha_desde, fecha_hasta))

# ============================================================
#  MULTAS (para mostrar en reservas)
# ============================================================

def obtener_multas_activas_estudiante(codigo):
    """
    Retorna un texto con las multas activas de un estudiante (desde tabla multas).
    """
    query = """
        SELECT motivo, fecha_multa, sancion 
        FROM multas 
        WHERE codigo_estudiante = ? AND pagado = 'NO'
    """
    rows = db.ejecutar(query, (codigo,), fetch=True)
    if rows:
        return "\n".join([f"• {row[0]} ({row[1]}) - Sanción: {row[2]}" for row in rows])
    return ""
def cambiar_banco_reserva(id_res, nuevo_banco):
    """
    Cambia el banco de una reserva existente.
    Verifica que el nuevo banco esté disponible.
    """
    # Obtener la reserva actual
    r = db.ejecutar("SELECT laboratorio, fecha, hora FROM reservas WHERE id=?", (id_res,), fetch=True)
    if not r:
        return False, "Reserva no encontrada"
    
    lab, fecha, hora = r[0]
    
    # Verificar que el nuevo banco esté disponible
    r = db.ejecutar("""SELECT COUNT(*) FROM reservas 
                        WHERE laboratorio=? AND fecha=? AND hora=? 
                        AND banco=? 
                        AND activo=1 
                        AND id != ?
                        AND (asiste != 'No' OR asiste IS NULL OR asiste = '')""", 
                     (lab, fecha, hora, nuevo_banco, id_res), fetch=True)
    banco_ocupado = r[0][0] > 0 if r else False
    
    if banco_ocupado:
        return False, f"El banco {nuevo_banco} ya está ocupado en este horario"
    
    # Actualizar el banco
    db.ejecutar("UPDATE reservas SET banco = ? WHERE id = ?", (nuevo_banco, id_res))
    return True, "Banco actualizado correctamente"