"""Utilitários HTTP, TOTP, geração de PNG 1x1 e consulta somente leitura de OTP no banco."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import struct
import time
import zlib
from pathlib import Path
from typing import Any

import requests

ROOT_DIR = Path(__file__).resolve().parents[3]


def criar_sessao_http() -> requests.Session:
    """Cria sessão HTTP local sem herdar proxies de ambiente."""
    sessao = requests.Session()
    sessao.trust_env = False
    return sessao


def auth_headers(token: str) -> dict[str, str]:
    """Monta o cabeçalho Authorization Bearer."""
    return {"Authorization": f"Bearer {token.strip()}"}


def login_local(sessao: requests.Session, api_url: str, email: str, senha: str) -> dict[str, Any]:
    """Realiza login local em POST /api/auth/login."""
    resp = sessao.post(
        f"{api_url.rstrip('/')}/api/auth/login",
        json={"email": email, "password": senha, "remember_me": False},
        timeout=10,
        allow_redirects=False,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Login falhou para {email}: HTTP {resp.status_code} | {resp.text[:200]}")
    return resp.json()


def extrair_token_desafio(dados_login: dict[str, Any]) -> str | None:
    """Extrai o token temporário de desafio 2FA retornado pelo login."""
    return dados_login.get("two_factor_token") or dados_login.get("access_token") or dados_login.get("temp_token")


def png_1x1() -> bytes:
    """Gera uma imagem PNG válida de 1x1 pixel para testes de upload multipart."""
    def _chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00\xff\x00\x00")
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")


def totp_now(secret: str, interval: int = 30, digits: int = 6) -> str:
    """Calcula código TOTP RFC 6238 (SHA-1, 6 dígitos, janela de 30 s)."""
    s = secret.strip().replace(" ", "").upper()
    s += "=" * ((8 - len(s) % 8) % 8)
    key = base64.b32decode(s, casefold=True)
    msg = struct.pack(">Q", int(time.time()) // interval)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return f"{code % (10 ** digits):0{digits}d}"


def aguardar_janela_totp(margem_seg: int = 5) -> None:
    """Aguarda a virada da janela de 30 s se o código atual estiver perto de expirar."""
    resto = int(time.time()) % 30
    if resto >= (30 - margem_seg):
        time.sleep(30 - resto + 1)


def _ler_database_url() -> str | None:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        for candidato in (ROOT_DIR / ".env", ROOT_DIR / "backend" / ".env"):
            if not candidato.exists():
                continue
            for linha in candidato.read_text(encoding="utf-8").splitlines():
                linha = linha.strip()
                if linha.startswith("DATABASE_URL=") and not linha.startswith("#"):
                    valor = linha.split("=", 1)[1].strip().strip('"').strip("'")
                    if valor:
                        url = valor
                        break
            if url:
                break
    if not url:
        return None
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


def consultar_otp_email_banco(user_id: int) -> tuple[str | None, list[str]]:
    """Inspeciona somente leitura o banco experimental por eventual código OTP em texto puro."""
    url = _ler_database_url()
    if not url:
        return None, ["DATABASE_URL não configurada"]
    try:
        from sqlalchemy import create_engine, text
    except ImportError:
        return None, ["sqlalchemy não instalado"]

    engine = create_engine(url)
    achado: str | None = None
    candidatos: list[str] = []
    try:
        with engine.connect() as conn:
            cols = [
                r[0]
                for r in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'users' "
                        "ORDER BY ordinal_position"
                    )
                ).fetchall()
            ]
            cols_alvo = [
                c for c in cols
                if any(k in c.lower() for k in ("code", "otp", "2fa", "two_factor", "token"))
                and c.lower() not in ("two_factor_enabled", "two_factor_method")
            ]
            if cols_alvo:
                sel = ", ".join(f'"{c}"' for c in cols_alvo)
                row = conn.execute(
                    text(f'SELECT {sel} FROM "users" WHERE id = :uid'), {"uid": user_id}
                ).mappings().first()
                if row:
                    for c, v in row.items():
                        if v is None:
                            continue
                        s = str(v).strip()
                        candidatos.append(f"users.{c} (tipo={type(v).__name__}, len={len(s)})")
                        if re.fullmatch(r"\d{6}", s):
                            achado = s
    finally:
        engine.dispose()
    return achado, list(dict.fromkeys(candidatos))
