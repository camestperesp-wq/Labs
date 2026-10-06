from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from scripts.backup_databases import backup


class BackupTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / "source"
        self.destination = Path(self.temp.name) / "backup"
        self.source.mkdir()
        for name in ("mi_agenda.db", "auth.db"):
            conn = sqlite3.connect(self.source / name)
            try:
                conn.execute("CREATE TABLE ejemplo (valor TEXT)")
                conn.execute("INSERT INTO ejemplo VALUES (?)", (name,))
                conn.commit()
            finally:
                conn.close()

    def test_copia_y_rechaza_sobrescritura(self):
        backup(self.source, self.destination)
        for name in ("mi_agenda.db", "auth.db"):
            conn = sqlite3.connect(self.destination / name)
            try:
                self.assertEqual(conn.execute("SELECT valor FROM ejemplo").fetchone(), (name,))
            finally:
                conn.close()
        before = (self.destination / "auth.db").read_bytes()
        with self.assertRaises(FileExistsError):
            backup(self.source, self.destination)
        self.assertEqual((self.destination / "auth.db").read_bytes(), before)

    def test_origen_incompleto_no_crea_destino(self):
        (self.source / "auth.db").unlink()
        with self.assertRaises(FileNotFoundError):
            backup(self.source, self.destination)
        self.assertFalse(self.destination.exists())

    def test_fallo_no_deja_copia_parcial(self):
        connect = sqlite3.connect

        def fail_second_source(path, *args, **kwargs):
            if str(path).endswith("auth.db?mode=ro"):
                raise sqlite3.OperationalError("Fallo simulado")
            return connect(path, *args, **kwargs)

        with patch("scripts.backup_databases.sqlite3.connect", side_effect=fail_second_source):
            with self.assertRaises(sqlite3.OperationalError):
                backup(self.source, self.destination)
        self.assertEqual(list(self.destination.iterdir()), [])
