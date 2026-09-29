import asyncio
from contextlib import ExitStack
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, PropertyMock

import pandas as pd
import streamlit as st
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.app_test import calc_hash

import auth
import database as db
import estudiantes as est
import multas
import prestamos_pasillos as prestamos
from routing import SECTIONS, ROLE_PERMISSIONS


class RutasConsultasTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.stack = ExitStack()
        self.stack.enter_context(patch.object(db, 'DB_PATH', Path(self.temp.name) / 'datos.db'))
        self.stack.enter_context(patch.object(auth, 'AUTH_DB', Path(self.temp.name) / 'auth.db'))
        db.init_db()
        prestamos._invalidar_cache_lecturas()
        auth.set_password('operador', 'clave-local-de-prueba', role='tecnico')
        self.token = auth.login('operador', 'clave-local-de-prueba', 'local')
        self.cookies = self.stack.enter_context(patch.object(
            type(st.context), 'cookies', new_callable=PropertyMock,
            return_value={auth.COOKIE: self.token}))

    def tearDown(self):
        prestamos._invalidar_cache_lecturas()
        db.ensure_initialized.clear()
        self.stack.close()
        self.temp.cleanup()

    def usuario(self):
        db.ejecutar("INSERT INTO estudiantes(codigo,nombres,proyecto,documento) VALUES ('123','María José Pérez Gómez','Ingeniería','900123')")

    def test_busqueda_nombre_completo_importado_y_sin_tildes(self):
        archivo = io.BytesIO()
        archivo.name = 'personas.xlsx'
        pd.DataFrame([{'Codigo': '123', 'Nombres': 'María José',
                       'Primer apellido': 'Pérez', 'Segundo apellido': 'Gómez',
                       'Proyecto': 'Ingeniería'}]).to_excel(archivo, index=False)
        archivo.seek(0)
        est.cargar_estudiantes(archivo)
        self.assertEqual(est.buscar_estudiante('123')[1], 'María José Pérez Gómez')
        for termino in ('  MARIA   JOSE PEREZ GOMEZ ', 'Pérez Gómez', 'Gomez Maria'):
            self.assertEqual(multas.buscar_estudiantes(termino).codigo.tolist(), ['123'])
        self.assertTrue(est.buscar_personas("' OR 1=1 --").empty)
        self.assertTrue(est.buscar_personas('Maria Garcia').empty)

    def test_multa_inmediata_sin_reserva_y_pago_actualiza_historial(self):
        self.usuario()
        app = AppTest.from_string('from reportes import mostrar_busqueda_codigo\nmostrar_busqueda_codigo()')
        app.session_state.labs_codigo_busqueda = '123'
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(prestamos.obtener_alertas_bloqueo('123'), [])
        multas.agregar_multa('123', '2026-09-29', 'Prueba de persistencia', 'Manual', 'Técnico', 'Observación visible')
        self.assertTrue(prestamos.obtener_alertas_bloqueo('123'))
        app.run()
        self.assertFalse(app.exception)
        self.assertTrue(any('1 multa(s)' in w.value for w in app.warning))
        historial = next(d.value for d in app.dataframe if 'Observaciones' in d.value.columns)
        self.assertEqual(historial.iloc[0]['Observaciones'], 'Observación visible')
        multa_id = int(multas.obtener_multas_estudiante('123').iloc[0].id)
        multas.pagar_multa(multa_id, 'Técnico')
        app.run()
        self.assertFalse(app.exception)
        historial = next(d.value for d in app.dataframe if 'Pagado' in d.value.columns)
        self.assertEqual(historial.iloc[0]['Pagado'], 'SI')

    def test_consulta_multa_sin_ficha_estudiante(self):
        multas.agregar_multa('999', '2026-09-29', 'Multa sin ficha', '', 'Técnico')
        app = AppTest.from_string('from reportes import mostrar_busqueda_codigo\nmostrar_busqueda_codigo()')
        app.session_state.labs_codigo_busqueda = '999'
        app.run()
        self.assertFalse(app.exception)
        self.assertTrue(any('1 multa(s)' in w.value for w in app.warning))

    def test_migraciones_solo_una_vez(self):
        db.ensure_initialized.clear()
        with patch.object(db, 'init_db') as initialize:
            db.ensure_initialized(str(db.DB_PATH.resolve()))
            db.ensure_initialized(str(db.DB_PATH.resolve()))
            self.assertEqual(initialize.call_count, 1)

    def test_navegacion_ejecuta_solo_seccion_activa(self):
        renders = {
            'horario': 'ui_components.mostrar_horario_general',
            'reservas': 'calendario.mostrar_calendario_interactivo',
            'prestamos': 'prestamos_pasillos_ui.mostrar_prestamos_pasillos',
            'deudores': 'ui_components.mostrar_deudores',
            'consultas': 'reportes.mostrar_busqueda_codigo',
            'alertas': 'alertas_inasistencias.mostrar_alertas_inasistencias',
        }
        with ExitStack() as mocks:
            spies = {key: mocks.enter_context(patch(target)) for key, target in renders.items()}
            for target in ('app_shell.mostrar_marco', 'app_shell.preparar_lector',
                           'app_shell.restaurar_scroll_horario', 'asistencias_pendientes.mostrar_panel_asistencias_pendientes',
                           'calendario.mostrar_detalle_celda', 'calendario.mostrar_formulario_reserva_profesor',
                           'calendario.mostrar_formulario_asistencia_docente'):
                mocks.enter_context(patch(target))
            app = AppTest.from_file('app.py').run()
            self.assertFalse(app.exception)
            self.assertEqual(spies["horario"].call_count, 1)
            self.assertEqual(spies["alertas"].call_count, 1)
            for section, (_, file) in SECTIONS.items():
                for spy in spies.values():
                    spy.reset_mock()
                app.switch_page(file)
                # AppTest infiere el hash del archivo; la app declara URL personalizada.
                app._page_hash = calc_hash(section)
                app.run()
                self.assertFalse(app.exception, section)
                for key, spy in spies.items():
                    self.assertEqual(spy.call_count, int(key == section or key == "alertas"), (section, key))

    def test_pagina_directa_y_fragmento_rechazan_token_revocado(self):
        auth.logout(self.token)
        with patch('prestamos_pasillos_ui.mostrar_prestamos_pasillos') as render:
            app = AppTest.from_file('app_pages/prestamos.py').run()
            self.assertFalse(app.exception)
            render.assert_not_called()
        app = AppTest.from_string('from alertas_inasistencias import mostrar_alertas_inasistencias\nmostrar_alertas_inasistencias()').run()
        self.assertFalse(app.exception)
        self.assertFalse(app.expander)

    def test_paginas_reales_sin_errores(self):
        app = AppTest.from_file('app.py', default_timeout=30).run()
        self.assertFalse(app.exception)
        for section, (_, file) in SECTIONS.items():
            app.switch_page(file)
            app._page_hash = calc_hash(section)
            app.run()
            self.assertFalse(app.exception, file)
            self.assertTrue(any("Alertas para técnicos" in element.label for element in app.expander))

    def test_roles_y_cuenta_desactivada_revalidan_sesion(self):
        self.assertEqual(auth.session(self.token)[2], 'tecnico')
        with auth.connection() as conn:
            conn.execute("UPDATE users SET role='desconocido' WHERE username='operador'")
        self.assertIsNone(auth.session(self.token))
        with auth.connection() as conn:
            conn.execute("UPDATE users SET role='administrador',active=0 WHERE username='operador'")
        self.assertIsNone(auth.session(self.token))
        with auth.connection() as conn:
            conn.execute("UPDATE users SET active=1 WHERE username='operador'")
        self.assertEqual(auth.session(self.token)[2], 'administrador')
        self.assertIsNone(auth.session(self.token + 'x'))

    def request(self, path, token='', kind='http'):
        from server import AuthenticationMiddleware
        messages = []
        async def endpoint(scope, receive, send):
            messages.append({'type': 'authorized'})
        async def receive():
            return {'type': 'http.request', 'body': b''}
        async def send(message):
            messages.append(message)
        asyncio.run(AuthenticationMiddleware(endpoint)(
            {'type': kind, 'path': path, 'headers': [(b'cookie', f'labs_session={token}'.encode())]}, receive, send))
        return messages

    def test_http_cada_ruta_exige_sesion_y_permiso(self):
        for section in SECTIONS:
            self.assertEqual(self.request('/' + section)[0]['status'], 303)
            self.assertEqual(self.request('/' + section, self.token)[0]['type'], 'authorized')
        with patch.dict(ROLE_PERMISSIONS, {'tecnico': frozenset({'consultas'})}):
            self.assertEqual(self.request('/deudores', self.token)[0]['status'], 403)
            with patch('ui_components.mostrar_deudores') as render:
                app = AppTest.from_file('app_pages/deudores.py').run()
                self.assertFalse(app.exception)
                render.assert_not_called()
        auth.logout(self.token)
        self.assertEqual(self.request('/_stcore/stream', self.token, 'websocket')[0]['code'], 4401)

    def test_websocket_revocado_durante_conexion(self):
        from server import AuthenticationMiddleware
        messages = []
        async def endpoint(scope, receive, send):
            await receive()
            auth.logout(self.token)
            await receive()
            self.fail('No debe procesar mensajes después de revocar la sesión')
        async def receive():
            return {'type': 'websocket.receive', 'text': 'rerun'}
        async def send(message):
            messages.append(message)
        asyncio.run(AuthenticationMiddleware(endpoint)(
            {'type': 'websocket', 'path': '/_stcore/stream',
             'headers': [(b'cookie', f'labs_session={self.token}'.encode())]}, receive, send))
        self.assertEqual(messages[-1]['code'], 4401)


if __name__ == '__main__':
    unittest.main()
