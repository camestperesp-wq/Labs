"""Importación transaccional; identifica reportes por estudiante, día y detalle."""
import io
import re
import unicodedata
import zipfile
import pandas as pd
import database as db


def normalizar(value):
    value = unicodedata.normalize("NFKD", str(value)).upper()
    return re.sub(r"[^A-Z0-9]", "", "".join(c for c in value if not unicodedata.combining(c)))


def texto(value):
    return "" if pd.isna(value) else str(value).strip()


def fecha(value, optional=False):
    if not texto(value):
        if optional:
            return None
        raise ValueError("La fecha de sanción es obligatoria.")
    try:
        if isinstance(value, (int, float)):
            result = pd.to_datetime(value, unit="D", origin="1899-12-30")
        else:
            raw = texto(value)
            result = pd.to_datetime(value, dayfirst=not bool(re.match(r"^\d{4}-", raw)), errors="raise")
    except (ValueError, TypeError, OverflowError):
        raise ValueError("Fecha invalida.") from None
    if pd.isna(result):
        raise ValueError("Fecha inválida.")
    return result.strftime("%Y-%m-%d")


COLUMNS = {
    "codigo": "CODIGO", "nombres": "NOMBREDELESTUDIANTE", "proyecto": "PROYECTOCURRICULAR",
    "correo": "CORREOUSUARIO", "fecha": "FECHASANCION", "cancelacion": "FECHACANCELACION",
    "motivo": "DESCRIPCIONDELREPORTE", "tecnico": "TECNICOQUEREGISTRALASANCION",
    "sancion": "DESCRIPCIONDELASANCION", "pago": "PAGO", "observaciones": "OBSERVACIONES",
}


def leer_tabla_multas(contenido):
    # Excel Strict utiliza otros espacios de nombres. Normalizar una copia en
    # memoria permite leer también esos libros sin modificar el original.
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(contenido)) as source, zipfile.ZipFile(output, "w") as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename.endswith((".xml", ".rels")):
                data = data.replace(b"http://purl.oclc.org/ooxml/spreadsheetml/main",
                                    b"http://schemas.openxmlformats.org/spreadsheetml/2006/main")
                data = data.replace(b"http://purl.oclc.org/ooxml/officeDocument/relationships",
                                    b"http://schemas.openxmlformats.org/officeDocument/2006/relationships")
            target.writestr(item, data)
    with pd.ExcelFile(io.BytesIO(output.getvalue())) as book:
        sheet = next((s for s in book.sheet_names if normalizar(s) == "DEUDORES"), book.sheet_names[0])
        preview = pd.read_excel(book, sheet_name=sheet, header=None, nrows=20, dtype=object)
        header = next((i for i, row in preview.iterrows()
                       if "CODIGO" in [normalizar(v) for v in row]), None)
        if header is None:
            raise ValueError("No se encontró el encabezado Código en las primeras 20 filas.")
        return pd.read_excel(book, sheet_name=sheet, header=header, dtype=object), header


