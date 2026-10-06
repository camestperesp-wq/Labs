"""Copia ambas bases con la API SQLite, sin sobrescribir archivos existentes."""
import argparse
from pathlib import Path
import sqlite3


def backup(source: Path, destination: Path) -> None:
    names = ("mi_agenda.db", "auth.db")
    source, destination = source.resolve(), destination.resolve()
    for name in names:
        if not (source / name).is_file():
            raise FileNotFoundError(f"Falta la base de origen: {source / name}")
        if (destination / name).exists():
            raise FileExistsError(f"El destino ya existe: {destination / name}")
    destination.mkdir(parents=True, exist_ok=True)
    created = []
    try:
        for name in names:
            target = destination / name
            # Reserva exclusiva: incluso dos ejecuciones simultáneas no sobrescriben.
            target.touch(exist_ok=False)
            created.append(target)
            src = sqlite3.connect((source / name).as_uri() + "?mode=ro", uri=True)
            try:
                dst = sqlite3.connect(target)
                try:
                    src.backup(dst)
                    if dst.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                        raise RuntimeError(f"Falló la verificación de {name}")
                finally:
                    dst.close()
            finally:
                src.close()
    except Exception:
        for target in created:
            target.unlink(missing_ok=True)
        raise
    print(f"Bases respaldadas en {destination}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Carpeta que contiene ambas bases")
    parser.add_argument("destination", type=Path, help="Carpeta de destino")
    args = parser.parse_args()
    backup(args.source, args.destination)
