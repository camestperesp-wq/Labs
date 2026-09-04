import streamlit as st
import database as db
from datetime import datetime
from constants import LABS_NAMES, DIAS
import reservas as res
from utils import parse_fecha_a_espanol

def obtener_asistencias_pendientes():
    hoy = datetime.now().date().strftime("%Y-%m-%d")
    dia_semana = parse_fecha_a_espanol(hoy)
    hora_actual = datetime.now().hour

    # Una sola ida a SQLite: evita concatenaciones y filtros fila a fila.
    query = """
        SELECT 
            id, fecha, hora, laboratorio, banco, codigo, nombres, proyecto,
            'Estudiante' as tipo
        FROM reservas
        WHERE (asiste IS NULL OR asiste = '')
        AND fecha = ?
        AND activo = 1
        AND codigo != 'PROFESOR'
        AND CAST(substr(hora, 1, 2) AS INTEGER) <= ?

        UNION ALL

        SELECT
            'prof_' || h.profesor || '_' || h.hora || '_' || h.laboratorio AS id,
            ? AS fecha,
            h.hora,
            h.laboratorio,
            0 AS banco,
            'PROFESOR' AS codigo,
            h.profesor AS nombres,
            h.asignatura AS proyecto,
            'Docente' AS tipo
        FROM horario_fijo h
        WHERE h.dia_semana = ?
          AND h.profesor IS NOT NULL
          AND trim(h.profesor) != ''
          AND h.laboratorio NOT IN ('FLU 101', 'PRO 102', 'MEC 103', 'NEW 408', 'ELE 509', 'OND 510')
          AND CAST(substr(h.hora, 1, 2) AS INTEGER) <= ?
          AND NOT EXISTS (
              SELECT 1
              FROM reservas r
              WHERE r.fecha = ?
                AND r.hora = h.hora
                AND r.laboratorio = h.laboratorio
                AND r.codigo = 'PROFESOR'
                AND r.nombres = h.profesor
                AND r.activo = 1
          )

        ORDER BY hora
    """
    return db.fetch_df(query, (hoy, hora_actual, hoy, dia_semana, hora_actual, hoy))

def contar_asistencias_pendientes():
    pendientes = obtener_asistencias_pendientes()
    return len(pendientes)

def _asistencia_key(row):
    raw = f"{row['tipo']}_{row['id']}_{row['fecha']}_{row['hora']}_{row['laboratorio']}"
    return "".join(ch if ch.isalnum() else "_" for ch in raw)


def _registrar_estado_binario(row, estado):
    """Única ruta de guardado para los dos estados permitidos."""
    if estado not in ("Si", "No"):
        raise ValueError("Estado de asistencia no válido")
    if row["codigo"] == "PROFESOR":
        return res.registrar_asistencia_docente(
            row["fecha"], row["hora"], row["laboratorio"],
            row["nombres"], row["proyecto"], estado, None,
        )
    res.actualizar_asiste(row["id"], estado, None)
    return True


