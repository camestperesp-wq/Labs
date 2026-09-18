# estudiantes.py

import base64
import binascii
import json
import re

import pandas as pd
import database as db
from datetime import datetime, timedelta
from utils import normalizar_texto


CLAVES_DOCUMENTO = ("nid", "cc", "cedula", "c?dula", "documento", "identificacion", "identificaci?n", "nro_identificacion")


def _extraer_numero_documento(texto):
    numeros = re.findall(r"\d{6,10}", str(texto or ""))
    return numeros[0] if numeros else ""


def _documento_desde_json(data):
    if not isinstance(data, dict):
        return ""
    normalizado = {str(k).strip().lower(): v for k, v in data.items()}
    for clave in CLAVES_DOCUMENTO:
        if clave in normalizado:
            documento = _extraer_numero_documento(normalizado[clave])
            if documento:
                return documento
    return _extraer_numero_documento(json.dumps(data, ensure_ascii=False))


def _decodificar_base64(texto):
    entrada = str(texto or "").strip()
    if len(entrada) < 8:
        return None
    coincidencias = re.findall(r"[A-Za-z0-9+/=_-]{8,}", entrada)
    candidatos = sorted(coincidencias or [entrada], key=len, reverse=True)
    for candidato in candidatos:
        limpio = candidato.strip("=")
        fragmentos = []
        for inicio in range(0, max(1, len(limpio) - 7)):
            for fin in range(len(limpio), inicio + 7, -1):
                fragmentos.append(limpio[inicio:fin])
        fragmentos.sort(key=len, reverse=True)
        vistos = set()
        for fragmento in fragmentos:
            if fragmento in vistos:
                continue
            vistos.add(fragmento)
            normalizado = fragmento.replace("-", "+").replace("_", "/")
            normalizado += "=" * (-len(normalizado) % 4)
            try:
                decodificado = base64.b64decode(normalizado, validate=True)
                texto_decodificado = decodificado.decode("utf-8").strip()
                if texto_decodificado and (
                    re.search(r"\d{6,10}", texto_decodificado)
                    or texto_decodificado.startswith("{")
                    or re.search(r"(?i)nid|cc|cedula|documento|identificacion", texto_decodificado)
                ):
                    return texto_decodificado
            except (binascii.Error, UnicodeDecodeError, ValueError):
                continue
    return None

def normalizar_entrada_busqueda(valor, _permitir_base64=True):
    texto = str(valor or "").strip()
    if not texto:
        return ""
    if texto.startswith("{") and texto.endswith("}"):
        try:
            documento = _documento_desde_json(json.loads(texto))
            if documento:
                return documento
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    match = re.search(r'"(?:nid|cc|cedula|c?dula|documento|identificacion|identificaci?n|nro_identificacion)"\s*:\s*"?(\d{6,10})"?', texto, flags=re.IGNORECASE)
    if match:
        return match.group(1)

    if re.search(r"(?i)nid|[\[\]{}*Ññ]", texto):
        documento = _extraer_numero_documento(texto)
        if documento:
            return documento

    if _permitir_base64:
        decodificado = _decodificar_base64(texto)
        if decodificado and decodificado != texto:
            return normalizar_entrada_busqueda(decodificado, _permitir_base64=False)
    return texto


def resolver_codigo(termino):
    termino = normalizar_entrada_busqueda(termino)
    if not termino:
        return ""
    r = db.ejecutar(
        "SELECT codigo FROM estudiantes WHERE codigo=? OR documento=? LIMIT 1",
        (termino, termino),
        fetch=True,
    )
    return str(r[0][0]).strip() if r else termino


def buscar_estudiante(codigo):
    codigo = resolver_codigo(codigo)
    r = db.ejecutar("SELECT codigo, nombres, proyecto FROM estudiantes WHERE codigo=?", (codigo,), fetch=True)
    return r[0] if r else None

def contar_reservas_hoy(codigo):
    codigo = resolver_codigo(codigo)
    hoy = datetime.now().date().strftime("%Y-%m-%d")
    r = db.ejecutar("""SELECT COUNT(*) FROM reservas 
                        WHERE codigo=? AND fecha=? AND activo=1""", 
                     (codigo, hoy), fetch=True)
    return r[0][0] if r else 0

