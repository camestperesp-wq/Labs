"""Lógica de datos para inventario y préstamos de equipos de pasillo."""

from datetime import datetime, timedelta
import io
import unicodedata

import pandas as pd
import streamlit as st

import database as db
from constants import TECNICOS


CACHE_TTL_SEGUNDOS = 60
TOLERANCIA_FPGA_MINUTOS = 20


def _invalidar_cache_lecturas():
    """Invalida las vistas afectadas por una escritura, sin intervención del usuario."""
    obtener_equipos.clear()
    obtener_prestamos.clear()
    obtener_prestamos_activos_codigo.clear()
    obtener_solicitante.clear()
    obtener_alertas_bloqueo.clear()
    db.clear_cache()


def _texto(valor, campo):
    texto = "" if valor is None else str(valor).strip()
    if not texto or texto.lower() == "nan":
        raise ValueError(f"{campo} es obligatorio.")
    return texto


def _texto_opcional(valor):
    texto = "" if valor is None else str(valor).strip()
    return None if not texto or texto.lower() == "nan" else texto


def _normalizar_columna(valor):
    texto = unicodedata.normalize("NFKD", str(valor).strip().lower())
    return "".join(caracter for caracter in texto if not unicodedata.combining(caracter))


def registrar_equipo(placa, nombre, numero_interno):
    placa = _texto_opcional(placa)
    nombre = _texto(nombre, "Nombre del equipo")
    numero_interno = _texto(numero_interno, "Número interno")
    try:
        with db.get_connection() as conn:
            conn.execute(
                """INSERT INTO equipos_pasillo (placa, nombre, numero_interno)
                   VALUES (?, ?, ?)""",
                (placa, nombre, numero_interno),
            )
            conn.commit()
    except Exception as error:
        if "UNIQUE constraint failed" in str(error):
            raise ValueError("La placa o el número interno ya están registrados.") from error
        raise
    _invalidar_cache_lecturas()


def eliminar_equipo(equipo_id):
    """Desactiva un equipo solo cuando no pertenece a un préstamo abierto."""
    with db.get_connection() as conn:
        activo = conn.execute(
            """SELECT 1 FROM prestamos_pasillo_equipos pe
               JOIN prestamos_pasillo p ON p.id=pe.prestamo_id
               WHERE pe.equipo_id=? AND p.estado='PRESTADO' LIMIT 1""",
            (int(equipo_id),),
        ).fetchone()
        if activo:
            raise ValueError("No se puede eliminar un equipo con un préstamo activo.")
        cursor = conn.execute(
            "UPDATE equipos_pasillo SET activo=0 WHERE id=? AND activo=1",
            (int(equipo_id),),
        )
        if cursor.rowcount != 1:
            raise ValueError("El equipo no existe o ya fue eliminado.")
        conn.commit()
    _invalidar_cache_lecturas()


