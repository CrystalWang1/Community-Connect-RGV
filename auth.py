from brand import header_logo
"""Local prototype accounts. No external service or API key is required."""

import hashlib
import hmac
import os
import sqlite3
from contextlib import closing
import secrets
import time
import re
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

AUTH_DB = Path(__file__).with_name("accounts.db")
ITERATIONS = 600_000


def secret(name):
    """Read a value from Streamlit Secrets (.streamlit/secrets.toml locally, the app's Secrets box when deployed)."""
    try:
        value = st.secrets.get(name)
    except Exception:  # no secrets file at all
        return None
    return str(value).strip() if value else None


def admin_emails():
    """Admin email(s) come from the ADMIN_EMAIL secret so they never appear in the public code."""
    return {email.strip().lower() for email in (secret("ADMIN_EMAIL") or "").split(",") if email.strip()}


ADMIN_EMAILS = admin_emails()  # kept for any page that imported this name


def reserved_emails():
    """Emails nobody can sign up with: the admin and demo accounts are created from Secrets instead."""
    return admin_emails() | ({secret("DEMO_EMAIL").lower()} if secret("DEMO_EMAIL") else set())


def is_admin():
    user = st.session_state.get("user")
    if not user:
        return False
    with closing(sqlite3.connect(AUTH_DB)) as connection:
        row = connection.execute("SELECT email FROM users WHERE id = ?", (user["id"],)).fetchone()
    return bool(row and row[0].strip().lower() in admin_emails())


def require_admin():
    if not is_admin():
        raise PermissionError("Administrator access required.")
AUTH_TEXT = {
    "en": {"welcome": "Welcome, {name}", "sign_out": "Sign out", "eyebrow": "Your local community, connected",
           "tagline": "Find help. Discover programs. Make plans nearby.",
           "intro": "Sign in to find community resources and events.", "sign_in": "Sign in",
           "create": "Create an account", "email": "Email", "password": "Password", "remember": "Remember me",
           "bad_login": "Email or password is incorrect.", "name": "Your name",
           "password_help": "Use at least 10 characters.", "confirm": "Confirm password",
           "create_button": "Create account", "need_name": "Enter your name.",
           "bad_email": "Enter a valid email address.", "short_password": "Use a password with at least 10 characters.",
           "mismatch": "Passwords do not match.", "exists": "An account with this email already exists. Use Sign in.",
           "created": "Account created! Open the Sign in tab to continue.",
           "cookie_blocked": "Your browser blocked the cookie change. Allow cookies and refresh to continue.",
           "other_language": "Español", "try_demo": "Try the demo (no account needed)"},
    "es": {"welcome": "Hola, {name}", "sign_out": "Cerrar sesión", "eyebrow": "Tu comunidad local, conectada",
           "tagline": "Encuentra ayuda. Descubre programas. Haz planes cerca de ti.",
           "intro": "Inicia sesión para encontrar recursos y eventos comunitarios.", "sign_in": "Iniciar sesión",
           "create": "Crear una cuenta", "email": "Correo electrónico", "password": "Contraseña",
           "remember": "Recordarme", "bad_login": "El correo o la contraseña son incorrectos.", "name": "Tu nombre",
           "password_help": "Usa al menos 10 caracteres.", "confirm": "Confirma la contraseña",
           "create_button": "Crear cuenta", "need_name": "Escribe tu nombre.",
           "bad_email": "Escribe un correo electrónico válido.",
           "short_password": "Usa una contraseña de al menos 10 caracteres.",
           "mismatch": "Las contraseñas no coinciden.",
           "exists": "Ya existe una cuenta con este correo. Usa Iniciar sesión.",
           "created": "¡Cuenta creada! Abre la pestaña Iniciar sesión para continuar.",
           "cookie_blocked": "Tu navegador bloqueó el cambio de cookies. Permite las cookies y recarga la página para continuar.",
           "other_language": "English", "try_demo": "Probar la demostración (sin cuenta)"},
}


def auth_text(key):
    return AUTH_TEXT[st.session_state.get("lang", "en")][key]


def clear_session():
    """Sign the user out of this browser session but keep their language choice."""
    language = st.session_state.get("lang")
    st.session_state.clear()
    if language:
        st.session_state.lang = language


REMEMBER_SECONDS = 7 * 24 * 60 * 60
COOKIE_NAME = "community_connect_remember"
cookie_component = components.declare_component(
    "community_connect_cookie", path=str(Path(__file__).with_name("cookie_component")))



