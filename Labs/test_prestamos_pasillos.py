import io
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timedelta

import pandas as pd

import database as db
import prestamos_pasillos as prestamos


class PrestamosPasillosTest(unittest.TestCase):
    def setUp(self):
        self._db_original = db.DB_PATH
        self._temporal = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self._temporal.name) / "prestamos_test.db"
        db.clear_cache()
        db.init_db()

    def tearDown(self):
        db.clear_cache()
        db.DB_PATH = self._db_original
        self._temporal.cleanup()

    def test_prestamo_multi_equipo_y_devolucion(self):
        prestamos.registrar_equipo("P-001", "Portátil", "INT-001")
        prestamos.registrar_equipo("P-002", "Video beam", "INT-002")
        equipos = prestamos.listar_equipos(solo_disponibles=True)

        prestamo_id = prestamos.crear_prestamo(
            equipos["id"].tolist(), "Ana Pérez", "Camilo Pérez", "Buen estado"
        )
        self.assertEqual(len(prestamos.listar_equipos(solo_disponibles=True)), 0)
        activo = prestamos.listar_prestamos("PRESTADO").iloc[0]
        self.assertEqual(int(activo["cantidad_equipos"]), 2)

        prestamos.registrar_devolucion(prestamo_id, "Carlos Rodríguez", "Sin novedades")
        self.assertEqual(len(prestamos.listar_equipos(solo_disponibles=True)), 2)
        devuelto = prestamos.listar_prestamos().iloc[0]
        self.assertEqual(devuelto["estado"], "DEVUELTO")
        self.assertTrue(devuelto["fecha_retorno"])

    def test_fpga_renovacion_tardia_genera_multa(self):
        prestamos.registrar_equipo("FP-1", "Kit FPGA Nexys", "FP-I-1")
        equipo_id = int(prestamos.obtener_equipos(True).iloc[0]["id"])
        prestamo_id = prestamos.crear_prestamo([equipo_id], "20249999", "Camilo Pérez")
        limite_vencido = (datetime.now() - timedelta(minutes=25)).isoformat(sep=" ", timespec="seconds")
        db.ejecutar("UPDATE prestamos_pasillo SET limite_fpga=? WHERE id=?", (limite_vencido, prestamo_id))
        prestamos.obtener_prestamos.clear()

        nuevo_limite = prestamos.renovar_prestamo_fpga(
            prestamo_id, "Camilo Pérez", detalle_multa="Retraso confirmado en recepción"
        )
        self.assertGreater(datetime.fromisoformat(nuevo_limite), datetime.now())
        multa = db.ejecutar(
            "SELECT motivo, retraso_minutos, monto_pago FROM multas_prestamos WHERE prestamo_id=?",
            (prestamo_id,), fetch=True,
        )[0]
        self.assertIn("No renovó a tiempo", multa[0])
        self.assertGreaterEqual(multa[1], 5)
        self.assertEqual(multa[2], 0)

    def test_fpga_dentro_de_tolerancia_no_genera_multa(self):
        prestamos.registrar_equipo("FP-2", "FPGA Basys", "FP-I-2")
        equipo_id = int(prestamos.obtener_equipos(True).iloc[0]["id"])
        prestamo_id = prestamos.crear_prestamo([equipo_id], "20247777", "Camilo Pérez")
        limite = (datetime.now() - timedelta(minutes=10)).isoformat(sep=" ", timespec="seconds")
        db.ejecutar("UPDATE prestamos_pasillo SET limite_fpga=? WHERE id=?", (limite, prestamo_id))
        prestamos.renovar_prestamo_fpga(prestamo_id, "Camilo Pérez")
        multas = db.ejecutar(
            "SELECT COUNT(*) FROM multas_prestamos WHERE prestamo_id=?",
            (prestamo_id,), fetch=True,
        )[0][0]
        self.assertEqual(multas, 0)

    def test_no_elimina_equipo_prestado(self):
        prestamos.registrar_equipo("E-1", "Osciloscopio", "E-I-1")
        equipo_id = int(prestamos.obtener_equipos(True).iloc[0]["id"])
        prestamos.crear_prestamo([equipo_id], "20248888", "Camilo Pérez")
        with self.assertRaises(ValueError):
            prestamos.eliminar_equipo(equipo_id)

    def test_devolucion_dia_siguiente_genera_bloqueo(self):
        prestamos.registrar_equipo("D-1", "Multímetro", "D-I-1")
        equipo_id = int(prestamos.obtener_equipos(True).iloc[0]["id"])
        prestamo_id = prestamos.crear_prestamo([equipo_id], "20247777", "Camilo Pérez")
        salida_ayer = (datetime.now() - timedelta(days=1)).isoformat(sep=" ", timespec="seconds")
        db.ejecutar("UPDATE prestamos_pasillo SET fecha_salida=? WHERE id=?", (salida_ayer, prestamo_id))

        prestamos.registrar_devolucion(prestamo_id, "Camilo Pérez", monto_pago=3000)
        alertas = prestamos.obtener_alertas_bloqueo("20247777")
        self.assertTrue(any("mismo día" in alerta for alerta in alertas))

    def test_carga_excel(self):
        archivo = io.BytesIO()
        pd.DataFrame([
            {"Número de placa": "P-010", "Nombre del equipo": "Tablet", "Número interno": "I-010"},
            {"Número de placa": "P-011", "Nombre del equipo": "Cámara", "Número interno": "I-011"},
        ]).to_excel(archivo, index=False)
        archivo.seek(0)

        self.assertEqual(prestamos.cargar_inventario_excel(archivo), 2)
        self.assertEqual(len(prestamos.listar_equipos()), 2)

    def test_permite_varios_equipos_sin_placa(self):
        prestamos.registrar_equipo("", "Adaptador", "I-020")
        prestamos.registrar_equipo(None, "Cable", "I-021")

        equipos = prestamos.listar_equipos()
        self.assertEqual(len(equipos), 2)
        self.assertTrue((equipos["placa"] == "").all())

    def test_busqueda_rapida_de_solicitante_por_codigo(self):
        db.ejecutar(
            "INSERT INTO estudiantes (codigo, nombres, proyecto) VALUES (?, ?, ?)",
            ("20240001", "Juan Pérez", "Ingeniería Electrónica"),
        )
        prestamos.obtener_solicitante.clear()

        solicitante = prestamos.obtener_solicitante("20240001")
        self.assertEqual(solicitante["nombres"], "Juan Pérez")
        self.assertIsNone(prestamos.obtener_solicitante("NO-EXISTE"))

        prestamos.registrar_equipo("P-030", "Grabadora", "I-030")
        equipo_id = int(prestamos.obtener_equipos(True).iloc[0]["id"])
        prestamos.crear_prestamo([equipo_id], "20240001", "Camilo Pérez")
        activos = prestamos.obtener_prestamos_activos_codigo("20240001")
        self.assertEqual(len(activos), 1)
        self.assertEqual(activos.iloc[0]["solicitante_nombre"], "Juan Pérez")


if __name__ == "__main__":
    unittest.main()