def cargar_inventario_excel(archivo):
    """Valida y carga un .xlsx completo en una única transacción."""
    contenido = archivo.getvalue() if hasattr(archivo, "getvalue") else archivo.read()
    tabla = pd.read_excel(io.BytesIO(contenido), dtype=str)
    columnas = {_normalizar_columna(columna): columna for columna in tabla.columns}
    alias = {
        "placa": ("numero de placa", "numero placa", "placa"),
        "nombre": ("nombre del equipo", "nombre equipo", "equipo", "nombre"),
        "numero_interno": ("numero interno", "nro interno", "interno", "id_elemento", "codigo_inventario"),
    }
    seleccion = {}
    for destino, opciones in alias.items():
        seleccion[destino] = next((columnas[o] for o in opciones if o in columnas), None)
        if seleccion[destino] is None and destino != "placa":
            raise ValueError(
                "El Excel debe incluir: Número de placa, Nombre del equipo y Número interno."
            )

    registros = []
    for numero_fila, fila in tabla.iterrows():
        try:
            registros.append((
                _texto_opcional(fila[seleccion["placa"]]) if seleccion["placa"] else None,
                _texto(fila[seleccion["nombre"]], "Nombre del equipo"),
                _texto(fila[seleccion["numero_interno"]], "Número interno"),
            ))
        except ValueError as error:
            raise ValueError(f"Fila {numero_fila + 2}: {error}") from error

    if not registros:
        raise ValueError("El archivo no contiene equipos.")
    placas = [r[0] for r in registros if r[0] is not None]
    if len(set(placas)) != len(placas):
        raise ValueError("El archivo contiene números de placa duplicados.")
    if len({r[2] for r in registros}) != len(registros):
        raise ValueError("El archivo contiene números internos duplicados.")

    try:
        with db.get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            for placa, nombre, numero_interno in registros:
                coincidencias = conn.execute(
                    "SELECT id,placa FROM equipos_pasillo WHERE numero_interno=? OR placa=?",
                    (numero_interno, placa),
                ).fetchall()
                if len(coincidencias) > 1:
                    raise ValueError("La placa y el número interno corresponden a equipos diferentes.")
                if coincidencias:
                    conn.execute("""UPDATE equipos_pasillo SET placa=?,nombre=?,numero_interno=?,activo=1
                                 WHERE id=?""",
                                 (placa or coincidencias[0][1], nombre, numero_interno, coincidencias[0][0]))
                else:
                    conn.execute("INSERT INTO equipos_pasillo(placa,nombre,numero_interno) VALUES (?,?,?)",
                                 (placa, nombre, numero_interno))
            conn.commit()
    except Exception as error:
        if "UNIQUE constraint failed" in str(error):
            raise ValueError("Un número interno ya pertenece a otra placa.") from error
        raise
    _invalidar_cache_lecturas()
    return len(registros)


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS, show_spinner=False)
def obtener_equipos(solo_disponibles=False):
    prestado_sql = """EXISTS (
        SELECT 1 FROM prestamos_pasillo_equipos pe
        JOIN prestamos_pasillo p ON p.id=pe.prestamo_id
        WHERE pe.equipo_id=e.id AND p.estado='PRESTADO'
    )"""
    condicion = f"AND NOT {prestado_sql}" if solo_disponibles else ""
    with db.get_connection() as conn:
        return pd.read_sql_query(
            f"""SELECT e.id, coalesce(e.placa, '') AS placa, e.nombre, e.numero_interno,
                       CASE WHEN {prestado_sql} THEN 'Prestado' ELSE 'Disponible' END AS estado
                  FROM equipos_pasillo e
                 WHERE e.activo=1 {condicion}
                 ORDER BY e.nombre COLLATE NOCASE, e.placa""",
            conn,
        )


def listar_equipos(solo_disponibles=False):
    """Alias compatible para consumidores existentes."""
    return obtener_equipos(solo_disponibles)


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS, show_spinner=False)
def obtener_tecnicos():
    """Lista estable de técnicos configurados para entrega y recepción."""
    return tuple(TECNICOS)


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS, show_spinner=False)
def obtener_solicitante(codigo):
    codigo = str(codigo or "").strip()
    if not codigo:
        return None
    with db.get_connection() as conn:
        fila = conn.execute(
            "SELECT codigo, nombres, proyecto FROM estudiantes WHERE codigo=? LIMIT 1",
            (codigo,),
        ).fetchone()
    if not fila:
        return None
    return {"codigo": fila[0], "nombres": fila[1], "proyecto": fila[2]}


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS, show_spinner=False)
def obtener_alertas_bloqueo(codigo):
    codigo = str(codigo or "").strip()
    if not codigo:
        return []
    with db.get_connection() as conn:
        generales = conn.execute(
            """SELECT motivo, fecha_multa FROM multas
               WHERE codigo_estudiante=? AND pagado='NO' ORDER BY fecha_multa DESC""",
            (codigo,),
        ).fetchall()
        prestamos = conn.execute(
            """SELECT motivo, fecha_incidente, retraso_minutos FROM multas_prestamos
               WHERE codigo_estudiante=? AND estado='PENDIENTE'
               ORDER BY fecha_incidente DESC""",
            (codigo,),
        ).fetchall()
    alertas = [f"{motivo} — {fecha}" for motivo, fecha in generales]
    alertas.extend(
        f"{motivo} — {fecha} — retraso {_formatear_retraso(minutos)}"
        for motivo, fecha, minutos in prestamos
    )
    return alertas


