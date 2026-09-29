"""Normalización compartida para nombres completos y apellidos."""
import unicodedata


def normalizar_busqueda(value):
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).split())
