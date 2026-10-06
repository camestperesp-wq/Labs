"""Usuarios locales y sesiones opacas de duración absoluta: 24 horas."""
import hashlib
import hmac
import secrets
import sqlite3
import time
from contextlib import contextmanager
import re
from functools import lru_cache
from routing import ROLE_PERMISSIONS, can_access

from paths import AUTH_DB
TTL_SECONDS = 24 * 60 * 60
COOKIE = "labs_session"


@contextmanager
def connection():
    initialize_auth(str(AUTH_DB.resolve()))
    conn = sqlite3.connect(AUTH_DB, timeout=10)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


@lru_cache(maxsize=32)
def initialize_auth(path):
    conn = sqlite3.connect(path, timeout=10)
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY, salt TEXT NOT NULL, password TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY, username TEXT NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS attempts (
                identity TEXT PRIMARY KEY, count INTEGER NOT NULL, until REAL NOT NULL);
        """)
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            columns = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
            if "role" not in columns:
                conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'tecnico'")
            if "active" not in columns:
                conn.execute("ALTER TABLE users ADD COLUMN active INTEGER NOT NULL DEFAULT 1")
    finally:
        conn.close()


def password_hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()


def set_password(username, password, role=None):
    username = username.strip()
    if not username or len(password) < 12:
        raise ValueError("Indique un usuario y una contraseña de al menos 12 caracteres.")
    if role is not None and role not in ROLE_PERMISSIONS:
        raise ValueError("Rol no permitido.")
    salt = secrets.token_hex(16)
    with connection() as conn:
        conn.execute("""INSERT INTO users(username,salt,password,role) VALUES (?,?,?,?)
                     ON CONFLICT(username) DO UPDATE SET salt=excluded.salt,password=excluded.password""",
                     (username, salt, password_hash(password, salt), role or "tecnico"))
        if role is not None:
            conn.execute("UPDATE users SET role=? WHERE username=?", (role, username))
        conn.execute("DELETE FROM sessions WHERE username=?", (username,))


def login(username, password, ip):
    now = time.time()
    identities = ["user:" + username, "ip:" + ip]
    with connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM attempts WHERE until<=?", (now,))
        conn.execute("DELETE FROM sessions WHERE expires<=?", (now,))
        for identity in identities:
            attempt = conn.execute("SELECT count FROM attempts WHERE identity=?", (identity,)).fetchone()
            if attempt and attempt[0] >= 10:
                return None
        row = conn.execute("SELECT salt,password FROM users WHERE username=? AND active=1 AND role IN ('administrador','tecnico')", (username,)).fetchone()
        valid = hmac.compare_digest(password_hash(password, row[0] if row else "00" * 16),
                                    row[1] if row else "0" * 128)
        if not row or not valid:
            for identity in identities:
                conn.execute("""INSERT INTO attempts VALUES (?,1,?) ON CONFLICT(identity)
                             DO UPDATE SET count=count+1""", (identity, now + 900))
            return None
        conn.execute("DELETE FROM attempts WHERE identity=?", (identities[0],))
        token = secrets.token_urlsafe(32)
        conn.execute("INSERT INTO sessions VALUES (?,?,?)", (digest(token), username, now + TTL_SECONDS))
        return token


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def session(token):
    if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
        return None
    with connection() as conn:
        return conn.execute("""SELECT s.username,s.expires,u.role FROM sessions s
                            JOIN users u ON u.username=s.username
                            WHERE s.token=? AND s.expires>? AND u.active=1
                              AND u.role IN ('administrador','tecnico')""",
                            (digest(token), time.time())).fetchone()


def logout(token):
    with connection() as conn:
        conn.execute("DELETE FROM sessions WHERE token=?", (digest(token),))


def require_login(section=None):
    import streamlit as st

    user = session(st.context.cookies.get(COOKIE, ""))
    if not user:
        st.markdown(
            """
            <meta http-equiv="refresh" content="0; url=/login">
            <script>window.location.replace('/login');</script>
            """,
            unsafe_allow_html=True,
        )
        st.title("Laboratorios ? Universidad Distrital")
        st.info("La sesión no está activa. Redirigiendo al inicio de sesión...")
        st.link_button("Iniciar sesión", "/login")
        st.stop()
    if section is not None and not can_access(user[2], section):
        st.error("No tienes permiso para acceder a esta sección.")
        st.stop()
    return user[0]


def require_section(section):
    """Revalida la cookie y permisos también en reruns de fragmentos y diálogos."""
    return require_login(section)


if __name__ == "__main__":
    import getpass
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=sorted(ROLE_PERMISSIONS), default=None)
    args = parser.parse_args()
    username = input("Usuario: ").strip()
    password = getpass.getpass("Contraseña (mínimo 12 caracteres): ")
    if password != getpass.getpass("Repita la contraseña: "):
        raise SystemExit("Las contraseñas no coinciden.")
    set_password(username, password, role=args.role)
    print("Usuario guardado; sus sesiones anteriores fueron revocadas.")
