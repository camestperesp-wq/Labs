"""Vista Streamlit del módulo Préstamos de Pasillos."""

from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

from constants import es_tecnico_valido
from exportaciones import crear_excel_institucional
import prestamos_pasillos as prestamos


def _mostrar_metricas_globales():
    inventario = prestamos.obtener_equipos()
    disponibles = int((inventario["estado"] == "Disponible").sum()) if not inventario.empty else 0
    total_col, disponible_col, prestado_col = st.columns(3)
    total_col.metric("Total en inventario", len(inventario))
    disponible_col.metric("Disponibles", disponibles)
    prestado_col.metric("Actualmente prestados", len(inventario) - disponibles)


@st.fragment
def _mostrar_inventario():
    st.markdown("#### Inventario de equipos")
    mensaje = st.session_state.pop("pasillos_flash_inventario", None)
    if mensaje:
        st.success(mensaje)
    inventario = prestamos.obtener_equipos()
    carga_col, registro_col = st.columns(2, gap="large")
    with carga_col:
        with st.container(border=True):
            st.markdown("##### Cargar inventario desde Excel")
            st.caption("Columnas: Número de placa (puede estar vacía), Nombre del equipo y Número interno.")
            archivo = st.file_uploader("Archivo Excel", type=["xlsx"], key="pasillos_inventario_excel")
            if st.button("Cargar inventario", key="pasillos_cargar_excel", disabled=archivo is None):
                try:
                    cantidad = prestamos.cargar_inventario_excel(archivo)
                    st.session_state.pasillos_flash_inventario = f"{cantidad} equipo(s) procesado(s)."
                    st.rerun(scope="fragment")
                except (ValueError, TypeError) as error:
                    st.error(str(error))
                except Exception as error:
                    st.error(f"No fue posible cargar el inventario: {error}")

    with registro_col:
        with st.container(border=True):
            st.markdown("##### Registrar nuevo equipo")
            with st.form("pasillos_registrar_equipo", clear_on_submit=True):
                placa = st.text_input("Número de placa", help="Opcional: puede quedar en blanco.")
                nombre = st.text_input("Nombre del equipo *")
                numero_interno = st.text_input("Número interno *")
                registrar = st.form_submit_button("Registrar equipo", use_container_width=True)
            if registrar:
                try:
                    prestamos.registrar_equipo(placa, nombre, numero_interno)
                    st.session_state.pasillos_flash_inventario = "Equipo registrado correctamente."
                    st.rerun(scope="fragment")
                except ValueError as error:
                    st.error(str(error))

    if inventario.empty:
        st.info("Aún no hay equipos registrados.")
    else:
        st.dataframe(
            inventario.rename(columns={
                "placa": "Número de placa",
                "nombre": "Equipo",
                "numero_interno": "Número interno",
                "estado": "Estado",
            })[["Número de placa", "Equipo", "Número interno", "Estado"]],
            hide_index=True,
            use_container_width=True,
        )
        with st.expander("Eliminar equipo"):
            opciones = {
                int(fila["id"]): f"{fila['nombre']} · Interno {fila['numero_interno']} · {fila['estado']}"
                for _, fila in inventario.iterrows()
            }
            equipo_id = st.selectbox("Equipo", list(opciones), format_func=lambda valor: opciones[valor])
            estado = inventario.loc[inventario["id"] == equipo_id, "estado"].iloc[0]
            if st.button("Eliminar del inventario", disabled=estado == "Prestado"):
                try:
                    prestamos.eliminar_equipo(equipo_id)
                    st.session_state.pasillos_flash_inventario = "Equipo eliminado del inventario."
                    st.rerun(scope="fragment")
                except ValueError as error:
                    st.error(str(error))


