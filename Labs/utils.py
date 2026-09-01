# utils.py
from datetime import datetime
import re
import unicodedata


def normalizar_texto(valor):
    """Devuelve texto Unicode NFC limpio y repara mojibake UTF-8 frecuente."""
    if valor is None:
        return ""
    texto = str(valor)
    if any(marca in texto for marca in ("Ã", "Â", "â€", "ðŸ")):
        try:
            texto = texto.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    texto = unicodedata.normalize("NFC", texto)
    texto = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", texto)
    return re.sub(r"\s+", " ", texto).strip()

import database as db


def generar_multa(lab, fecha, hora):
    fecha_formateada = datetime.strptime(fecha, "%Y-%m-%d").strftime("%d/%m/%Y")
    return f"No asistió Lab {lab} - {fecha_formateada} {hora}"


def actualizar_reservas_vencidas():
    hoy = datetime.now().date().strftime("%Y-%m-%d")
    fecha_hoy = hoy

    with db.get_connection() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT id, laboratorio, fecha, hora, codigo
            FROM reservas
            WHERE fecha < ?
            AND activo = 1
            AND (asiste IS NULL OR asiste = '')
        """, (hoy,))
        rows = c.fetchall()

        for id_res, lab, fecha, hora, codigo in rows:
            if codigo == "PROFESOR":
                c.execute("UPDATE reservas SET asiste = 'No' WHERE id = ?", (id_res,))
                continue

            c.execute("SELECT nombres FROM estudiantes WHERE codigo = ?", (codigo,))
            estudiante = c.fetchone()
            if estudiante:
                motivo = f"No asistió a {lab} - {fecha} {hora}"
                c.execute("""
                    INSERT INTO multas
                    (codigo_estudiante, fecha_multa, motivo, sancion, tecnico_asigna, pagado)
                    VALUES (?, ?, ?, ?, ?, 'NO')
                """, (codigo, fecha_hoy, motivo, "", "Sistema (vencida)"))

            c.execute("UPDATE reservas SET asiste = 'No' WHERE id = ?", (id_res,))

        conn.commit()

    if rows:
        db.clear_cache()

    return len(rows)


def parse_fecha_a_espanol(fecha_str):
    """Convierte fecha YYYY-MM-DD a dia de la semana en espanol."""
    from constants import DIA_MAP

    dia_semana = datetime.strptime(fecha_str, "%Y-%m-%d").strftime("%A")
    return DIA_MAP.get(dia_semana, dia_semana)


def formatear_fecha_espanol(fecha_str):
    """Devuelve dd/mm/yyyy."""
    return datetime.strptime(fecha_str, "%Y-%m-%d").strftime("%d/%m/%Y")
