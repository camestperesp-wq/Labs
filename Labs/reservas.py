# reservas.py

import database as db
from utils import generar_multa
from constants import LABORATORIOS, LABS_NAMES
import streamlit as st


CLAVE_INTERCAMBIOS_RESERVAS = "intercambios_reservas_por_fecha"


def obtener_intercambios_fecha(fecha):
    """Devuelve la permutación visual de celdas para una fecha de esta sesión."""
    todos = st.session_state.get(CLAVE_INTERCAMBIOS_RESERVAS, {})
    return dict(todos.get(str(fecha), {}))


def coordenada_origen_visual(fecha, hora, laboratorio):
    """Resuelve qué celda base debe mostrarse en una posición del calendario."""
    clave = f"{hora}|{laboratorio}"
    origen = obtener_intercambios_fecha(fecha).get(clave, clave)
    return tuple(origen.split("|", 1))


def intercambiar_espacios_sesion(fecha, hora_origen, lab_origen, hora_destino, lab_destino):
    """Permuta dos posiciones solo en session_state; nunca escribe en SQLite."""
    if not all((fecha, hora_origen, lab_origen, hora_destino, lab_destino)):
        raise ValueError("Las dos celdas del intercambio son obligatorias.")
    clave_origen = f"{hora_origen}|{lab_origen}"
    clave_destino = f"{hora_destino}|{lab_destino}"
    if clave_origen == clave_destino:
        raise ValueError("Selecciona dos espacios diferentes.")
    fecha = str(fecha)
    todos = dict(st.session_state.get(CLAVE_INTERCAMBIOS_RESERVAS, {}))
    mapa = dict(todos.get(fecha, {}))
    contenido_origen = mapa.get(clave_origen, clave_origen)
    contenido_destino = mapa.get(clave_destino, clave_destino)
    mapa[clave_origen] = contenido_destino
    mapa[clave_destino] = contenido_origen
    todos[fecha] = mapa
    # Reasignar el objeto completo garantiza que Streamlit conserve la mutación
    # antes del rerun del diálogo.
    st.session_state[CLAVE_INTERCAMBIOS_RESERVAS] = todos
    st.session_state["intercambios_reservas_revision"] = (
        int(st.session_state.get("intercambios_reservas_revision", 0)) + 1
    )
    return mapa


def aplicar_intercambios_busqueda(df):
    """Proyecta salones/horas temporales en resultados sin alterar sus registros."""
    if df is None or df.empty or not {"fecha", "hora", "laboratorio"}.issubset(df.columns):
        return df
    resultado = df.copy()
    mapas = st.session_state.get(CLAVE_INTERCAMBIOS_RESERVAS, {})
    inversos = {
        fecha: {origen: destino for destino, origen in mapa.items()}
        for fecha, mapa in mapas.items()
    }
    for indice, fila in resultado.iterrows():
        fecha = str(fila["fecha"])
        origen = f"{fila['hora']}|{fila['laboratorio']}"
        destino = inversos.get(fecha, {}).get(origen)
        if destino:
            hora, laboratorio = destino.split("|", 1)
            resultado.at[indice, "hora"] = hora
            resultado.at[indice, "laboratorio"] = laboratorio
    return resultado

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
        st.error(" Ya tienes una reserva activa en esta fecha y hora. No puedes reservar en dos laboratorios al mismo tiempo.")
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
        st.error(f" El banco {banco} ya está ocupado en este laboratorio y horario.")
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
        st.error(f" El laboratorio está reservado completo en este horario.")
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
        st.error(f" El laboratorio {LABS_NAMES.get(laboratorio, laboratorio)} ya tiene reservas en este bloque.")
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
    if estado not in ("Si", "No"):
        raise ValueError("El estado docente solo puede ser 'Si' o 'No'.")

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
    # Guardado idempotente: un doble clic o rerun no crea dos asistencias.
    with db.get_connection() as conn:
        existente = conn.execute(
            """SELECT id FROM reservas
               WHERE fecha=? AND hora=? AND laboratorio=? AND codigo='PROFESOR'
                 AND nombres=? AND activo=1
               ORDER BY id DESC LIMIT 1""",
            (fecha, hora, laboratorio, nombre_docente),
        ).fetchone()
        if existente:
            conn.execute(
                """UPDATE reservas
                   SET proyecto=?, asiste=?, observaciones=?, tecnico=?, banco=0
                   WHERE id=?""",
                (asignatura, estado, f"Asistencia docente: {asignatura}", tecnico, existente[0]),
            )
        else:
            conn.execute(
                """INSERT INTO reservas
                   (fecha, hora, laboratorio, banco, codigo, nombres, proyecto, asiste, observaciones, tecnico, activo)
                   VALUES (?,?,?,?,?,?,?,?,?,?,1)""",
                datos,
            )
        conn.commit()
    db.clear_cache()
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
    df = db.fetch_df("""SELECT
                            r.id, r.fecha, r.hora, r.laboratorio, r.banco,
                            r.codigo, r.nombres, r.proyecto, r.asiste,
                            r.observaciones, r.tecnico,
                            (SELECT COUNT(*)
                               FROM multas m
                              WHERE trim(m.codigo_estudiante) = trim(r.codigo)
                                AND upper(trim(coalesce(m.pagado, 'NO'))) = 'NO'
                            ) AS multas_activas
                       FROM reservas r
                       WHERE r.codigo LIKE ? AND r.activo=1
                       ORDER BY r.fecha DESC, r.hora ASC""",
                    (f'%{termino}%',))
    return aplicar_intercambios_busqueda(df)