@st.fragment
def _mostrar_nuevo_prestamo():
    st.markdown("#### Registrar salida")
    mensaje = st.session_state.pop("pasillos_flash_salida", None)
    if mensaje:
        st.success(mensaje)

    # Cambiar la versión crea widgets nuevos después de una salida exitosa. Las
    # claves anteriores se eliminan al inicio del siguiente render, cuando ya no
    # están instanciadas, evitando errores de session_state.
    claves_anteriores = st.session_state.pop("pasillos_limpiar_salida", [])
    for clave in claves_anteriores:
        st.session_state.pop(clave, None)
    version = int(st.session_state.get("pasillos_salida_version", 0))
    codigo_key = f"pasillos_codigo_solicitante_{version}"
    equipos_key = f"pasillos_equipos_{version}"
    tecnico_key = f"pasillos_tecnico_entrega_{version}"
    observaciones_key = f"pasillos_observaciones_salida_{version}"

    disponibles = prestamos.obtener_equipos(solo_disponibles=True)
    if disponibles.empty:
        st.info("No hay equipos disponibles para prestar.")
        return

    etiquetas = {
        int(fila["id"]): (
            f"{fila['nombre']} · "
            f"{'Placa ' + fila['placa'] + ' · ' if fila['placa'] else ''}"
            f"Interno {fila['numero_interno']}"
        )
        for _, fila in disponibles.iterrows()
    }
    codigo_solicitante = st.text_input(
        "Código del solicitante *",
        key=codigo_key,
        placeholder="Ingresa el código institucional",
    ).strip()
    solicitante = prestamos.obtener_solicitante(codigo_solicitante)
    if codigo_solicitante and solicitante:
        st.markdown(f"**Solicitante:** {solicitante['nombres']}")
        if solicitante.get("proyecto"):
            st.markdown(f"Proyecto curricular: {solicitante['proyecto']}")
    elif codigo_solicitante:
        st.markdown("**Código no encontrado.** Puedes continuar con el registro de la salida.")

    alertas = prestamos.obtener_alertas_bloqueo(codigo_solicitante)
    if alertas:
        st.error("ALERTA CRÍTICA: el estudiante tiene incumplimientos pendientes.")
        for alerta in alertas:
            st.markdown(f"- {alerta}")

    tecnicos = ["Seleccionar", *prestamos.obtener_tecnicos()]
    equipos_ids = st.multiselect(
        "Equipos *", options=list(etiquetas),
        format_func=lambda equipo_id: etiquetas[equipo_id],
        help="Puedes seleccionar uno o varios equipos en la misma salida.", key=equipos_key,
    )
    tecnico = st.selectbox("Técnico responsable de la entrega *", tecnicos, key=tecnico_key)
    observaciones = st.text_area("Observaciones de salida", height=100, key=observaciones_key)
    autorizacion = False
    autorizacion_key = f"pasillos_autorizacion_{version}"
    if alertas:
        autorizacion = st.checkbox(
            "Autorizo excepcionalmente este préstamo bajo mi responsabilidad",
            key=autorizacion_key,
        )
    bloqueado = bool(alertas) and not (autorizacion and es_tecnico_valido(tecnico))
    guardar = st.button("Registrar Salida", use_container_width=True, disabled=bloqueado)

    if guardar:
        try:
            if not es_tecnico_valido(tecnico):
                raise ValueError("Selecciona el técnico responsable de la entrega.")
            prestamo_id = prestamos.crear_prestamo(equipos_ids, codigo_solicitante, tecnico, observaciones)
            st.session_state.pasillos_flash_salida = (
                "Salida registrada correctamente. Fecha y hora guardadas automáticamente."
            )
            st.session_state.pasillos_limpiar_salida = [
                codigo_key, equipos_key, tecnico_key, observaciones_key, autorizacion_key
            ]
            st.session_state.pasillos_salida_version = version + 1
            st.rerun(scope="fragment")
        except ValueError as error:
            st.error(str(error))


