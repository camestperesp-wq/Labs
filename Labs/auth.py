"""Usuarios locales y sesiones opacas de duración absoluta: 24 horas."""
import hashlib
import hmac
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

AUTH_DB = Path(__file__).with_name("auth.db")
TTL_SECONDS = 24 * 60 * 60
COOKIE = "labs_session"


@contextmanager
def connection():
    conn = sqlite3.connect(AUTH_DB, timeout=10)
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
            yield conn
    finally:
        conn.close()


def password_hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()


def set_password(username, password):
    username = username.strip()
    if not username or len(password) < 12:
        raise ValueError("Indique un usuario y una contraseña de al menos 12 caracteres.")
    salt = secrets.token_hex(16)
    with connection() as conn:
        conn.execute("INSERT OR REPLACE INTO users VALUES (?, ?, ?)",
                     (username, salt, password_hash(password, salt)))
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
        row = conn.execute("SELECT salt,password FROM users WHERE username=?", (username,)).fetchone()
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
    if not token:
        return None
    with connection() as conn:
        return conn.execute("SELECT username,expires FROM sessions WHERE token=? AND expires>?",
                            (digest(token), time.time())).fetchone()


def logout(token):
    with connection() as conn:
        conn.execute("DELETE FROM sessions WHERE token=?", (digest(token),))


def require_login():
    import streamlit as st
    user = session(st.context.cookies.get(COOKIE, ""))
    if not user:
        st.title("Laboratorios · Universidad Distrital")
        st.info("Inicie sesión para acceder al sistema.")
        st.link_button("Iniciar sesión", "/login")
        st.stop()
    st.caption(f"Sesión: {user[0]}")
    st.link_button("Cerrar sesión", "/logout", icon=":material/menu:")
    return user[0]


if __name__ == "__main__":
    import getpass
    username = input("Usuario: ").strip()
    password = getpass.getpass("Contraseña (mínimo 12 caracteres): ")
    if password != getpass.getpass("Repita la contraseña: "):
        raise SystemExit("Las contraseñas no coinciden.")
    set_password(username, password)
    print("Usuario guardado; sus sesiones anteriores fueron revocadas.")