def initialize_accounts():
    with closing(sqlite3.connect(AUTH_DB)) as connection, connection:
        connection.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
            salt BLOB NOT NULL, password_hash BLOB NOT NULL)""")
        connection.execute("""CREATE TABLE IF NOT EXISTS remembered_sessions (
            token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
            expires_at INTEGER NOT NULL)""")
        connection.execute("DELETE FROM remembered_sessions WHERE expires_at <= ?", (int(time.time()),))
    seed_accounts(
        (secret("ADMIN_NAME") or "Admin", (secret("ADMIN_EMAIL") or "").split(",")[0].strip().lower(), secret("ADMIN_PASSWORD")),
        (secret("DEMO_NAME") or "Demo User", (secret("DEMO_EMAIL") or "").lower(), secret("DEMO_PASSWORD")),
    )


@st.cache_resource(show_spinner=False)
def seed_accounts(*accounts):
    """Create (or update the password of) the admin and demo accounts from Secrets.

    Runs once per server start, so these accounts exist before anyone else can sign up with the same email,
    and they come back automatically whenever a free host resets the database.
    """
    with closing(sqlite3.connect(AUTH_DB)) as connection, connection:
        for name, email, password in accounts:
            if not email or not password:
                continue
            salt = os.urandom(32)
            if connection.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
                connection.execute("UPDATE users SET salt = ?, password_hash = ? WHERE email = ?",
                                   (salt, password_hash(password, salt), email))
            else:
                connection.execute("INSERT INTO users (name,email,salt,password_hash) VALUES (?,?,?,?)",
                                   (name, email, salt, password_hash(password, salt)))


def token_hash(token):
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def issue_token(user_id):
    token = secrets.token_urlsafe(32)
    with closing(sqlite3.connect(AUTH_DB)) as connection, connection:
        connection.execute("INSERT INTO remembered_sessions VALUES (?, ?, ?)",
                           (token_hash(token), user_id, int(time.time()) + REMEMBER_SECONDS))
    return token


def valid_token(token):
    return isinstance(token, str) and re.fullmatch(r"[A-Za-z0-9_-]{43}", token) is not None



def restore_user(token):
    if not valid_token(token):
        return None
    with closing(sqlite3.connect(AUTH_DB)) as connection, connection:
        row = connection.execute("""SELECT u.id, u.name, u.email FROM users u
            JOIN remembered_sessions s ON u.id = s.user_id
            WHERE s.token_hash = ? AND s.expires_at > ?""",
            (token_hash(token), int(time.time()))).fetchone()
    return {"id": row[0], "name": row[1], "email": row[2]} if row else None


def revoke_token(token):
    if valid_token(token):
        with closing(sqlite3.connect(AUTH_DB)) as connection, connection:
            connection.execute("DELETE FROM remembered_sessions WHERE token_hash = ?", (token_hash(token),))


def cookie_command(action, **kwargs):
    st.session_state["_cookie_command"] = {"id": secrets.token_hex(16), "action": action, **kwargs}


def password_hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)


def create_account(name, email, password):
    salt = os.urandom(32)
    with closing(sqlite3.connect(AUTH_DB)) as connection, connection:
        connection.execute("INSERT INTO users (name,email,salt,password_hash) VALUES (?,?,?,?)",
                           (name.strip(), email.strip().lower(), salt, password_hash(password, salt)))


def authenticate(email, password):
    with closing(sqlite3.connect(AUTH_DB)) as connection, connection:
        row = connection.execute("SELECT id,name,email,salt,password_hash FROM users WHERE email=?",
                                 (email.strip().lower(),)).fetchone()
    if row and hmac.compare_digest(password_hash(password, row[3]), row[4]):
        return {"id": row[0], "name": row[1], "email": row[2]}
    return None


def require_account():
    initialize_accounts()
    if "_cookie_command" not in st.session_state:
        cookie_command("read")
    command = st.session_state["_cookie_command"]
    result = cookie_component(command=command, cookie_name=COOKIE_NAME, key="remember_cookie", default=None)
    if not isinstance(result, dict) or result.get("request_id") != command["id"]:
        st.stop()
    if result.get("error"):
        if command["action"] == "set":
            revoke_token(command.get("token"))
        st.warning(auth_text("cookie_blocked"))
        st.stop()
    if command["action"] != "read":
        # Remove the raw token from command state after the browser acknowledges it.
        cookie_command("read")
        st.rerun()
    token = result.get("token")
    if not st.session_state.get("user") and token:
        user = restore_user(token)
        if user:
            st.session_state.user = user
            st.session_state.saved = set()
            st.session_state["_remember_token"] = token
        else:
            cookie_command("clear")
            st.rerun()
    if st.session_state.get("_remember_token"):
        if not restore_user(st.session_state["_remember_token"]):
            clear_session()
            cookie_command("clear")
            st.rerun()
    if st.session_state.get("user"):
        with st.container(horizontal=True, vertical_alignment="center", horizontal_alignment="right"):
            st.text(auth_text("welcome").format(name=st.session_state.user["name"]))
            if st.button(auth_text("sign_out"), icon=":material/logout:", width="content"):
                revoke_token(st.session_state.get("_remember_token"))
                revoke_token(token)
                clear_session()
                cookie_command("clear")
                st.rerun()
        return

 
    st.markdown(f'<div class="cc-header">{header_logo()}<div><div class="cc-eyebrow">{auth_text("eyebrow")}</div><h1>CommunityConnect</h1><p>{auth_text("tagline")}</p></div></div>', unsafe_allow_html=True)
    intro, language = st.columns([4, 1], vertical_alignment="center")
    intro.write(auth_text("intro"))
    if language.button(auth_text("other_language"), icon=":material/language:", key="signin_language", use_container_width=True):
        st.session_state.lang = "es" if st.session_state.get("lang", "en") == "en" else "en"
        st.rerun()
    if secret("DEMO_EMAIL") and secret("DEMO_PASSWORD"):
        if st.button(auth_text("try_demo"), icon=":material/play_circle:", key="try_demo", type="primary"):
            user = authenticate(secret("DEMO_EMAIL"), secret("DEMO_PASSWORD"))
            if user:
                revoke_token(token)
                st.session_state.user = user
                st.session_state.saved = set()
                cookie_command("clear")
                st.rerun()
    st.markdown("""<style>
    [data-testid="stTextInput"] div:has(> [data-testid="InputInstructions"]) {
        position: static !important;
        inset: auto !important;
    }
    [data-testid="stTextInput"] [data-testid="InputInstructions"] {
        position: static !important;
        inset: auto !important;
        display: block !important;
        width: 100% !important;
        text-align: left !important;
        margin-top: 0.25rem !important;
    }
    </style>""", unsafe_allow_html=True)
    signin, signup = st.tabs([auth_text("sign_in"), auth_text("create")])
    with signin:
        with st.form("signin"):
            email = st.text_input(auth_text("email"), key="signin_email")
            password = st.text_input(auth_text("password"), type="password", key="signin_password")
            remember = st.checkbox(auth_text("remember"))
            submitted = st.form_submit_button(auth_text("sign_in"), width="stretch")
        if submitted:
            user = authenticate(email, password)
            if user:
                revoke_token(token)
                st.session_state.user = user
                st.session_state.saved = set()
                if remember:
                    new_token = issue_token(user["id"])
                    st.session_state["_remember_token"] = new_token
                    cookie_command("set", token=new_token, max_age=REMEMBER_SECONDS)
                else:
                    cookie_command("clear")
                st.rerun()
            else:
                st.error(auth_text("bad_login"))
    with signup:
        with st.form("signup"):
            name = st.text_input(auth_text("name"))
            email = st.text_input(auth_text("email"), key="signup_email")
            password = st.text_input(auth_text("password"), type="password", help=auth_text("password_help"), key="signup_password")
            confirmation = st.text_input(auth_text("confirm"), type="password")
            submitted = st.form_submit_button(auth_text("create_button"), width="stretch")
        if submitted:
            normalized = email.strip().lower()
            if not name.strip():
                st.error(auth_text("need_name"))
            elif "@" not in normalized or "." not in normalized.rsplit("@", 1)[-1] or " " in normalized:
                st.error(auth_text("bad_email"))
            elif len(password) < 10:
                st.error(auth_text("short_password"))
            elif password != confirmation:
                st.error(auth_text("mismatch"))
            elif normalized in reserved_emails():
                st.error(auth_text("exists"))
            else:
                try:
                    create_account(name, normalized, password)
                except sqlite3.IntegrityError:
                    st.error(auth_text("exists"))
                else:
                    st.success(auth_text("created"))
    st.stop()