@st.fragment
def _mostrar_devoluciones():
    st.markdown("#### Registrar devolución")
    mensaje = st.session_state.pop("pasillos_flash_devolucion", None)
    if mensaje:
        st.success(mensaje)
    activos = prestamos.obtener_prestamos("PRESTADO")
    if activos.empty:
        st.info("No hay préstamos activos.")
        return
    tecnicos = ["Seleccionar", *prestamos.obtener_tecnicos()]
    ahora = datetime.now()
    for _, detalle in activos.iterrows():
        prestamo_id = int(detalle["id"])
        limite = pd.to_datetime(detalle.get("limite_fpga"), errors="coerce")
        salida = pd.to_datetime(detalle["fecha_salida"])
        es_fpga = pd.notna(limite)
        limite_gracia = (
            limite.to_pydatetime() + timedelta(minutes=prestamos.TOLERANCIA_FPGA_MINUTOS)
            if es_fpga else None
        )
        fpga_vencida = es_fpga and ahora > limite_gracia
        dia_vencido = ahora.date() > salida.date()
        titulo = f"{detalle['solicitante_nombre']} ({detalle['solicitante']}) · {detalle['cantidad_equipos']} equipo(s)"
        destacado = str(st.session_state.get("pasillos_prestamo_destacado", "")) == str(prestamo_id)
        with st.expander(titulo, expanded=destacado):
            st.write(f"**Nombre:** {detalle['solicitante_nombre']}")
            st.write(f"**Código:** {detalle['solicitante']}")
            st.write(f"**Equipos:** {detalle['equipos']}")
            st.write(f"**Técnico que entregó:** {detalle['tecnico_entrega']}")
            st.write(f"**Fecha y hora de salida:** {detalle['fecha_salida']}")
            if es_fpga:
                st.write(
                    f"**Límite FPGA:** {detalle['limite_fpga']} · "
                    f"tolerancia hasta {limite_gracia.strftime('%Y-%m-%d %H:%M:%S')}"
                )
            if fpga_vencida:
                retraso = int((ahora - limite_gracia).total_seconds() // 60)
                st.error(f"Tiempo FPGA vencido por {prestamos._formatear_retraso(retraso)}.")
            if dia_vencido:
                st.error("El préstamo no fue devuelto el mismo día.")
            if not fpga_vencida and not dia_vencido:
                st.success("Sin alertas de tiempo vencido.")

            with st.form(f"pasillos_devolucion_{prestamo_id}"):
                receptor = st.selectbox("Técnico responsable *", tecnicos)
                detalle_multa = st.text_area(
                    "Registro de la multa por retraso *",
                    disabled=not fpga_vencida,
                    help="La multa no es monetaria y debe ser documentada por el técnico.",
                )
                observaciones = st.text_area("Observaciones de entrada", height=80)
                acciones = st.columns(2) if es_fpga else [st.container()]
                devolver = acciones[0].form_submit_button("Registrar devolución", use_container_width=True)
                renovar = es_fpga and acciones[1].form_submit_button("Renovar préstamo", use_container_width=True)
            if devolver or renovar:
                if not es_tecnico_valido(receptor):
                    st.error("Selecciona el técnico responsable.")
                else:
                    try:
                        if renovar:
                            prestamos.renovar_prestamo_fpga(
                                prestamo_id, receptor, detalle_multa=detalle_multa
                            )
                            st.session_state.pasillos_flash_devolucion = "Préstamo FPGA renovado por dos horas."
                        else:
                            prestamos.registrar_devolucion(
                                prestamo_id, receptor, observaciones,
                                detalle_multa=detalle_multa,
                            )
                            st.session_state.pasillos_flash_devolucion = "Devolución registrada correctamente."
                        st.rerun(scope="fragment")
                    except ValueError as error:
                        st.error(str(error))


@st.fragment
def _mostrar_historial():
    st.markdown("#### Historial de préstamos")
    filtro = st.selectbox(
        "Estado",
        ["Todos", "Prestados", "Devueltos"],
        key="pasillos_historial_estado",
    )
    estado = {"Prestados": "PRESTADO", "Devueltos": "DEVUELTO"}.get(filtro)
    fecha_col, hasta_col = st.columns(2)
    hoy = datetime.now().date()
    desde = fecha_col.date_input("Desde", hoy - timedelta(days=30), key="pasillos_historial_desde")
    hasta = hasta_col.date_input("Hasta", hoy, key="pasillos_historial_hasta")
    if desde > hasta:
        st.error("La fecha inicial no puede ser posterior a la fecha final.")
        return
    historial = prestamos.obtener_prestamos(estado)
    if not historial.empty:
        fechas = pd.to_datetime(historial["fecha_salida"], errors="coerce").dt.date
        historial = historial[(fechas >= desde) & (fechas <= hasta)].copy()
    if historial.empty:
        st.info("No hay préstamos en el rango seleccionado.")
        return
    vista = historial.rename(columns={
        "solicitante": "Código",
        "solicitante_nombre": "Solicitante",
        "equipos": "Equipos",
        "tecnico_entrega": "Técnico de entrega",
        "fecha_salida": "Salida",
        "observaciones_salida": "Observaciones de salida",
        "receptor": "Receptor",
        "fecha_retorno": "Retorno",
        "observaciones_entrada": "Observaciones de entrada",
        "estado": "Estado",
        "multas_asociadas": "Multas asociadas",
    })
    st.dataframe(
        vista[[
            "Código", "Solicitante", "Equipos", "Técnico de entrega", "Salida",
            "Observaciones de salida", "Receptor", "Retorno",
            "Observaciones de entrada", "Estado",
        ]],
        hide_index=True,
        use_container_width=True,
    )
    columnas_exportar = [
        "Código", "Solicitante", "Equipos", "Técnico de entrega", "Salida",
        "Observaciones de salida", "Receptor", "Retorno",
        "Observaciones de entrada", "Estado", "Multas asociadas",
    ]
    excel = crear_excel_institucional(
        vista[columnas_exportar],
        "Historial de préstamos de pasillos",
        "Trazabilidad de entrega y devolución de equipos",
        [
            ("Periodo", f"{desde.strftime('%d/%m/%Y')} al {hasta.strftime('%d/%m/%Y')}"),
            ("Estado incluido", filtro),
            ("Transacciones", len(vista)),
        ],
        nombre_hoja="Prestamos",
    )
    st.download_button(
        "Descargar historial en Excel",
        data=excel,
        file_name="historial_prestamos_pasillos.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="pasillos_descargar_historial",
    )


def mostrar_prestamos_pasillos():
    st.markdown(
        """<style>
        .labs-section-title { margin-bottom: .35rem !important; }
        </style>""",
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <div class="labs-section-title">
            <h2>Préstamos de Pasillos</h2>
            <p>Inventario, entrega multi-equipo, devoluciones y trazabilidad.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    prestamos.sincronizar_incumplimientos()
    _mostrar_metricas_globales()
    opciones_seccion = [
        "Registrar Préstamo", "Devoluciones", "Inventario de Equipos",
        "Reportes e Historial",
    ]
    if st.session_state.get("pasillos_seccion") not in (None, *opciones_seccion):
        st.session_state.pasillos_seccion = "Registrar Préstamo"
    seccion = st.segmented_control(
        "Sección",
        opciones_seccion,
        default="Registrar Préstamo",
        key="pasillos_seccion",
    )
    if seccion == "Registrar Préstamo":
        _mostrar_nuevo_prestamo()
    elif seccion == "Devoluciones":
        _mostrar_devoluciones()
    elif seccion == "Inventario de Equipos":
        _mostrar_inventario()
    else:
        _mostrar_historial()