def mostrar_panel_asistencias_pendientes():
    pendientes = obtener_asistencias_pendientes()
    total_pendientes = len(pendientes)
    fecha_hoy = datetime.now().strftime("%d/%m/%Y")

    if not pendientes.empty:
        docentes_pendientes = len(pendientes[pendientes["tipo"] == "Docente"])
        estudiantes_pendientes = len(pendientes[pendientes["tipo"] == "Estudiante"])
    else:
        docentes_pendientes = 0
        estudiantes_pendientes = 0

    if "asistencias_panel_abierto" not in st.session_state:
        st.session_state.asistencias_panel_abierto = False

    if total_pendientes > 0:
        st.markdown(
            f"""
            <div style="background: #fff8d9; border: 1px solid #e3b41d; border-left: 6px solid #9f1d24; border-radius: 8px; padding: 12px 13px; box-shadow: 0 6px 16px rgba(43,31,20,0.045); margin: 0 0 0.75rem 0;">
                <h4 style="margin: 0; color: #731116; font-size: 1rem; line-height: 1.2;">Asistencias pendientes - Hoy ({fecha_hoy})</h4>
                <p style="margin: 8px 0 0 0; color: #725900; font-size: 0.92rem; line-height: 1.35;">
                    Total: <strong>{total_pendientes}</strong>
                    | Docentes: <strong>{docentes_pendientes}</strong>
                    | Estudiantes: <strong>{estudiantes_pendientes}</strong>
                    <span style="color:#856404;"> | Hora actual: <strong id="asistencias-live-clock">--:--</strong></span>
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"""
            <div style="background: #f5fbf6; border: 1px solid #c7dfc2; border-left: 6px solid #2f7d32; border-radius: 8px; padding: 9px 13px; box-shadow: 0 6px 16px rgba(43,31,20,0.04); margin: 0 0 0.45rem 0;">
                <h4 style="margin: 0; color: #1f5e24; font-size: 1rem; line-height: 1.2;">Todo al dia</h4>
                <p style="margin: 2px 0 0 0; color: #496049; font-size: 0.86rem; line-height: 1.35;">
                    No hay asistencias pendientes de marcar para hoy.
                    <span style="color:#496049;"> | Hora actual: <strong id="asistencias-live-clock">--:--</strong></span>
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.components.v1.html(
        """
        <script>
        (function () {
            const doc = window.parent.document;
            function updateClock() {
                const clock = doc.getElementById("asistencias-live-clock");
                if (!clock) return;
                const now = new Date();
                clock.textContent = now.toLocaleTimeString("es-CO", {
                    hour: "2-digit",
                    minute: "2-digit",
                    hour12: false
                });
            }
            updateClock();
            if (window.parent.__asistenciasClockTimer) {
                window.parent.clearInterval(window.parent.__asistenciasClockTimer);
            }
            window.parent.__asistenciasClockTimer = window.parent.setInterval(updateClock, 15000);
        })();
        </script>
        """,
        height=0,
        scrolling=False,
    )

    if total_pendientes > 0:
        with st.expander(
            f"Ver y marcar asistencias ({total_pendientes} pendientes)",
            expanded=st.session_state.asistencias_panel_abierto,
        ):
            st.caption("Marca cada asistencia. El panel permanecera abierto mientras trabajas.")
            registros = pendientes.reset_index(drop=True)
            if not registros.empty:
                modo_key = "asistencias_modo_seleccion_multiple"
                if modo_key not in st.session_state:
                    st.session_state[modo_key] = False
                modo_multiple = bool(st.session_state[modo_key])
                if st.button(
                    "Cancelar selección" if modo_multiple else "Seleccionar varios",
                    key="alternar_seleccion_multiple",
                    use_container_width=False,
                ):
                    if modo_multiple:
                        for estado_key in list(st.session_state.keys()):
                            if str(estado_key).startswith("asistencia_seleccionada_"):
                                st.session_state.pop(estado_key, None)
                        st.session_state["seleccionar_todos_docentes_pendientes"] = False
                    st.session_state[modo_key] = not modo_multiple
                    st.rerun()

                claves_docentes = {
                    indice: f"asistencia_seleccionada_{_asistencia_key(row)}"
                    for indice, row in registros.iterrows()
                }
                master_key = "seleccionar_todos_docentes_pendientes"

                # Los widgets solo pueden limpiarse antes de ser instanciados.
                # Las acciones masivas dejan esta señal para el siguiente rerun.
                if st.session_state.pop("asistencias_limpiar_seleccion", False):
                    for clave in claves_docentes.values():
                        st.session_state.pop(clave, None)
                    st.session_state.pop(master_key, None)

                def cambiar_seleccion_todos_docentes():
                    valor = bool(st.session_state.get(master_key, False))
                    for clave in claves_docentes.values():
                        st.session_state[clave] = valor

                if modo_multiple:
                    st.checkbox(
                        "Seleccionar todos los pendientes",
                        key=master_key,
                        on_change=cambiar_seleccion_todos_docentes,
                    )

                pagina_key = "asistencias_pagina"
                total_paginas = max(1, (len(registros) + 4) // 5)
                st.session_state[pagina_key] = min(max(1, st.session_state.get(pagina_key, 1)), total_paginas)
                pagina = st.session_state[pagina_key]
                inicio = (pagina - 1) * 5
                registros_pagina = registros.iloc[inicio:inicio + 5]

                anchos = [0.45, 0.9, 1, 2, 2, 0.9, 0.9] if modo_multiple else [0.9, 1, 2, 2, 0.9, 0.9]
                titulos = ("Seleccionar", "Hora", "Laboratorio", "Persona", "Tipo / Asignatura", "", "") if modo_multiple else ("Hora", "Laboratorio", "Persona", "Tipo / Asignatura", "", "")
                encabezado = st.columns(anchos)
                for columna, texto in zip(encabezado, titulos):
                    columna.markdown(f"**{texto}**")

                for indice, row in registros_pagina.iterrows():
                    columnas = st.columns(anchos)
                    desplazamiento = 1 if modo_multiple else 0
                    if modo_multiple:
                        with columnas[0]:
                            st.checkbox(
                                "Seleccionar",
                                key=claves_docentes[indice],
                                label_visibility="collapsed",
                            )
                    columnas[desplazamiento].write(row["hora"])
                    columnas[desplazamiento + 1].write(row["laboratorio"])
                    columnas[desplazamiento + 2].write(row["nombres"])
                    columnas[desplazamiento + 3].write(f"{row['tipo']} · {row['proyecto']}")
                    key_base = _asistencia_key(row)
                    with columnas[desplazamiento + 4]:
                        if st.button("Asistió", key=f"asi_{key_base}", use_container_width=True):
                            _registrar_estado_binario(row, "Si")
                            st.session_state.asistencias_panel_abierto = True
                            st.rerun()
                    with columnas[desplazamiento + 5]:
                        if st.button("No asistió", key=f"no_{key_base}", use_container_width=True):
                            _registrar_estado_binario(row, "No")
                            st.session_state.asistencias_panel_abierto = True
                            st.rerun()

                indices_seleccionados = [
                    indice for indice, clave in claves_docentes.items()
                    if st.session_state.get(clave, False)
                ]
                marcar_docentes_si = False
                marcar_docentes_no = False
                if modo_multiple:
                    st.caption(f"Registros seleccionados: {len(indices_seleccionados)}")
                    masivo_si_col, masivo_no_col = st.columns(2)
                    with masivo_si_col:
                        marcar_docentes_si = st.button("Seleccionados: Asistieron", use_container_width=True)
                    with masivo_no_col:
                        marcar_docentes_no = st.button("Seleccionados: No asistieron", use_container_width=True)

                if marcar_docentes_si or marcar_docentes_no:
                    if not indices_seleccionados:
                        st.warning("Selecciona al menos un registro.")
                    else:
                        estado_masivo = "Si" if marcar_docentes_si else "No"
                        for indice in indices_seleccionados:
                            row = registros.loc[indice]
                            _registrar_estado_binario(row, estado_masivo)
                        st.session_state.asistencias_limpiar_seleccion = True
                        st.session_state.asistencias_panel_abierto = True
                        st.success(f"Asistencia actualizada para {len(indices_seleccionados)} registro(s).")
                        st.rerun()
                nav_anterior, nav_info, nav_siguiente = st.columns([1, 2, 1])
                with nav_anterior:
                    if st.button("Anterior", key="asistencias_anterior", disabled=pagina == 1, use_container_width=True):
                        st.session_state[pagina_key] -= 1
                        st.rerun()
                nav_info.markdown(
                    f"<div style='text-align:center;padding:.55rem;color:#5f6368'>Mostrar registros {inicio + 1}–{min(inicio + 5, len(registros))} de {len(registros)}</div>",
                    unsafe_allow_html=True,
                )
                with nav_siguiente:
                    if st.button("Siguiente", key="asistencias_siguiente", disabled=pagina == total_paginas, use_container_width=True):
                        st.session_state[pagina_key] += 1
                        st.rerun()
    else:
        st.session_state.asistencias_panel_abierto = False
        st.caption("Sin pendientes hoy")