def contar_reservas_fecha(codigo, fecha):
    codigo = resolver_codigo(codigo)
    r = db.ejecutar("""SELECT COUNT(*) FROM reservas
                        WHERE codigo=? AND fecha=? AND activo=1""",
                     (codigo, fecha), fetch=True)
    return r[0][0] if r else 0

def cargar_estudiantes(archivo):
    try:
        nombre = archivo.name.lower()
        df = pd.read_excel(archivo, header=None) if nombre.endswith(('.xlsx', '.xls')) else pd.read_csv(archivo, encoding='utf-8')
        df = _normalizar_tabla_estudiantes(df)
        columnas_requeridas = ['codigo', 'nombres', 'proyecto', 'multas', 'documento']
        columnas_faltantes = [col for col in columnas_requeridas if col not in df.columns]
        if columnas_faltantes:
            raise ValueError(f"Faltan columnas requeridas: {', '.join(columnas_faltantes)}")

        df = df[columnas_requeridas].dropna(subset=['codigo'])
        df['codigo'] = df['codigo'].map(_limpiar_identificador)
        df['documento'] = df['documento'].map(_limpiar_identificador)
        for columna in ('nombres', 'proyecto', 'multas'):
            df[columna] = df[columna].fillna('').map(normalizar_texto)
        df = df[(df['codigo'] != '')].drop_duplicates(subset=['codigo'])
        with db.get_connection() as conn:
            c = conn.cursor()
            c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_codigo ON estudiantes(codigo)")
            datos = df.to_records(index=False).tolist()
            c.executemany("""
                INSERT INTO estudiantes (codigo, nombres, proyecto, multas, documento)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(codigo) DO UPDATE SET
                    nombres=excluded.nombres,
                    proyecto=excluded.proyecto,
                    multas=excluded.multas,
                    documento=excluded.documento
            """, datos)
            conn.commit()
        db.clear_cache()
        return len(df)
    except Exception as e:
        raise e


def _normalizar_tabla_estudiantes(df):
    if not all(str(col).startswith("Unnamed") or isinstance(col, int) for col in df.columns):
        return _renombrar_columnas_estudiantes(df)
    for index, row in df.head(20).iterrows():
        normalizadas = [_normalizar_columna(valor) for valor in row.tolist()]
        if "CODESTUDIANTE" in normalizadas or "CODIGO" in normalizadas:
            tabla = df.iloc[index + 1:].copy()
            tabla.columns = normalizadas
            return _renombrar_columnas_estudiantes(tabla)
    return _renombrar_columnas_estudiantes(df)


def _renombrar_columnas_estudiantes(df):
    aliases = {
        "CODIGO": "codigo",
        "CODESTUDIANTE": "codigo",
        "CODIGOESTUDIANTE": "codigo",
        "NOMBRES": "nombres",
        "NOMBRE": "nombres",
        "NOMBREESTUDIANTE": "nombres",
        "PROYECTO": "proyecto",
        "PROGRAMA": "proyecto",
        "PROYECTOCURRICULAR": "proyecto",
        "MULTAS": "multas",
        "NROIDENTIFICACION": "documento",
        "IDENTIFICACION": "documento",
        "DOCUMENTO": "documento",
        "CEDULA": "documento",
    }
    columnas = {_normalizar_columna(col): col for col in df.columns}
    renombradas = {}
    for normalizada, original in columnas.items():
        if normalizada in aliases:
            renombradas[original] = aliases[normalizada]
    resultado = df.rename(columns=renombradas).copy()
    for columna in ("multas", "documento"):
        if columna not in resultado.columns:
            resultado[columna] = ""
    return resultado


def _normalizar_columna(valor):
    import unicodedata
    valor = unicodedata.normalize("NFKD", str(valor)).upper()
    valor = "".join(c for c in valor if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9]", "", valor)


def _limpiar_identificador(valor):
    if pd.isna(valor):
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    texto = str(valor).strip()
    if re.fullmatch(r"\d+\.0", texto):
        return texto[:-2]
    return texto