def get_reporte_completo(fecha_desde, fecha_hasta):
    """
    Obtiene un reporte completo de reservas en un rango de fechas.
    """
    df = db.fetch_df("""
        SELECT fecha, hora, laboratorio, banco, codigo, nombres, proyecto, observaciones, tecnico,
               CASE WHEN asiste='Si' THEN 'Asistio' WHEN asiste='No' THEN 'No asistio' ELSE 'Pendiente' END as estado
        FROM reservas WHERE fecha BETWEEN ? AND ? AND activo=1
        ORDER BY laboratorio, fecha, hora
    """, (fecha_desde, fecha_hasta))
    return aplicar_intercambios_busqueda(df)

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


def actualizar_reservas_desde_editor(cambios):
    """
    Actualiza banco y estudiante desde el editor de reservas.
    Valida el estado final completo para permitir intercambios entre filas.
    """
    if not cambios:
        return True, []

    ids = [int(cambio["id"]) for cambio in cambios]
    placeholders = ",".join("?" for _ in ids)
    actuales = db.ejecutar(
        f"""SELECT id, laboratorio, fecha, hora, banco, codigo, nombres, proyecto
            FROM reservas
            WHERE id IN ({placeholders}) AND activo=1""",
        tuple(ids),
        fetch=True,
    )
    actuales_por_id = {row[0]: row for row in actuales}
    errores = []
    estudiantes_por_codigo = {}

    for cambio in cambios:
        id_res = int(cambio["id"])
        nuevo_codigo = "" if cambio["codigo"] is None else str(cambio["codigo"]).strip()
        nuevo_banco = int(cambio["banco"])
        actual = actuales_por_id.get(id_res)

        if not actual:
            errores.append(f"Reserva {id_res}: no encontrada")
            continue

        _, _, _, _, banco_actual, codigo_actual, nombres_actual, _ = actual
        if codigo_actual == "PROFESOR" or banco_actual == 0:
            if nuevo_codigo != codigo_actual or nuevo_banco != banco_actual:
                errores.append(f"{nombres_actual}: las reservas docentes no se cambian desde este editor")
            continue

        if not nuevo_codigo:
            errores.append(f"{nombres_actual}: el codigo no puede quedar vacio")
            continue

        if nuevo_codigo == "PROFESOR":
            errores.append(f"{nombres_actual}: PROFESOR no es un codigo valido para reserva individual")
            continue

        estudiante = db.ejecutar(
            "SELECT codigo, nombres, proyecto FROM estudiantes WHERE codigo=?",
            (nuevo_codigo,),
            fetch=True,
        )
        if not estudiante:
            errores.append(f"{nombres_actual}: el codigo {nuevo_codigo} no existe en estudiantes")
            continue
        estudiantes_por_codigo[nuevo_codigo] = estudiante[0]

    if errores:
        return False, errores

    cambios_por_id = {int(cambio["id"]): cambio for cambio in cambios}
    grupos_banco = {
        (actual[1], actual[2], actual[3])
        for actual in actuales_por_id.values()
    }

    for lab, fecha, hora in grupos_banco:
        rows = db.ejecutar(
            """SELECT id, banco, nombres FROM reservas
                WHERE laboratorio=? AND fecha=? AND hora=?
                AND activo=1
                AND (asiste != 'No' OR asiste IS NULL OR asiste = '')""",
            (lab, fecha, hora),
            fetch=True,
        )
        bancos = {}
        for id_res, banco, nombre in rows:
            cambio = cambios_por_id.get(id_res)
            banco_final = int(cambio["banco"]) if cambio else banco
            if banco_final == 0:
                continue
            if banco_final in bancos:
                errores.append(f"Banco {banco_final} duplicado entre {bancos[banco_final]} y {nombre}")
            else:
                bancos[banco_final] = nombre

    grupos_codigo = {
        (actual[2], actual[3])
        for actual in actuales_por_id.values()
    }

    for fecha, hora in grupos_codigo:
        rows = db.ejecutar(
            """SELECT id, codigo, nombres FROM reservas
                WHERE fecha=? AND hora=?
                AND activo=1
                AND codigo != 'PROFESOR'
                AND (asiste != 'No' OR asiste IS NULL OR asiste = '')""",
            (fecha, hora),
            fetch=True,
        )
        codigos = {}
        for id_res, codigo, nombre in rows:
            cambio = cambios_por_id.get(id_res)
            codigo_final = str(cambio["codigo"]).strip() if cambio and cambio["codigo"] is not None else codigo
            if codigo_final in codigos:
                errores.append(f"Codigo {codigo_final} duplicado entre {codigos[codigo_final]} y {nombre}")
            else:
                codigos[codigo_final] = nombre

    if errores:
        return False, errores

    with db.get_connection() as conn:
        c = conn.cursor()
        for cambio in cambios:
            id_res = int(cambio["id"])
            nuevo_banco = int(cambio["banco"])
            nuevo_codigo = "" if cambio["codigo"] is None else str(cambio["codigo"]).strip()
            estudiante = estudiantes_por_codigo[nuevo_codigo]
            c.execute(
                """UPDATE reservas
                    SET banco=?, codigo=?, nombres=?, proyecto=?
                    WHERE id=?""",
                (
                    nuevo_banco,
                    nuevo_codigo,
                    estudiante[1],
                    estudiante[2] if estudiante[2] else "",
                    id_res,
                ),
            )
        conn.commit()

    db.clear_cache()
    return True, []
