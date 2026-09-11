import asyncio
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import auth
import database as db
import prestamos_pasillos as pasillos
from excel_multas import COLUMNS, importar_multas_excel


def excel(rows):
    output = io.BytesIO()
    pd.DataFrame(rows).to_excel(output, index=False)
    return output


class ImportacionesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = patch.object(db, "DB_PATH", Path(self.temp.name) / "agenda.db")
        self.path.start()
        db.init_db()
        self.row = {column: "" for column in COLUMNS.values()}
        self.row.update(CODIGO="00123", NOMBREDELESTUDIANTE="Ana Pérez", FECHASANCION="11/09/2026", PAGO="NO")

    def tearDown(self):
        db.clear_cache()
        pasillos._invalidar_cache_lecturas()
        self.path.stop()
        self.temp.cleanup()

    def test_reimportacion_actualiza_sin_duplicar(self):
        self.assertEqual(importar_multas_excel(excel([self.row]))["insertadas"], 1)
        self.row["PAGO"] = "SI"
        self.row["FECHACANCELACION"] = "2026-09-12"
        result = importar_multas_excel(excel([self.row, self.row]))
        self.assertEqual(result, {"insertadas": 0, "actualizadas": 1, "repetidas": 1})
        self.assertEqual(db.ejecutar("SELECT codigo_estudiante,pagado,fecha_pago FROM multas", fetch=True),
                         [("00123", "SI", "2026-09-12")])

    def test_error_no_importa_parcialmente(self):
        invalid = dict(self.row, CODIGO="999", FECHASANCION="ayer")
        with self.assertRaises(ValueError):
            importar_multas_excel(excel([self.row, invalid]))
        self.assertEqual(db.ejecutar("SELECT count(*) FROM multas", fetch=True)[0][0], 0)

    def test_filas_contradictorias_rechazadas(self):
        with self.assertRaises(ValueError):
            importar_multas_excel(excel([self.row, dict(self.row, PAGO="SI")]))

    def test_inventario_sin_placa_repetible(self):
        row = {"ID_Elemento": "INT-1", "Nombre": "Multímetro"}
        pasillos.cargar_inventario_excel(excel([row]))
        row["Nombre"] = "Multímetro actualizado"
        pasillos.cargar_inventario_excel(excel([row]))
        self.assertEqual(db.ejecutar("SELECT nombre FROM equipos_pasillo", fetch=True), [(row["Nombre"],)])

    def test_conflicto_inventario_revierte_carga(self):
        pasillos.registrar_equipo("P1", "Uno", "I1")
        pasillos.registrar_equipo("P2", "Dos", "I2")
        rows = [{"Placa": "P3", "Nombre": "Tres", "Interno": "I3"},
                {"Placa": "P1", "Nombre": "Conflicto", "Interno": "I2"}]
        with self.assertRaises(ValueError):
            pasillos.cargar_inventario_excel(excel(rows))
        self.assertEqual(db.ejecutar("SELECT count(*) FROM equipos_pasillo", fetch=True)[0][0], 2)

    def test_editor_permanece_al_cambiar_dia_y_guarda(self):
        from streamlit.testing.v1 import AppTest
        from constants import DIAS, HORAS, LABS_ORDEN_HORARIO
        import horario_fijo as hf
        view = AppTest.from_string("from ui_components import mostrar_horario_general\nmostrar_horario_general()").run()
        for day in (DIAS[0], DIAS[1], DIAS[0]):
            view.radio(key="horario_dia").set_value(day).run()
            self.assertFalse(view.exception)
            self.assertNotIn('horario-cell-edit', view.get("html")[0].proto.body)
            self.assertIn('horario-editable-cell', view.get("html")[0].proto.body)
            self.assertFalse(view.selectbox)
        view.query_params.update(accion_horario="guardar", dia=DIAS[0], hora=HORAS[0],
                                 lab=LABS_ORDEN_HORARIO[0], asignatura="Circuitos",
                                 carrera="Adicional", profesor="Ana", monitor="Monitor", _="test-save")
        view.run()
        self.assertFalse(view.exception)
        self.assertEqual(hf.get_horario_celda(DIAS[0], HORAS[0], LABS_ORDEN_HORARIO[0])["profesor"], "Ana")

    def test_otras_muestra_campo_y_conserva_concepto(self):
        from streamlit.testing.v1 import AppTest
        import multas
        view = AppTest.from_string("from ui_components import seleccionar_motivo_multa\nseleccionar_motivo_multa('prueba')").run()
        self.assertEqual(view.selectbox[0].options, [*multas.MOTIVOS_ESTANDAR, "OTRAS"])
        self.assertFalse(view.text_input)
        view.selectbox[0].set_value("OTRAS").run()
        self.assertEqual(len(view.text_input), 1)
        view.text_input[0].set_value("Concepto personalizado").run()
        import multas
        multas.agregar_multa("123", "2026-09-10", "Concepto personalizado", "", "Tecnico")
        self.assertIn("2026-09-10: Concepto personalizado", multas.detalles_multas_activas()["123"])
        self.assertIn("Concepto personalizado", multas.obtener_motivos_registrados())
        view.run()
        self.assertNotIn("Concepto personalizado", view.selectbox[0].options)

    def test_excel_exige_posicion_nombre_y_admite_correo_vacio(self):
        row = dict(self.row)
        nombre = row.pop("NOMBREDELESTUDIANTE")
        row["NOMBREDELESTUDIANTE"] = nombre
        with self.assertRaisesRegex(ValueError, "inmediatamente"):
            importar_multas_excel(excel([row]))
        importar_multas_excel(excel([self.row]))
        self.assertEqual(db.ejecutar("SELECT correo_usuario FROM multas", fetch=True), [("",)])

    def test_plantilla_nombre_despues_codigo(self):
        from excel_multas import plantilla_multas_excel
        columns = pd.read_excel(io.BytesIO(plantilla_multas_excel())).columns.tolist()
        self.assertEqual(columns[1], "NOMBRE DEL ESTUDIANTE")
        row = dict(self.row)
        row = {("Nombre del estudiante" if key == "NOMBREDELESTUDIANTE" else key): value for key, value in row.items()}
        self.assertEqual(importar_multas_excel(excel([row]))["insertadas"], 1)

    def test_vista_general_nombres_docente_y_monitor(self):
        import calendario as cal
        import horario_fijo as hf
        from constants import HORAS, LABS_ORDEN
        hora, lab, dia, fecha = HORAS[0], LABS_ORDEN[0], "Lunes", "2026-09-14"
        hf.set_horario_celda(dia, hora, lab, "Circuitos", "Práctica Libre", "Monitor Ana", "Docente Luis")
        for contexto in (None, cal._build_contexto_calendario(dia, fecha)):
            estado = cal._obtener_estado_celda(dia, lab, fecha, hora, contexto)
            self.assertIn("Monitor Ana", estado["etiqueta"])
            self.assertNotIn("Docente Luis", estado["etiqueta"])
        db.ejecutar("""INSERT INTO reservas(fecha,hora,laboratorio,banco,codigo,nombres,proyecto,asiste,observaciones,activo)
            VALUES (?,?,?,0,'PROFESOR','Docente Luis','Circuitos','Si','Asistencia docente: Circuitos',1)""", (fecha,hora,lab))
        for contexto in (None, cal._build_contexto_calendario(dia, fecha)):
            self.assertIn("Docente Luis", cal._obtener_estado_celda(dia,lab,fecha,hora,contexto)["etiqueta"])
        db.ejecutar("UPDATE reservas SET observaciones='Reserva de profesor: Circuitos'")
        for contexto in (None, cal._build_contexto_calendario(dia, fecha)):
            self.assertIn("Docente Luis", cal._obtener_estado_celda(dia,lab,fecha,hora,contexto)["etiqueta"])

    def test_reporte_multas_pagadas_filtra_fechas(self):
        from streamlit.testing.v1 import AppTest
        from datetime import date
        importar_multas_excel(excel([dict(self.row, PAGO="SI")]))
        view = AppTest.from_string("from ui_components import mostrar_deudores\nmostrar_deudores()").run(timeout=20)
        self.assertFalse(view.exception)
        view.date_input(key="multas_reporte_desde").set_value(date(2026,9,1))
        view.date_input(key="multas_reporte_hasta").set_value(date(2026,9,10)).run()
        self.assertFalse(view.exception)
        self.assertEqual(next(m.value for m in view.metric if m.label == "Registros"), "0")
        view.date_input(key="multas_reporte_hasta").set_value(date(2026,9,11)).run()
        self.assertFalse(view.exception)
        self.assertEqual(next(m.value for m in view.metric if m.label == "Registros"), "1")

    def test_practica_conserva_nombre_y_docente(self):
        import horario_fijo as hf
        hf.set_horario_celda("Lunes", "08:00-10:00", "Laboratorio", "Medición de voltaje",
                             "Práctica Libre", "Monitor", "Ana Pérez")
        stored = hf.get_horario_celda("Lunes", "08:00-10:00", "Laboratorio")
        self.assertEqual(stored["asignatura"], "Medición de voltaje")
        self.assertEqual(stored["profesor"], "Ana Pérez")


class AuthTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = patch.object(auth, "AUTH_DB", Path(self.temp.name) / "auth.db")
        self.path.start()
        auth.set_password("tecnico", "contraseña-de-prueba")

    def tearDown(self):
        self.path.stop()
        self.temp.cleanup()

    def test_ttl_absoluto_y_revocacion(self):
        with patch("auth.time.time", return_value=1000):
            token = auth.login("tecnico", "contraseña-de-prueba", "local")
        with patch("auth.time.time", return_value=87399):
            self.assertIsNotNone(auth.session(token))
        with patch("auth.time.time", return_value=87400):
            self.assertIsNone(auth.session(token))
        token = auth.login("tecnico", "contraseña-de-prueba", "local")
        auth.logout(token)
        self.assertIsNone(auth.session(token))

    def test_password_invalido_bloquea(self):
        for _ in range(10):
            self.assertIsNone(auth.login("tecnico", "incorrecta", "local"))
        self.assertIsNone(auth.login("tecnico", "contraseña-de-prueba", "local"))

    def test_middleware_http_y_websocket(self):
        from server import AuthenticationMiddleware
        reached = []
        async def endpoint(scope, receive, send):
            reached.append(scope["path"])
        async def request(kind, token=""):
            messages = []
            async def send(message):
                messages.append(message)
            async def receive():
                return {"type": "http.request", "body": b""}
            await AuthenticationMiddleware(endpoint)(
                {"type": kind, "path": "/_stcore/stream", "headers": [(b"cookie", f"labs_session={token}".encode())]}, receive, send)
            return messages
        self.assertEqual(asyncio.run(request("http"))[0]["status"], 303)
        self.assertEqual(asyncio.run(request("websocket"))[0]["code"], 4401)
        token = auth.login("tecnico", "contraseña-de-prueba", "local")
        asyncio.run(request("http", token))
        self.assertEqual(len(reached), 1)

    def test_login_cookie_segura_y_logout(self):
        from server import access
        from starlette.requests import Request
        from urllib.parse import urlencode
        async def post(path, fields, cookie):
            async def receive():
                return {"type": "http.request", "body": urlencode(fields).encode(), "more_body": False}
            return await access(Request({
                "type": "http", "method": "POST", "path": path, "scheme": "https",
                "query_string": b"", "server": ("labs.example", 443), "client": ("127.0.0.1", 10),
                "headers": [(b"host", b"labs.example"), (b"cookie", cookie.encode())],
            }, receive))
        invalid = asyncio.run(post("/login", {}, ""))
        self.assertEqual(invalid.status_code, 403)
        response = asyncio.run(post("/login", {"username": "tecnico", "password": "contraseña-de-prueba", "csrf": "test"}, "labs_csrf=test"))
        self.assertEqual(response.status_code, 303)
        cookie = response.headers.getlist("set-cookie")[0]
        for flag in ("HttpOnly", "Secure", "SameSite=strict", "Max-Age=86400"):
            self.assertIn(flag, cookie)
        token_cookie = cookie.split(";", 1)[0]
        token = token_cookie.split("=", 1)[1]
        self.assertIsNotNone(auth.session(token))
        asyncio.run(post("/logout", {"csrf": "test"}, token_cookie + "; labs_csrf=test"))
        self.assertIsNone(auth.session(token))

    def test_formulario_recupera_csrf_y_admite_dos_pestanas(self):
        from server import access
        from starlette.requests import Request
        from urllib.parse import urlencode
        from http.cookies import SimpleCookie
        import re

        async def request(method="GET", cookie="", fields=None):
            async def receive():
                return {"type": "http.request", "body": urlencode(fields or {}).encode(), "more_body": False}
            return await access(Request({
                "type": "http", "method": method, "path": "/login", "scheme": "http",
                "query_string": b"", "server": ("localhost", 8502), "client": ("127.0.0.1", 10),
                "headers": [(b"host", b"localhost:8502"), (b"cookie", cookie.encode())],
            }, receive))

        first = asyncio.run(request())
        cookies = SimpleCookie(first.headers["set-cookie"])
        token = cookies["labs_csrf"].value
        cookie = f"labs_csrf={token}"
        second = asyncio.run(request(cookie=cookie))
        self.assertEqual(re.search(r'name="csrf" value="([^"]+)"', second.body.decode())[1], token)
        self.assertNotIn("Secure", second.headers["set-cookie"])

        # Una cookie perdida no autentica el POST y devuelve un formulario utilizable.
        expired = asyncio.run(request("POST", fields={"csrf": token}))
        self.assertEqual(expired.status_code, 403)
        self.assertIn("text/html; charset=utf-8", expired.headers["content-type"])
        self.assertIn('name="password"', expired.body.decode())
        renewed = SimpleCookie(expired.headers["set-cookie"])["labs_csrf"].value
        response = asyncio.run(request("POST", f"labs_csrf={renewed}", {
            "csrf": renewed, "username": "tecnico", "password": "contraseña-de-prueba",
        }))
        self.assertEqual(response.status_code, 303)


if __name__ == "__main__":
    unittest.main()