def _formatear_retraso(minutos):
    minutos = max(0, int(minutos or 0))
    horas, resto = divmod(minutos, 60)
    return f"{horas} h {resto} min"


def _crear_multa_prestamo(conn, prestamo_id, codigo, tipo, motivo, incidente,
                           referencia, retraso_minutos, monto_pago=0, tecnico=None):
    cursor = conn.execute(
        """INSERT OR IGNORE INTO multas_prestamos
           (prestamo_id, codigo_estudiante, tipo, motivo, fecha_incidente,
            fecha_limite_referencia, retraso_minutos, monto_pago, tecnico_responsable)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (prestamo_id, codigo, tipo, motivo, incidente, referencia,
         max(0, int(retraso_minutos)), max(0, float(monto_pago or 0)), tecnico),
    )
    if float(monto_pago or 0) > 0:
        conn.execute(
            """UPDATE multas_prestamos SET monto_pago=?, tecnico_responsable=coalesce(?, tecnico_responsable)
               WHERE prestamo_id=? AND tipo=? AND fecha_limite_referencia=?""",
            (float(monto_pago), tecnico, prestamo_id, tipo, referencia),
        )
    return cursor.rowcount


def _registrar_incumplimientos(conn, prestamo, momento, monto_pago=0, tecnico=None,
                               detalle_multa="", registrar_fpga=True):
    prestamo_id, codigo, fecha_salida, limite_fpga = prestamo
    salida = datetime.fromisoformat(fecha_salida)
    incidente = momento.isoformat(sep=" ", timespec="seconds")
    creadas = 0
    if momento.date() > salida.date():
        limite_dia = datetime.combine(salida.date(), datetime.max.time()).replace(microsecond=0)
        retraso = int((momento - limite_dia).total_seconds() // 60)
        creadas += _crear_multa_prestamo(
            conn, prestamo_id, codigo, "DEVOLUCION_DIA_SIGUIENTE",
            "No devolvió el equipo el mismo día", incidente,
            limite_dia.isoformat(sep=" "), retraso, monto_pago, tecnico,
        )
    if limite_fpga:
        limite = datetime.fromisoformat(limite_fpga)
        limite_con_gracia = limite + timedelta(minutes=TOLERANCIA_FPGA_MINUTOS)
        if registrar_fpga and momento > limite_con_gracia:
            detalle = str(detalle_multa or "").strip()
            if not detalle:
                raise ValueError("El técnico debe escribir el registro de la multa por retraso.")
            retraso = int((momento - limite_con_gracia).total_seconds() // 60)
            creadas += _crear_multa_prestamo(
                conn, prestamo_id, codigo, "FPGA_RETRASO",
                f"No renovó a tiempo — {detalle}", incidente,
                limite_con_gracia.isoformat(sep=" "), retraso, 0, tecnico,
            )
    return creadas


def crear_prestamo(equipos_ids, solicitante, tecnico_entrega, observaciones_salida=""):
    solicitante = _texto(solicitante, "Solicitante")
    tecnico_entrega = _texto(tecnico_entrega, "Técnico responsable")
    ids = list(dict.fromkeys(int(equipo_id) for equipo_id in equipos_ids))
    if not ids:
        raise ValueError("Selecciona al menos un equipo.")

    marcadores = ",".join("?" for _ in ids)
    fecha_salida = datetime.now().isoformat(sep=" ", timespec="seconds")
    with db.get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        disponibles = conn.execute(
            f"""SELECT e.id, e.nombre FROM equipos_pasillo e
                 WHERE e.activo=1 AND e.id IN ({marcadores})
                   AND NOT EXISTS (
                       SELECT 1 FROM prestamos_pasillo_equipos pe
                       JOIN prestamos_pasillo p ON p.id=pe.prestamo_id
                       WHERE pe.equipo_id=e.id AND p.estado='PRESTADO'
                   )""",
            ids,
        ).fetchall()
        if {fila[0] for fila in disponibles} != set(ids):
            raise ValueError("Uno o más equipos ya no están disponibles.")
        contiene_fpga = any("FPGA" in str(fila[1]).upper() for fila in disponibles)
        limite_fpga = (datetime.fromisoformat(fecha_salida) + timedelta(hours=2)).isoformat(
            sep=" ", timespec="seconds"
        ) if contiene_fpga else None
        cursor = conn.execute(
            """INSERT INTO prestamos_pasillo
               (solicitante, tecnico_entrega, fecha_salida, observaciones_salida, limite_fpga)
               VALUES (?, ?, ?, ?, ?)""",
            (solicitante, tecnico_entrega, fecha_salida,
             str(observaciones_salida or "").strip(), limite_fpga),
        )
        prestamo_id = cursor.lastrowid
        conn.executemany(
            "INSERT INTO prestamos_pasillo_equipos (prestamo_id, equipo_id) VALUES (?, ?)",
            [(prestamo_id, equipo_id) for equipo_id in ids],
        )
        conn.commit()
    _invalidar_cache_lecturas()
    return prestamo_id


def registrar_devolucion(prestamo_id, receptor, observaciones_entrada="", monto_pago=0,
                         detalle_multa=""):
    receptor = _texto(receptor, "Receptor")
    fecha_retorno = datetime.now().isoformat(sep=" ", timespec="seconds")
    with db.get_connection() as conn:
        prestamo = conn.execute(
            "SELECT id, solicitante, fecha_salida, limite_fpga FROM prestamos_pasillo WHERE id=? AND estado='PRESTADO'",
            (int(prestamo_id),),
        ).fetchone()
        if not prestamo:
            raise ValueError("El préstamo no existe o ya fue devuelto.")
        _registrar_incumplimientos(
            conn, prestamo, datetime.now(), 0, receptor, detalle_multa, True
        )
        cursor = conn.execute(
            """UPDATE prestamos_pasillo
                  SET receptor=?, fecha_retorno=?, observaciones_entrada=?, estado='DEVUELTO'
                WHERE id=? AND estado='PRESTADO'""",
            (receptor, fecha_retorno, str(observaciones_entrada or "").strip(), int(prestamo_id)),
        )
        if cursor.rowcount != 1:
            raise ValueError("El préstamo no existe o ya fue devuelto.")
        conn.commit()
    _invalidar_cache_lecturas()


def renovar_prestamo_fpga(prestamo_id, tecnico, monto_pago=0, detalle_multa=""):
    tecnico = _texto(tecnico, "Técnico responsable")
    momento = datetime.now()
    with db.get_connection() as conn:
        prestamo = conn.execute(
            "SELECT id, solicitante, fecha_salida, limite_fpga FROM prestamos_pasillo WHERE id=? AND estado='PRESTADO'",
            (int(prestamo_id),),
        ).fetchone()
        if not prestamo or not prestamo[3]:
            raise ValueError("El préstamo no corresponde a una FPGA activa.")
        _registrar_incumplimientos(conn, prestamo, momento, 0, tecnico, detalle_multa, True)
        nuevo_limite = (momento + timedelta(hours=2)).isoformat(sep=" ", timespec="seconds")
        conn.execute(
            "UPDATE prestamos_pasillo SET ultima_renovacion=?, limite_fpga=? WHERE id=?",
            (momento.isoformat(sep=" ", timespec="seconds"), nuevo_limite, int(prestamo_id)),
        )
        conn.commit()
    _invalidar_cache_lecturas()
    return nuevo_limite


def sincronizar_incumplimientos():
    """Materializa faltas de cambio de día; la multa FPGA la documenta el técnico."""
    momento = datetime.now()
    with db.get_connection() as conn:
        activos = conn.execute(
            "SELECT id, solicitante, fecha_salida, limite_fpga FROM prestamos_pasillo WHERE estado='PRESTADO'"
        ).fetchall()
        creadas = sum(
            _registrar_incumplimientos(conn, prestamo, momento, registrar_fpga=False)
            for prestamo in activos
        )
        conn.commit()
    if creadas:
        _invalidar_cache_lecturas()


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS, show_spinner=False)
def obtener_prestamos(estado=None):
    filtro = "WHERE p.estado=?" if estado else ""
    parametros = (estado,) if estado else ()
    with db.get_connection() as conn:
        return pd.read_sql_query(
            f"""SELECT p.id, p.solicitante,
                   coalesce(
                       (SELECT nullif(trim(s.nombres), '') FROM estudiantes s
                         WHERE s.codigo=p.solicitante LIMIT 1),
                       p.solicitante
                   ) AS solicitante_nombre,
                   p.tecnico_entrega, p.fecha_salida, p.limite_fpga, p.ultima_renovacion,
                   p.observaciones_salida, p.receptor, p.fecha_retorno,
                   p.observaciones_entrada, p.estado,
                   GROUP_CONCAT(
                       e.nombre
                       || CASE WHEN e.placa IS NULL OR trim(e.placa)=''
                               THEN '' ELSE ' · Placa ' || e.placa END
                       || ' · Interno ' || e.numero_interno,
                       ' | '
                   ) AS equipos,
                   COUNT(e.id) AS cantidad_equipos
                   ,coalesce((
                       SELECT GROUP_CONCAT(detalle, ' | ')
                       FROM (
                           SELECT mp.motivo || ' · ' || mp.fecha_incidente
                                  || ' · retraso ' || mp.retraso_minutos || ' min'
                                  || ' · monto ' || mp.monto_pago
                                  || ' · ' || mp.estado AS detalle
                           FROM multas_prestamos mp WHERE mp.prestamo_id=p.id
                           UNION ALL
                           SELECT m.motivo || ' · ' || m.fecha_multa
                                  || CASE WHEN trim(coalesce(m.sancion, ''))=''
                                          THEN '' ELSE ' · sanción ' || m.sancion END
                                  || ' · ' || CASE WHEN m.pagado='SI' THEN 'PAGADA' ELSE 'PENDIENTE' END
                           FROM multas m WHERE m.codigo_estudiante=p.solicitante
                       )
                   ), '') AS multas_asociadas
              FROM prestamos_pasillo p
              JOIN prestamos_pasillo_equipos pe ON pe.prestamo_id=p.id
              JOIN equipos_pasillo e ON e.id=pe.equipo_id
              {filtro}
             GROUP BY p.id
             ORDER BY CASE WHEN p.estado='PRESTADO' THEN 0 ELSE 1 END,
                          p.fecha_salida DESC""",
            conn,
            params=parametros,
        )


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS, show_spinner=False)
def obtener_prestamos_activos_codigo(codigo):
    """Obtiene solo las salidas pendientes asociadas al código consultado."""
    codigo = str(codigo or "").strip()
    if not codigo:
        return pd.DataFrame()
    with db.get_connection() as conn:
        return pd.read_sql_query(
            """SELECT p.id, p.solicitante,
                      coalesce(
                          (SELECT nullif(trim(nombre.nombres), '') FROM estudiantes nombre
                            WHERE nombre.codigo=p.solicitante LIMIT 1),
                          p.solicitante
                      ) AS solicitante_nombre,
                      p.tecnico_entrega, p.fecha_salida, p.observaciones_salida,
                      p.limite_fpga, p.ultima_renovacion,
                      GROUP_CONCAT(
                          e.nombre
                          || CASE WHEN e.placa IS NULL OR trim(e.placa)=''
                                  THEN '' ELSE ' · Placa ' || e.placa END
                          || ' · Interno ' || e.numero_interno,
                          ' | '
                      ) AS equipos,
                      COUNT(e.id) AS cantidad_equipos
                 FROM prestamos_pasillo p
                 JOIN prestamos_pasillo_equipos pe ON pe.prestamo_id=p.id
                 JOIN equipos_pasillo e ON e.id=pe.equipo_id
                WHERE p.estado='PRESTADO'
                  AND (
                      p.solicitante=?
                      OR EXISTS (
                          SELECT 1 FROM estudiantes legado
                           WHERE legado.codigo=? AND legado.nombres=p.solicitante
                      )
                  )
                GROUP BY p.id
                ORDER BY p.fecha_salida DESC""",
            conn,
            params=(codigo, codigo),
        )


def listar_prestamos(estado=None):
    """Alias compatible para consumidores existentes."""
    return obtener_prestamos(estado)
