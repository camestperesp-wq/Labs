# Puesta en marcha

Instalar las dependencias con `python -m pip install -r requirements.txt`.
La entrada protegida requiere Streamlit 1.62.0 (incluye el servidor ASGI).

Crear cada cuenta con `python auth.py`. El comando solicita usuario y contraseña
sin mostrarla. No hay usuarios ni contraseñas predeterminados. Ejecutar de nuevo
para cambiar una contraseña y revocar las sesiones de esa cuenta.

Iniciar con `python -m streamlit run server.py`. Para uso local, abrir
`http://localhost:8501`. En la red institucional, publicar esta entrada mediante
HTTPS y mantener el puerto interno limitado al proxy o al equipo local. Configurar
el proxy para transmitir WebSocket y el esquema HTTPS; confiar cabeceras reenviadas
únicamente desde la dirección del proxy. No publicar una segunda instancia de
`streamlit run app.py`: esa entrada bloquea los datos pero no ofrece las rutas de login.

Las cookies son HttpOnly, SameSite=Strict y Secure sobre HTTPS. El login remoto
por HTTP se rechaza. La sesión vence exactamente 86 400 segundos después del login,
sin renovación deslizante ni vencimiento por inactividad. Se conserva al recargar
o reiniciar el navegador dentro de ese plazo. Cerrar sesión revoca el token; cambiar
la contraseña revoca todos los tokens del usuario. Los WebSocket se cierran al
vencer y vuelven a validar la sesión en cada mensaje. Diez intentos fallidos por
usuario o dirección bloquean el acceso durante el resto de una ventana de 15 minutos.

Proteger `auth.db` con los permisos del usuario que ejecuta el servicio: contiene
hashes de contraseñas y tokens, nunca sus valores originales. No está versionado.
Respaldar `mi_agenda.db` antes de actualizar. Las pruebas usan bases temporales.

# Excel de multas

En **Deudores → Importar multas desde Excel**, cargar `.xlsx` con:

`CÓDIGO`, `NOMBRE DEL ESTUDIANTE`, `PROYECTO CURRICULAR`, `CORREO USUARIO`,
`FECHA SANCIÓN`, `FECHA CANCELACIÓN`, `DESCRIPCIÓN DEL REPORTE`,
`TÉCNICO QUE REGISTRA LA SANCIÓN`, `DESCRIPCIÓN DE LA SANCIÓN`, `PAGO`, `OBSERVACIONES`.

Se aceptan encabezados sin tildes y `FECHA CANCELACI[ÓN]` o `FECHA CANCELACI`.
La plantilla se descarga desde la misma sección; Nombre del Estudiante va
inmediatamente después de Código. Este nombre de columna y su posición son obligatorios.
La columna Correo usuario debe existir, pero sus valores pueden quedar vacíos.
Usar fechas de Excel, `DD/MM/AAAA` o `AAAA-MM-DD`, y PAGO `SI`/`NO`.
Guardar los códigos como texto en Excel para conservar ceros iniciales.
Código y día de sanción identifican el reporte; la reimportación actualiza sus
campos y los datos del estudiante. Las filas idénticas se omiten; las contradictorias
se rechazan. Si hay varios reportes históricos con esa clave, se detiene toda la
carga para revisarlos; no se borran registros automáticamente. Correo y observaciones
se conservan en la multa. `excel_multas.importar_multas_excel` es la función de backend.

# Excel de pasillos

Usar la carga de inventario existente con `Nombre del equipo`, `Número interno`
y, opcionalmente, `Número de placa`. También se admite `ID_Elemento` o
`Código_Inventario` como número interno. Cada fila representa una unidad física,
como en el modelo actual: las existencias son los equipos disponibles, descontando
los préstamos abiertos. No hay una columna de cantidad agregada.

Se actualiza por placa o número interno y se preserva el ID de base de datos y sus
préstamos. Si ambos identificadores señalan equipos diferentes, se rechaza toda
la carga. Repetir un equipo sin placa tampoco crea duplicados.
Backend: `prestamos_pasillos.cargar_inventario_excel`.

# Verificación

`python -m unittest test_importaciones_auth test_prestamos_pasillos`

Comprobar en navegador el ciclo lunes → otro día → lunes en Horario General:
únicamente el clic derecho abre el menú de edición del espacio seleccionado.
No hay botones de edición sobre las celdas ni panel adicional para elegir laboratorio y hora.
El calendario conserva el ancho anterior, con filas más altas y encabezados fijos.
Los nombres usan letra más pequeña: docente en préstamos docentes, monitor en
prácticas libres, y ambos en clases normales. El nombre del docente en los formularios
de préstamo se escribe en un campo de texto libre.

La razón de una multa se elige exclusivamente entre los 13 conceptos institucionales
suministrados y **OTRAS**, que habilita un texto personalizado. Se guarda el concepto
completo y se exporta en **Detalle de la multa**. Los textos personalizados no se agregan
al desplegable. El reporte detallado filtra por fecha de multa, con ambos
extremos incluidos, y puede descargarse aunque todas las multas estén pagadas.
La verificación de paz y salvo muestra fecha y concepto de cada multa activa.
