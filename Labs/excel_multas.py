"""Importación transaccional de sanciones; clave: código y día de sanción."""
import io
import re
import unicodedata
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
    if isinstance(value, (int, float)):
        result = pd.to_datetime(value, unit="D", origin="1899-12-30")
    else:
        raw = texto(value)
        result = pd.to_datetime(value, dayfirst=not bool(re.match(r"^\d{4}-", raw)), errors="raise")
    if pd.isna(result):
        raise ValueError("Fecha inválida.")
    return result.strftime("%Y-%m-%d")


COLUMNS = {
    "codigo": "CODIGO", "nombres": "NOMBREDELESTUDIANTE", "proyecto": "PROYECTOCURRICULAR",
    "correo": "CORREOUSUARIO", "fecha": "FECHASANCION", "cancelacion": "FECHACANCELACION",
    "motivo": "DESCRIPCIONDELREPORTE", "tecnico": "TECNICOQUEREGISTRALASANCION",
    "sancion": "DESCRIPCIONDELASANCION", "pago": "PAGO", "observaciones": "OBSERVACIONES",
}


def importar_multas_excel(archivo):
    contenido = archivo.getvalue() if hasattr(archivo, "getvalue") else archivo.read()
    tabla = pd.read_excel(io.BytesIO(contenido), dtype=object)
    headers = [normalizar(c) for c in tabla.columns]
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
    for index, row in tabla.dropna(how="all").iterrows():
        try:
            values = {key: row[column] for key, column in COLUMNS.items()}
            code = texto(values["codigo"])
            if isinstance(values["codigo"], (int, float)):
                if float(values["codigo"]) != int(values["codigo"]):
                    raise ValueError("El código no puede contener decimales.")
                code = str(int(values["codigo"]))
            if not code or not texto(values["nombres"]):
                raise ValueError("Código y nombre son obligatorios.")
            payment = normalizar(texto(values["pago"]))
            if payment not in ("", "NO", "SI", "PAGADO", "PENDIENTE", "0", "1"):
                raise ValueError("PAGO debe ser SI o NO.")
            values = {key: texto(value) for key, value in values.items() if key not in ("fecha", "cancelacion")}
            values.update(codigo=code, fecha=fecha(row[COLUMNS["fecha"]]),
                          cancelacion=fecha(row[COLUMNS["cancelacion"]], optional=True),
                          pago="SI" if payment in ("SI", "PAGADO", "1") else "NO")
            key = (code, values["fecha"])
            if key in records:
                if records[key] != values:
                    raise ValueError("Dos filas con el mismo código y fecha tienen datos diferentes.")
                repeated += 1
            records[key] = values
        except (ValueError, TypeError, OverflowError) as error:
            raise ValueError(f"Fila {index + 2}: {error}") from error
    if not records:
        raise ValueError("El archivo no contiene sanciones.")
    inserted = updated = 0
    with db.get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        for (code, day), values in records.items():
            matches = []
            for existing_id, existing_date in conn.execute(
                    "SELECT id,fecha_multa FROM multas WHERE codigo_estudiante=?", (code,)):
                try:
                    if fecha(existing_date) == day:
                        matches.append(existing_id)
                except (ValueError, TypeError):
                    raise ValueError(f"El estudiante {code} tiene una fecha histórica inválida; corríjala antes de importar.")
            if len(matches) > 1:
                raise ValueError(f"Ya existen varias multas de {code} el {day}. Revise esos reportes antes de importar.")
            conn.execute("""INSERT INTO estudiantes(codigo,nombres,proyecto) VALUES (?,?,?)
                         ON CONFLICT(codigo) DO UPDATE SET nombres=excluded.nombres,proyecto=excluded.proyecto""",
                         (code, values["nombres"], values["proyecto"]))
            params = (code, day, values["cancelacion"], values["motivo"], values["sancion"],
                      values["tecnico"], values["pago"], values["correo"], values["observaciones"])
            if matches:
                conn.execute("""UPDATE multas SET codigo_estudiante=?,fecha_multa=?,fecha_pago=?,motivo=?,
                             sancion=?,tecnico_asigna=?,pagado=?,correo_usuario=?,observaciones=? WHERE id=?""",
                             params + (matches[0],))
                updated += 1
            else:
                conn.execute("""INSERT INTO multas(codigo_estudiante,fecha_multa,fecha_pago,motivo,sancion,
                             tecnico_asigna,pagado,correo_usuario,observaciones) VALUES (?,?,?,?,?,?,?,?,?)""", params)
                inserted += 1
    db.clear_cache()
    # Los préstamos también consultan el estado de multas.
    from prestamos_pasillos import _invalidar_cache_lecturas
    _invalidar_cache_lecturas()
    return {"insertadas": inserted, "actualizadas": updated, "repetidas": repeated}


def plantilla_multas_excel():
    """Plantilla legible por el importador, sin títulos ni filas adicionales."""
    columnas = ["CÓDIGO", "NOMBRE DEL ESTUDIANTE", "PROYECTO CURRICULAR", "CORREO USUARIO",
                "FECHA SANCIÓN", "FECHA CANCELACIÓN", "DESCRIPCIÓN DEL REPORTE",
                "TÉCNICO QUE REGISTRA LA SANCIÓN", "DESCRIPCIÓN DE LA SANCIÓN", "PAGO", "OBSERVACIONES"]
    output = io.BytesIO()
    pd.DataFrame(columns=columnas).to_excel(output, index=False)
    return output.getvalue()