def importar_multas_excel(archivo):
    contenido = archivo.getvalue() if hasattr(archivo, "getvalue") else archivo.read()
    tabla, header = leer_tabla_multas(contenido)
    headers = [normalizar(c) for c in tabla.columns]
    headers = [{"NOMBRESYAPELLIDOS": "NOMBREDELESTUDIANTE",
                "FECHACANCELACI": "FECHACANCELACION"}.get(c, c) for c in headers]
    if len(headers) != len(set(headers)):
        raise ValueError("Hay columnas repetidas en el archivo.")
    tabla.columns = headers
    if "CODIGO" not in headers or headers[headers.index("CODIGO") + 1:headers.index("CODIGO") + 2] != ["NOMBREDELESTUDIANTE"]:
        raise ValueError('El Excel debe incluir "Nombre del estudiante" inmediatamente después de "Código".')
    # Algunos libros históricos contienen el encabezado truncado.
    tabla.rename(columns={"FECHACANCELACI": "FECHACANCELACION"}, inplace=True)
    missing = set(COLUMNS.values()) - set(tabla.columns)
    if missing:
        raise ValueError("Faltan columnas: " + ", ".join(sorted(missing)))
    records = {}
    repeated = 0
    omitted = 0
    for index, row in tabla.dropna(how="all", subset=list(COLUMNS.values())).iterrows():
        try:
            values = {key: row[column] for key, column in COLUMNS.items()}
            code = texto(values["codigo"])
            if isinstance(values["codigo"], (int, float)):
                if float(values["codigo"]) != int(values["codigo"]):
                    raise ValueError("El código no puede contener decimales.")
                code = str(int(values["codigo"]))
            if not code:
                raise ValueError("El código es obligatorio.")
            if not texto(values["nombres"]):
                with db.get_connection() as conn:
                    estudiante = conn.execute(
                        "SELECT nombres FROM estudiantes WHERE codigo=?", (code,)
                    ).fetchone()
                if not estudiante or not texto(estudiante[0]):
                    omitted += 1
                    continue
                values["nombres"] = estudiante[0]
            payment = normalizar(texto(values["pago"]))
            if payment not in ("", "NO", "SI", "PAGADO", "PENDIENTE", "0", "1"):
                raise ValueError("PAGO debe ser SI o NO.")
            values = {key: texto(value) for key, value in values.items() if key not in ("fecha", "cancelacion")}
            values.update(codigo=code, fecha=fecha(row[COLUMNS["fecha"]]),
                          cancelacion=fecha(row[COLUMNS["cancelacion"]], optional=True),
                          pago="SI" if payment in ("SI", "PAGADO", "1") else "NO")
            key = (code, values["fecha"], values["motivo"], values["sancion"], values["tecnico"])
            if key in records:
                if records[key] != values:
                    raise ValueError("Dos filas del mismo reporte (código, fecha, descripción, sanción y técnico) tienen datos diferentes. Revise el pago y los demás campos.")
                repeated += 1
            records[key] = values
        except (ValueError, TypeError, OverflowError) as error:
            raise ValueError(f"Fila {index + header + 2}: {error}") from error
    if not records:
        if omitted:
            return {"insertadas": 0, "actualizadas": 0, "repetidas": repeated, "omitidas_sin_nombre": omitted}
        raise ValueError("El archivo no contiene sanciones.")
    inserted = updated = 0
    with db.get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        for (code, day, motivo, sancion, tecnico), values in records.items():
            matches = []
            for existing_id, existing_date, existing_motivo, existing_sancion, existing_tecnico in conn.execute(
                    "SELECT id,fecha_multa,motivo,sancion,tecnico_asigna FROM multas WHERE codigo_estudiante=?", (code,)):
                try:
                    if (fecha(existing_date) == day and
                            (texto(existing_motivo), texto(existing_sancion), texto(existing_tecnico)) ==
                            (motivo, sancion, tecnico)):
                        matches.append(existing_id)
                except (ValueError, TypeError):
                    raise ValueError(f"El estudiante {code} tiene una fecha histórica inválida; corríjala antes de importar.")
            conn.execute("""INSERT INTO estudiantes(codigo,nombres,proyecto) VALUES (?,?,?)
                         ON CONFLICT(codigo) DO UPDATE SET nombres=excluded.nombres,proyecto=excluded.proyecto""",
                         (code, values["nombres"], values["proyecto"]))
            params = (code, day, values["cancelacion"], values["motivo"], values["sancion"],
                      values["tecnico"], values["pago"], values["correo"], values["observaciones"])
            if matches:
                for match_id in matches:
                    conn.execute("""UPDATE multas SET codigo_estudiante=?,fecha_multa=?,fecha_pago=?,motivo=?,
                                 sancion=?,tecnico_asigna=?,pagado=?,correo_usuario=?,observaciones=? WHERE id=?""",
                                 params + (match_id,))
                updated += len(matches)
            else:
                conn.execute("""INSERT INTO multas(codigo_estudiante,fecha_multa,fecha_pago,motivo,sancion,
                             tecnico_asigna,pagado,correo_usuario,observaciones) VALUES (?,?,?,?,?,?,?,?,?)""", params)
                inserted += 1
    db.clear_cache()
    # Los préstamos también consultan el estado de multas.
    from prestamos_pasillos import _invalidar_cache_lecturas
    _invalidar_cache_lecturas()
    return {"insertadas": inserted, "actualizadas": updated, "repetidas": repeated, "omitidas_sin_nombre": omitted}


def plantilla_multas_excel():
    """Plantilla legible por el importador, sin títulos ni filas adicionales."""
    columnas = ["CÓDIGO", "NOMBRE DEL ESTUDIANTE", "PROYECTO CURRICULAR", "CORREO USUARIO",
                "FECHA SANCIÓN", "FECHA CANCELACIÓN", "DESCRIPCIÓN DEL REPORTE",
                "TÉCNICO QUE REGISTRA LA SANCIÓN", "DESCRIPCIÓN DE LA SANCIÓN", "PAGO", "OBSERVACIONES"]
    output = io.BytesIO()
    pd.DataFrame(columns=columnas).to_excel(output, index=False)
    return output.getvalue()
