"""Entrada obligatoria: python -m streamlit run server.py"""
import asyncio
import hmac
from html import escape
import secrets
import re
import time
from pathlib import Path
from urllib.parse import parse_qs

import streamlit as st
from starlette.middleware import Middleware
from starlette.requests import HTTPConnection
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.routing import Route
from starlette.concurrency import run_in_threadpool

import auth


def form_page(action, csrf, message=""):
    csrf = escape(csrf, quote=True)
    fields = '''<label>Usuario<input name="username" autocomplete="username" required maxlength="150"></label>
    <label>Contraseña<input type="password" name="password" autocomplete="current-password" required maxlength="1024"></label>''' if action == "login" else ""
    label = "Ingresar" if action == "login" else "Cerrar sesión"
    return HTMLResponse(f'''<!doctype html><html lang="es"><meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1"><title>{label} · UD</title>
    <style>body{{font:16px 'Segoe UI',sans-serif;background:#f5f6f7;color:#20252a;margin:0}}
    main{{max-width:360px;margin:10vh auto;padding:32px;background:white;border-top:5px solid #941419}}
    h1{{font-size:24px}}label,input{{display:block}}input{{box-sizing:border-box;width:100%;padding:12px;margin:8px 0 20px;border:1px solid #aaa;border-radius:4px}}
    button{{background:#941419;color:white;padding:12px 24px;border:0;border-radius:4px;font-size:16px}}</style>
    <main><p>Universidad Distrital</p><h1>Gestión de laboratorios</h1><p>{message}</p>
    <form method="post" action="/{action}"><input type="hidden" name="csrf" value="{csrf}">{fields}<button>{label}</button></form></main></html>''', headers={"Cache-Control": "no-store", "X-Frame-Options": "DENY"})


def fresh_form(request, action, message="", status_code=200):
    # Una segunda pestaña no debe invalidar el formulario de la primera.
    csrf = request.cookies.get("labs_csrf", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", csrf):
        csrf = secrets.token_urlsafe(32)
    response = form_page(action, csrf, message)
    response.status_code = status_code
    response.set_cookie("labs_csrf", csrf, httponly=True,
                        secure=request.url.scheme == "https", samesite="strict",
                        max_age=auth.TTL_SECONDS, path="/")
    return response


async def access(request):
    action = request.url.path.strip("/")
    secure = request.url.scheme == "https"
    if not secure and request.url.hostname not in ("localhost", "127.0.0.1", "::1"):
        return Response("El acceso por red requiere HTTPS.", status_code=400)
    if request.method == "GET":
        return fresh_form(request, action)
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 8192:
            return Response(status_code=413)
    values = parse_qs(body.decode("utf-8", errors="replace"))
    csrf = values.get("csrf", [""])[0]
    if not csrf or not hmac.compare_digest(csrf.encode(), request.cookies.get("labs_csrf", "").encode()):
        return fresh_form(request, action,
                          "El formulario venció o cambió en otra ventana. Vuelva a ingresar sus datos para continuar.",
                          status_code=403)
    if action == "logout":
        await run_in_threadpool(auth.logout, request.cookies.get(auth.COOKIE, ""))
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie(auth.COOKIE)
        return response
    token = await run_in_threadpool(auth.login, values.get("username", [""])[0].strip(),
                                    values.get("password", [""])[0], request.client.host if request.client else "unknown")
    if not token:
        return fresh_form(request, action, "Acceso no válido o temporalmente bloqueado. Intente nuevamente.")
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(auth.COOKIE, token, max_age=auth.TTL_SECONDS, httponly=True,
                        secure=secure, samesite="strict", path="/")
    return response


class AuthenticationMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        if scope["type"] == "http" and scope["path"] in ("/login", "/logout"):
            return await self.app(scope, receive, send)
        token = HTTPConnection(scope).cookies.get(auth.COOKIE, "")
        user = await run_in_threadpool(auth.session, token)
        if not user:
            if scope["type"] == "websocket":
                return await send({"type": "websocket.close", "code": 4401})
            return await RedirectResponse("/login", status_code=303)(scope, receive, send)
        if scope["type"] == "websocket":
            async def authenticated_receive():
                message = await receive()
                if message["type"] == "websocket.receive" and not await run_in_threadpool(auth.session, token):
                    raise asyncio.TimeoutError
                return message
            try:
                await asyncio.wait_for(self.app(scope, authenticated_receive, send), max(0, user[1] - time.time()))
            except asyncio.TimeoutError:
                await send({"type": "websocket.close", "code": 4401})
            return
        await self.app(scope, receive, send)


app = st.App(str(Path(__file__).with_name("app.py")),
             routes=[Route("/login", access, methods=["GET", "POST"]),
                     Route("/logout", access, methods=["GET", "POST"])],
             middleware=[Middleware(AuthenticationMiddleware)])
