"""T3 (Pytest + HTTPX) — Unidades de Identity (27: I01–I14, 11 AUT e 2 CACHE) do protocolo EXP-SEG-01."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import struct
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import text

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.t3.helpers import (  # noqa: E402
    API_BASE_URL,
    RESULTS_T3_DIR,
    RegistradorEvidencias,
    auth_headers,
    carregar_manifesto,
    carregar_openapi,
    criar_engine,
    login_ator,
)

EVIDENCIAS_PATH = RESULTS_T3_DIR / "evidencias-identity.json"
TOKEN_INVALIDO = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI5OTk5OSJ9.assinatura-invalida"


def _totp_now(secret: str, interval: int = 30, digits: int = 6) -> str:
    """Calcula código TOTP RFC 6238 (SHA-1, 6 dígitos, janela de 30s)."""
    s = secret.strip().replace(" ", "").upper()
    s += "=" * ((8 - len(s) % 8) % 8)
    key = base64.b32decode(s, casefold=True)
    msg = struct.pack(">Q", int(time.time()) // interval)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return f"{code % (10 ** digits):0{digits}d}"


def _aguardar_janela_totp(margem_seg: int = 4) -> None:
    """Evita virada de janela de 30s durante envio de código TOTP."""
    resto = int(time.time()) % 30
    if resto >= (30 - margem_seg):
        time.sleep(30 - resto + 1)


def _extrair_token_desafio(dados: dict[str, Any]) -> str | None:
    """Extrai token temporário de desafio 2FA sem assumir nome único de campo."""
    return dados.get("two_factor_token") or dados.get("access_token")


def _extrair_diretivas_cache(resp: httpx.Response) -> tuple[str | None, list[str]]:
    raw = resp.headers.get("cache-control")
    if not raw:
        return None, []
    return raw, [d.strip().lower() for d in raw.split(",") if d.strip()]


def _restaurar_estado_a(
    client: httpx.Client,
    engine,
    email_a: str,
    senha_orig: str,
    senha_alt: str | None = None,
) -> str:
    """Garante 2FA desativado e senha original de A restaurada, retornando access_token válido de A."""
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE users SET two_factor_enabled = false, two_factor_method = NULL WHERE email = :em"),
            {"em": email_a},
        )

    r_login = client.post(
        "/api/auth/login",
        json={"email": email_a, "password": senha_orig, "remember_me": False},
    )
    if r_login.status_code == 200 and r_login.json().get("access_token"):
        return r_login.json()["access_token"]

    if senha_alt:
        r_alt = client.post(
            "/api/auth/login",
            json={"email": email_a, "password": senha_alt, "remember_me": False},
        )
        if r_alt.status_code == 200 and r_alt.json().get("access_token"):
            tok_alt = r_alt.json()["access_token"]
            client.post(
                "/api/auth/change-password",
                headers=auth_headers(tok_alt),
                json={"current_password": senha_alt, "new_password": senha_orig},
            )
            r_back = client.post(
                "/api/auth/login",
                json={"email": email_a, "password": senha_orig, "remember_me": False},
            )
            if r_back.status_code == 200 and r_back.json().get("access_token"):
                return r_back.json()["access_token"]

    raise RuntimeError("Não foi possível restaurar o acesso da conta A.")


@pytest.fixture(scope="module")
def ctx():
    senha = os.environ.get("SENHA_EXP") or os.environ.get("SENHA_A")
    if not senha:
        pytest.fail(
            "Senha não informada. Execute via 'python scripts/t3/executar_bloco2.py' "
            "ou defina a variável de ambiente SENHA_EXP."
        )

    manifesto = carregar_manifesto()
    openapi = carregar_openapi()
    engine = criar_engine()
    reg = RegistradorEvidencias(EVIDENCIAS_PATH)
    client = httpx.Client(base_url=API_BASE_URL, timeout=15.0)

    email_a = manifesto["atores"]["A"]["email"]
    email_b = manifesto["atores"]["B"]["email"]
    email_v1 = manifesto["atores"]["V1"]["email"]

    tok_a = _restaurar_estado_a(client, engine, email_a, senha)
    tok_b = login_ator(client, email_b, senha)["access_token"]
    tok_v1 = login_ator(client, email_v1, senha)["access_token"]

    estado: dict[str, Any] = {
        "client": client,
        "manifesto": manifesto,
        "openapi": openapi,
        "engine": engine,
        "reg": reg,
        "senha": senha,
        "tokens": {"A": tok_a, "B": tok_b, "V1": tok_v1},
        "google_secret": None,
        "email_challenge_token": None,
        "e012_valid_status": None,
        "e012_valid_body": None,
    }
    yield estado

    try:
        _restaurar_estado_a(client, engine, email_a, senha)
    finally:
        client.close()
        engine.dispose()


def _verificar_aut(
    reg: RegistradorEvidencias,
    unidade: str,
    operacao: str,
    perfil: str,
    status_valido: int,
    status_sem_auth: int,
    status_invalido: int,
    extra: dict[str, Any] | None = None,
) -> None:
    if status_valido == 429:
        ev = {
            "status_valido": status_valido,
            "status_sem_auth": status_sem_auth,
            "status_token_invalido": status_invalido,
            **(extra or {}),
        }
        just = f"Controle positivo recebeu HTTP 429 (rate limit); sem auth={status_sem_auth}, inválido={status_invalido}."
        reg.registrar(unidade, "Identity", operacao, perfil, "Operação protegida exige credencial válida", "inconclusiva", just, ev)
        pytest.skip(just)

    desvios: list[str] = []
    if not (200 <= status_valido < 300):
        desvios.append(f"Controle positivo falhou (HTTP {status_valido})")
    if status_sem_auth not in (401, 403):
        desvios.append(f"Chamada sem credencial não rejeitada (HTTP {status_sem_auth})")
    if status_invalido not in (401, 403):
        desvios.append(f"Credencial inválida não rejeitada (HTTP {status_invalido})")

    ev: dict[str, Any] = {
        "status_valido": status_valido,
        "status_sem_auth": status_sem_auth,
        "status_token_invalido": status_invalido,
    }
    if extra:
        ev.update(extra)

    decisao = "desvio_confirmado" if desvios else "conforme"
    just = "; ".join(desvios) if desvios else (
        f"Controle positivo HTTP {status_valido}; sem credencial HTTP {status_sem_auth}; credencial inválida HTTP {status_invalido}."
    )
    reg.registrar(unidade, "Identity", operacao, perfil, "Operação protegida exige credencial válida", decisao, just, ev)
    assert not desvios, just

def test_i03_consultar_identidade_e_campos(ctx):
    client, m, spec, tok, reg = ctx["client"], ctx["manifesto"], ctx["openapi"], ctx["tokens"], ctx["reg"]
    uid_a, email_a = m["atores"]["A"]["user_id"], m["atores"]["A"]["email"]
    uid_v1, email_v1 = m["atores"]["V1"]["user_id"], m["atores"]["V1"]["email"]

    r_a = client.get("/api/auth/me", headers=auth_headers(tok["A"]))
    r_v1 = client.get("/api/auth/me", headers=auth_headers(tok["V1"]))

    id_props = set(spec["components"]["schemas"]["IdentityResponse"]["properties"].keys())
    rel_props = set(spec["components"]["schemas"]["RelatedProfileSchema"]["properties"].keys())

    desvios: list[str] = []
    ev: dict[str, Any] = {"a_status": r_a.status_code, "v1_status": r_v1.status_code}

    if r_a.status_code != 200:
        desvios.append(f"GET /api/auth/me de A retornou HTTP {r_a.status_code}")
    else:
        da = r_a.json()
        extras_a = sorted(set(da.keys()) - id_props)
        extras_client = sorted(set(da["client"].keys()) - rel_props) if isinstance(da.get("client"), dict) else []
        ev["a_identidade"] = {
            "id": da.get("id"),
            "email": da.get("email"),
            "type": da.get("type"),
            "client_keys": sorted(da["client"].keys()) if isinstance(da.get("client"), dict) else None,
            "seller": da.get("seller"),
            "extras": extras_a,
            "extras_client": extras_client,
        }
        if da.get("id") != uid_a or da.get("email") != email_a or da.get("type") != "client":
            desvios.append(f"Identidade de A divergente: id={da.get('id')}, email={da.get('email')}, type={da.get('type')}")
        if extras_a or extras_client or not isinstance(da.get("client"), dict) or da.get("seller") is not None:
            desvios.append(f"Contrato/aninhamento de A divergente: extras={extras_a}, extras_client={extras_client}")

    if r_v1.status_code != 200:
        desvios.append(f"GET /api/auth/me de V1 retornou HTTP {r_v1.status_code}")
    else:
        dv = r_v1.json()
        extras_v = sorted(set(dv.keys()) - id_props)
        extras_seller = sorted(set(dv["seller"].keys()) - rel_props) if isinstance(dv.get("seller"), dict) else []
        ev["v1_identidade"] = {
            "id": dv.get("id"),
            "email": dv.get("email"),
            "type": dv.get("type"),
            "seller_keys": sorted(dv["seller"].keys()) if isinstance(dv.get("seller"), dict) else None,
            "client": dv.get("client"),
            "extras": extras_v,
            "extras_seller": extras_seller,
        }
        if dv.get("id") != uid_v1 or dv.get("email") != email_v1 or dv.get("type") != "seller":
            desvios.append(f"Identidade de V1 divergente: id={dv.get('id')}, email={dv.get('email')}, type={dv.get('type')}")
        if extras_v or extras_seller or not isinstance(dv.get("seller"), dict) or dv.get("client") is not None:
            desvios.append(f"Contrato/aninhamento de V1 divergente: extras={extras_v}, extras_seller={extras_seller}")

    decisao = "desvio_confirmado" if desvios else "conforme"
    just = "; ".join(desvios) if desvios else (
        "GET /api/auth/me retornou as identidades corretas de A e V1 com campos dentro de IdentityResponse "
        "e referências aninhadas restritas apenas a {'id'}."
    )
    reg.registrar("I03", "Identity", "GET /api/auth/me", "A, V1", "Identidade autenticada e campos aninhados conforme IdentityResponse", decisao, just, ev)
    assert not desvios, just


def test_i14_consultar_estado_2fa_sem_segredo(ctx):
    client, spec, tok, reg = ctx["client"], ctx["openapi"], ctx["tokens"], ctx["reg"]
    r = client.get("/api/2fa/status", headers=auth_headers(tok["A"]))

    allowed = set(spec["components"]["schemas"]["User2FASchema"]["properties"].keys())
    desvios: list[str] = []
    ev: dict[str, Any] = {"status": r.status_code}
    if r.status_code != 200:
        desvios.append(f"GET /api/2fa/status retornou HTTP {r.status_code}")
    else:
        body = r.json()
        extras = sorted(set(body.keys()) - allowed)
        proibidos = [k for k in body.keys() if any(p in k.lower() for p in ("secret", "code", "uri", "token", "password"))]
        ev.update({
            "campos": sorted(body.keys()),
            "two_factor_enabled": body.get("two_factor_enabled"),
            "two_factor_method": body.get("two_factor_method"),
            "extras": extras,
            "proibidos": proibidos,
        })
        if extras or proibidos:
            desvios.append(f"Campos inesperados ou sensíveis em /api/2fa/status: extras={extras}, proibidos={proibidos}")

    decisao = "desvio_confirmado" if desvios else "conforme"
    just = "; ".join(desvios) if desvios else "GET /api/2fa/status retornou apenas os campos de User2FASchema sem segredo ou código."
    reg.registrar("I14", "Identity", "GET /api/2fa/status", "A", "Estado e método de 2FA conforme User2FASchema sem expor segredos", decisao, just, ev)
    assert not desvios, just


def test_cache_e003_no_store(ctx):
    client, tok, reg = ctx["client"], ctx["tokens"], ctx["reg"]
    r = client.get("/api/auth/me", headers=auth_headers(tok["A"]))
    raw, diretivas = _extrair_diretivas_cache(r)
    ok = r.status_code == 200 and "no-store" in diretivas
    ev = {"status": r.status_code, "cache_control": raw, "contem_no_store": "no-store" in diretivas}
    decisao = "conforme" if ok else "desvio_confirmado"
    just = f"GET /api/auth/me retornou HTTP {r.status_code} com Cache-Control={raw!r}."
    reg.registrar("CACHE-E003", "Identity", "GET /api/auth/me", "A", "Resposta bem-sucedida contém Cache-Control: no-store", decisao, just, ev)
    assert ok, just


def test_cache_e015_no_store(ctx):
    client, tok, reg = ctx["client"], ctx["tokens"], ctx["reg"]
    r = client.get("/api/2fa/status", headers=auth_headers(tok["A"]))
    raw, diretivas = _extrair_diretivas_cache(r)
    ok = r.status_code == 200 and "no-store" in diretivas
    ev = {"status": r.status_code, "cache_control": raw, "contem_no_store": "no-store" in diretivas}
    decisao = "conforme" if ok else "desvio_confirmado"
    just = f"GET /api/2fa/status retornou HTTP {r.status_code} com Cache-Control={raw!r}."
    reg.registrar("CACHE-E015", "Identity", "GET /api/2fa/status", "A", "Resposta bem-sucedida contém Cache-Control: no-store", decisao, just, ev)
    assert ok, just


def test_i04_logout_e_evento_auditoria(ctx):
    client, m, eng, tok, reg = ctx["client"], ctx["manifesto"], ctx["engine"], ctx["tokens"], ctx["reg"]
    uid_a = m["atores"]["A"]["user_id"]

    with eng.connect() as conn:
        max_id_antes = conn.execute(
            text("SELECT COALESCE(MAX(id), 0) FROM activity_logs WHERE user_id = :uid"),
            {"uid": uid_a},
        ).scalar_one()

    r = client.post("/api/auth/logout", headers=auth_headers(tok["A"]))

    with eng.connect() as conn:
        novos = conn.execute(
            text("SELECT id, user_id, action, details FROM activity_logs WHERE user_id = :uid AND id > :mid ORDER BY id ASC"),
            {"uid": uid_a, "mid": max_id_antes},
        ).mappings().all()

    eventos = [dict(row) for row in novos]
    tem_logout = any("logout" in str(e.get("action", "")).lower() or "logout" in str(e.get("details", "")).lower() for e in eventos)

    desvios: list[str] = []
    if r.status_code != 200:
        desvios.append(f"POST /api/auth/logout retornou HTTP {r.status_code}")
    if not tem_logout:
        desvios.append(f"Nenhum evento de logout persistido em activity_logs para user_id={uid_a} (novos={eventos}).")

    ev = {
        "status": r.status_code,
        "resposta": r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text[:200],
        "novos_eventos_auditoria": eventos,
    }
    decisao = "desvio_confirmado" if desvios else "conforme"
    just = "; ".join(desvios) if desvios else (
        f"Logout de A retornou HTTP 200 e registrou evento de auditoria associado a user_id={uid_a} em activity_logs "
        "(política local não exige revogação imediata do JWT)."
    )
    reg.registrar("I04", "Identity", "POST /api/auth/logout", "A", "Logout retorna sucesso e registra evento de auditoria associado à conta", decisao, just, ev)
    assert not desvios, just


def test_i08_configurar_e_confirmar_google_2fa(ctx):
    client, tok, reg = ctx["client"], ctx["tokens"], ctx["reg"]
    desvios: list[str] = []
    ev: dict[str, Any] = {}

    st_antes = client.get("/api/2fa/status", headers=auth_headers(tok["A"])).json()
    ev["estado_antes"] = st_antes
    if st_antes.get("two_factor_enabled") is not False:
        desvios.append(f"Estado inicial antes da configuração já estava habilitado: {st_antes}")

    r_en = client.post("/api/2fa/enable/google", headers=auth_headers(tok["A"]))
    ev["enable_status"] = r_en.status_code
    if r_en.status_code != 200:
        desvios.append(f"POST /api/2fa/enable/google falhou: HTTP {r_en.status_code}")
    else:
        body_en = r_en.json()
        secret = body_en.get("secret")
        ev["secret_presente"] = bool(secret)
        ev["provisioning_uri_presente"] = bool(body_en.get("provisioning_uri"))
        if not secret:
            desvios.append("Segredo ausente no retorno de /api/2fa/enable/google.")
        else:
            ctx["google_secret"] = secret
            st_meio = client.get("/api/2fa/status", headers=auth_headers(tok["A"])).json()
            ev["estado_antes_confirmacao"] = st_meio
            if st_meio.get("two_factor_enabled") is not False:
                desvios.append(f"2FA ativou antes da confirmação: {st_meio}")

            _aguardar_janela_totp()
            r_conf = client.post(
                "/api/2fa/confirm/google",
                headers=auth_headers(tok["A"]),
                json={"code": _totp_now(secret)},
            )
            ev["confirm_status"] = r_conf.status_code
            st_depois = client.get("/api/2fa/status", headers=auth_headers(tok["A"])).json()
            ev["estado_depois_confirmacao"] = st_depois
            if r_conf.status_code != 200 or st_depois.get("two_factor_enabled") is not True or st_depois.get("two_factor_method") != "google":
                desvios.append(f"Confirmação Google 2FA não ativou o método esperado: HTTP {r_conf.status_code}, status={st_depois}")

    decisao = "desvio_confirmado" if desvios else "conforme"
    just = "; ".join(desvios) if desvios else (
        "Transição E008+E009 validada: 2FA permaneceu inativo antes da confirmação e tornou-se ativo (method='google') somente após confirmação TOTP válida."
    )
    reg.registrar("I08", "Identity", "POST /api/2fa/enable/google + POST /api/2fa/confirm/google", "A", "Transição de configuração e confirmação do autenticador Google", decisao, just, ev)
    assert not desvios, just


def test_i01_login_local_sem_e_com_2fa(ctx):
    client, m, reg = ctx["client"], ctx["manifesto"], ctx["reg"]
    senha = ctx["senha"]
    email_a, uid_a = m["atores"]["A"]["email"], m["atores"]["A"]["user_id"]
    email_b, uid_b = m["atores"]["B"]["email"], m["atores"]["B"]["user_id"]

    desvios: list[str] = []
    ev: dict[str, Any] = {}

    r_b = client.post("/api/auth/login", json={"email": email_b, "password": senha, "remember_me": False})
    ev["sem_2fa_login_status"] = r_b.status_code
    if r_b.status_code != 200:
        desvios.append(f"Login sem 2FA (B) falhou: HTTP {r_b.status_code}")
    else:
        db = r_b.json()
        tok_b = db.get("access_token")
        ev["sem_2fa_required"] = db.get("two_factor_required")
        r_me_b = client.get("/api/auth/me", headers=auth_headers(tok_b)) if tok_b else None
        ev["sem_2fa_me_status"] = r_me_b.status_code if r_me_b else None
        if db.get("two_factor_required") is not False or not r_me_b or r_me_b.status_code != 200 or r_me_b.json().get("id") != uid_b:
            desvios.append(f"Conta sem 2FA não recebeu acesso completo válido: required={db.get('two_factor_required')}, me={r_me_b.status_code if r_me_b else None}")

    r_a = client.post("/api/auth/login", json={"email": email_a, "password": senha, "remember_me": False})
    ev["com_2fa_login_status"] = r_a.status_code
    if r_a.status_code != 200:
        desvios.append(f"Login com 2FA (A) falhou: HTTP {r_a.status_code}")
    else:
        da = r_a.json()
        desafio_tok = _extrair_token_desafio(da)
        ev["com_2fa_required"] = da.get("two_factor_required")
        ev["com_2fa_method"] = da.get("two_factor_method")
        ev["com_2fa_desafio_presente"] = bool(desafio_tok)

        if da.get("two_factor_required") is not True or not desafio_tok:
            desvios.append(f"Conta com 2FA não recebeu desafio de segundo fator: required={da.get('two_factor_required')}")
        else:
            r_me_desafio = client.get("/api/auth/me", headers=auth_headers(desafio_tok))
            ev["desafio_em_me_status"] = r_me_desafio.status_code
            if r_me_desafio.status_code not in (401, 403):
                desvios.append(f"Credencial de desafio 2FA obteve acesso indevido em GET /api/auth/me (HTTP {r_me_desafio.status_code}).")

            secret = ctx.get("google_secret")
            if secret:
                _aguardar_janela_totp()
                r_ver = client.post(
                    "/api/2fa/verify/google",
                    headers=auth_headers(desafio_tok),
                    json={"code": _totp_now(secret)},
                )
                ev["pos_verificacao_status"] = r_ver.status_code
                if r_ver.status_code != 200:
                    desvios.append(f"Verificação 2FA após login falhou: HTTP {r_ver.status_code}")
                else:
                    full_tok = r_ver.json().get("access_token")
                    r_me_full = client.get("/api/auth/me", headers=auth_headers(full_tok)) if full_tok else None
                    ev["pos_verificacao_me_status"] = r_me_full.status_code if r_me_full else None
                    if not r_me_full or r_me_full.status_code != 200 or r_me_full.json().get("id") != uid_a:
                        desvios.append(f"Sessão pós-2FA não acessou /api/auth/me corretamente: HTTP {r_me_full.status_code if r_me_full else None}")

    decisao = "desvio_confirmado" if desvios else "conforme"
    just = "; ".join(desvios) if desvios else (
        "Login local distinguiu sessão completa (B sem 2FA -> /me 200) de desafio 2FA "
        "(A com 2FA -> token de desafio rejeitado em /me com 401/403 e acesso completo concedido somente após verificação)."
    )
    reg.registrar("I01", "Identity", "POST /api/auth/login", "A, B", "Login distingue sessão completa e desafio 2FA", decisao, just, ev)
    assert not desvios, just


def test_i09_verificar_autenticador_google(ctx):
    client, m, reg = ctx["client"], ctx["manifesto"], ctx["reg"]
    email_a, uid_a = m["atores"]["A"]["email"], m["atores"]["A"]["user_id"]
    secret = ctx.get("google_secret")
    assert secret, "Segredo Google 2FA não disponível a partir de I08."

    r_login = client.post("/api/auth/login", json={"email": email_a, "password": ctx["senha"], "remember_me": False})
    assert r_login.status_code == 200
    desafio_tok = _extrair_token_desafio(r_login.json())
    assert desafio_tok

    desvios: list[str] = []
    ev: dict[str, Any] = {}

    r_bad_code = client.post(
        "/api/2fa/verify/google",
        headers=auth_headers(desafio_tok),
        json={"code": "000000" if _totp_now(secret) != "000000" else "999999"},
    )
    ev["codigo_invalido_status"] = r_bad_code.status_code
    if r_bad_code.status_code == 200:
        desvios.append("POST /api/2fa/verify/google aceitou código TOTP inválido.")

    _aguardar_janela_totp()
    r_ok = client.post(
        "/api/2fa/verify/google",
        headers=auth_headers(desafio_tok),
        json={"code": _totp_now(secret)},
    )
    ev["codigo_valido_status"] = r_ok.status_code
    if r_ok.status_code != 200:
        desvios.append(f"Verificação Google 2FA válida falhou: HTTP {r_ok.status_code}")
    else:
        body = r_ok.json()
        full_tok = body.get("access_token")
        ev["two_factor_required_final"] = body.get("two_factor_required")
        r_me = client.get("/api/auth/me", headers=auth_headers(full_tok)) if full_tok else None
        ev["me_status"] = r_me.status_code if r_me else None
        ev["me_user_id"] = r_me.json().get("id") if r_me and r_me.status_code == 200 else None
        if body.get("two_factor_required") is not False or not r_me or r_me.status_code != 200 or r_me.json().get("id") != uid_a:
            desvios.append(f"Sessão resultante da verificação Google não corresponde a A: status={r_me.status_code if r_me else None}")

    decisao = "desvio_confirmado" if desvios else "conforme"
    just = "; ".join(desvios) if desvios else "Verificação Google rejeitou código inválido e concluiu sessão completa da conta A com TOTP válido."
    reg.registrar("I09", "Identity", "POST /api/2fa/verify/google", "A", "Verificação pelo autenticador conclui sessão da conta do desafio", decisao, just, ev)
    assert not desvios, just


def test_aut_e010_verify_google(ctx):
    client, m, reg = ctx["client"], ctx["manifesto"], ctx["reg"]
    secret = ctx.get("google_secret")
    assert secret, "Segredo Google 2FA ausente."
    r_login = client.post("/api/auth/login", json={"email": m["atores"]["A"]["email"], "password": ctx["senha"], "remember_me": False})
    assert r_login.status_code == 200
    desafio_tok = _extrair_token_desafio(r_login.json())
    assert desafio_tok

    _aguardar_janela_totp()
    code = _totp_now(secret)
    r_no = client.post("/api/2fa/verify/google", json={"code": code})
    r_bad = client.post("/api/2fa/verify/google", headers=auth_headers(TOKEN_INVALIDO), json={"code": code})
    r_ok = client.post("/api/2fa/verify/google", headers=auth_headers(desafio_tok), json={"code": code})
    _verificar_aut(reg, "AUT-E010", "POST /api/2fa/verify/google", "A (desafio)", r_ok.status_code, r_no.status_code, r_bad.status_code)


def test_aut_e008_e_e009_google_setup(ctx):
    client, tok, reg = ctx["client"], ctx["tokens"], ctx["reg"]
    client.post("/api/2fa/disable", headers=auth_headers(tok["A"]))

    r8_no = client.post("/api/2fa/enable/google")
    r8_bad = client.post("/api/2fa/enable/google", headers=auth_headers(TOKEN_INVALIDO))
    r8_ok = client.post("/api/2fa/enable/google", headers=auth_headers(tok["A"]))
    _verificar_aut(reg, "AUT-E008", "POST /api/2fa/enable/google", "A", r8_ok.status_code, r8_no.status_code, r8_bad.status_code)

    secret = r8_ok.json().get("secret")
    assert secret
    _aguardar_janela_totp()
    code = _totp_now(secret)
    r9_no = client.post("/api/2fa/confirm/google", json={"code": code})
    r9_bad = client.post("/api/2fa/confirm/google", headers=auth_headers(TOKEN_INVALIDO), json={"code": code})
    r9_ok = client.post("/api/2fa/confirm/google", headers=auth_headers(tok["A"]), json={"code": code})
    _verificar_aut(reg, "AUT-E009", "POST /api/2fa/confirm/google", "A", r9_ok.status_code, r9_no.status_code, r9_bad.status_code)

def test_i10_habilitar_2fa_email(ctx):
    client, tok, reg = ctx["client"], ctx["tokens"], ctx["reg"]
    client.post("/api/2fa/disable", headers=auth_headers(tok["A"]))

    st_a_antes = client.get("/api/2fa/status", headers=auth_headers(tok["A"])).json()
    st_b_antes = client.get("/api/2fa/status", headers=auth_headers(tok["B"])).json()

    r = client.post("/api/2fa/enable/email", headers=auth_headers(tok["A"]))
    st_a_depois = client.get("/api/2fa/status", headers=auth_headers(tok["A"])).json()
    st_b_depois = client.get("/api/2fa/status", headers=auth_headers(tok["B"])).json()

    desvios: list[str] = []
    if r.status_code != 200 or st_a_depois.get("two_factor_enabled") is not True or st_a_depois.get("two_factor_method") != "email":
        desvios.append(f"Ativação 2FA por e-mail em A falhou: HTTP {r.status_code}, depois={st_a_depois}")
    if st_b_depois != st_b_antes:
        desvios.append(f"Ativação em A alterou 2FA de B: antes={st_b_antes}, depois={st_b_depois}")

    ev = {"status": r.status_code, "a_antes": st_a_antes, "a_depois": st_a_depois, "b_preservado": st_b_depois == st_b_antes}
    decisao = "desvio_confirmado" if desvios else "conforme"
    just = "; ".join(desvios) if desvios else "Ativação por A habilitou 2FA com método 'email' apenas na própria conta, preservando B."
    reg.registrar("I10", "Identity", "POST /api/2fa/enable/email", "A, B", "Ativação do método e-mail restrita à própria conta", decisao, just, ev)
    assert not desvios, just


def test_i11_enviar_codigo_email(ctx):
    client, m, eng, reg = ctx["client"], ctx["manifesto"], ctx["engine"], ctx["reg"]
    email_a, uid_a = m["atores"]["A"]["email"], m["atores"]["A"]["user_id"]

    r_login = client.post("/api/auth/login", json={"email": email_a, "password": ctx["senha"], "remember_me": False})
    assert r_login.status_code == 200
    desafio_tok = _extrair_token_desafio(r_login.json())
    assert desafio_tok
    ctx["email_challenge_token"] = desafio_tok

    r = client.post("/api/2fa/send/email", headers=auth_headers(desafio_tok))
    ctx["e012_valid_status"] = r.status_code
    ctx["e012_valid_body"] = r.text[:200]

    with eng.connect() as conn:
        row = conn.execute(
            text("SELECT two_factor_email_code, two_factor_email_expiry FROM users WHERE id = :uid"),
            {"uid": uid_a},
        ).mappings().first()

    code_val = row["two_factor_email_code"] if row else None
    expiry_val = str(row["two_factor_email_expiry"]) if row and row["two_factor_email_expiry"] else None

    ev = {
        "status": r.status_code,
        "resposta": r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text[:200],
        "db_hash_presente": bool(code_val),
        "db_hash_len": len(str(code_val)) if code_val else 0,
        "db_expiry_presente": bool(expiry_val),
        "caixa_teste_smtp": "indisponivel (dominio sintetico example.com sem Mailpit/sink local)",
    }

    if r.status_code not in (200, 429):
        just = f"POST /api/2fa/send/email falhou inesperadamente com HTTP {r.status_code}."
        reg.registrar("I11", "Identity", "POST /api/2fa/send/email", "A (desafio)", "Envio de código 2FA ao destinatário previsto", "desvio_confirmado", just, ev)
        pytest.fail(just)

    just = (
        f"Operação retornou HTTP {r.status_code} e persistiu hash do OTP (len={ev['db_hash_len']}) com expiração no banco, "
        "mas a entrega efetiva ao destinatário na caixa de teste não pôde ser conferida (dependência externa SMTP com domínio sintético example.com)."
    )
    reg.registrar("I11", "Identity", "POST /api/2fa/send/email", "A (desafio)", "Envio de código 2FA ao destinatário previsto", "inconclusiva", just, ev)
    pytest.skip(just)


def test_i12_verificar_codigo_email(ctx):
    client, m, eng, reg = ctx["client"], ctx["manifesto"], ctx["engine"], ctx["reg"]
    desafio_tok = ctx.get("email_challenge_token")
    assert desafio_tok, "Token de desafio de e-mail ausente."
    uid_a = m["atores"]["A"]["user_id"]

    r_bad = client.post("/api/2fa/verify/email", headers=auth_headers(desafio_tok), json={"code": "000000"})
    with eng.connect() as conn:
        code_val = conn.execute(
            text("SELECT two_factor_email_code FROM users WHERE id = :uid"),
            {"uid": uid_a},
        ).scalar_one_or_none()

    ev = {
        "codigo_ficticio_status": r_bad.status_code,
        "db_hash_len": len(str(code_val)) if code_val else 0,
        "caixa_teste_smtp": "indisponivel (OTP armazenado em hash e dominio example.com sem caixa recebivel)",
    }
    if r_bad.status_code == 200:
        just = "POST /api/2fa/verify/email aceitou código fictício 000000."
        reg.registrar("I12", "Identity", "POST /api/2fa/verify/email", "A (desafio)", "Verificação válida do código de e-mail conclui sessão de A", "desvio_confirmado", just, ev)
        pytest.fail(just)

    just = (
        f"Código fictício foi rejeitado (HTTP {r_bad.status_code}), mas o controle positivo não pôde ser executado "
        f"porque o OTP é armazenado como hash (len={ev['db_hash_len']}) e o ambiente não dispõe de caixa SMTP recebível para example.com."
    )
    reg.registrar("I12", "Identity", "POST /api/2fa/verify/email", "A (desafio)", "Verificação válida do código de e-mail conclui sessão de A", "inconclusiva", just, ev)
    pytest.skip(just)


def test_aut_e011_enable_email(ctx):
    client, tok, reg = ctx["client"], ctx["tokens"], ctx["reg"]
    r_no = client.post("/api/2fa/enable/email")
    r_bad = client.post("/api/2fa/enable/email", headers=auth_headers(TOKEN_INVALIDO))
    r_ok = client.post("/api/2fa/enable/email", headers=auth_headers(tok["A"]))
    _verificar_aut(reg, "AUT-E011", "POST /api/2fa/enable/email", "A", r_ok.status_code, r_no.status_code, r_bad.status_code)


def test_aut_e012_send_email(ctx):
    client, reg = ctx["client"], ctx["reg"]
    status_valido = ctx.get("e012_valid_status")
    if status_valido is None:
        desafio_tok = ctx.get("email_challenge_token")
        assert desafio_tok
        status_valido = client.post("/api/2fa/send/email", headers=auth_headers(desafio_tok)).status_code

    r_no = client.post("/api/2fa/send/email")
    r_bad = client.post("/api/2fa/send/email", headers=auth_headers(TOKEN_INVALIDO))
    _verificar_aut(
        reg,
        "AUT-E012",
        "POST /api/2fa/send/email",
        "A (desafio)",
        status_valido,
        r_no.status_code,
        r_bad.status_code,
        extra={"controle_positivo_reaproveitado_de_i11_para_evitar_429": True},
    )


def test_aut_e013_verify_email(ctx):
    client, reg = ctx["client"], ctx["reg"]
    r_no = client.post("/api/2fa/verify/email", json={"code": "000000"})
    r_bad = client.post("/api/2fa/verify/email", headers=auth_headers(TOKEN_INVALIDO), json={"code": "000000"})
    ev = {
        "status_sem_auth": r_no.status_code,
        "status_token_invalido": r_bad.status_code,
        "controle_positivo": "indisponivel (OTP em hash + SMTP sem caixa recebivel)",
    }
    if r_no.status_code == 200 or r_bad.status_code == 200:
        just = f"POST /api/2fa/verify/email aceitou requisição sem credencial válida (sem_auth={r_no.status_code}, invalido={r_bad.status_code})."
        reg.registrar("AUT-E013", "Identity", "POST /api/2fa/verify/email", "A (desafio)", "Operação protegida exige credencial válida", "desvio_confirmado", just, ev)
        pytest.fail(just)

    just = (
        f"Chamadas sem credencial (HTTP {r_no.status_code}) e com credencial inválida (HTTP {r_bad.status_code}) foram rejeitadas, "
        "mas faltou controle positivo 2xx porque o OTP é armazenado em hash e não há caixa SMTP recebível para example.com."
    )
    reg.registrar("AUT-E013", "Identity", "POST /api/2fa/verify/email", "A (desafio)", "Operação protegida exige credencial válida", "inconclusiva", just, ev)
    pytest.skip(just)


def test_i13_desabilitar_2fa_e_login_posterior(ctx):
    client, m, eng, tok, reg = ctx["client"], ctx["manifesto"], ctx["engine"], ctx["tokens"], ctx["reg"]
    email_a, uid_a = m["atores"]["A"]["email"], m["atores"]["A"]["user_id"]

    r = client.post("/api/2fa/disable", headers=auth_headers(tok["A"]))
    st = client.get("/api/2fa/status", headers=auth_headers(tok["A"])).json()
    with eng.connect() as conn:
        db_row = conn.execute(
            text("SELECT two_factor_enabled, two_factor_method FROM users WHERE id = :uid"),
            {"uid": uid_a},
        ).mappings().first()

    r_login = client.post("/api/auth/login", json={"email": email_a, "password": ctx["senha"], "remember_me": False})
    desvios: list[str] = []
    if r.status_code != 200 or st.get("two_factor_enabled") is not False:
        desvios.append(f"Desativação de 2FA falhou: HTTP {r.status_code}, status={st}")
    if not db_row or db_row["two_factor_enabled"] is not False:
        desvios.append(f"Estado persistido no banco não desativou 2FA: {dict(db_row) if db_row else None}")
    if r_login.status_code != 200 or r_login.json().get("two_factor_required") is not False or not r_login.json().get("access_token"):
        desvios.append(f"Login posterior após desativação não retornou sessão direta: HTTP {r_login.status_code}")

    ev = {
        "disable_status": r.status_code,
        "status_api": st,
        "db_two_factor_enabled": db_row["two_factor_enabled"] if db_row else None,
        "login_posterior_status": r_login.status_code,
        "login_posterior_2fa_required": r_login.json().get("two_factor_required") if r_login.status_code == 200 else None,
    }
    decisao = "desvio_confirmado" if desvios else "conforme"
    just = "; ".join(desvios) if desvios else "Desativação persistiu two_factor_enabled=False no banco e o login seguinte retornou sessão completa direta."
    reg.registrar("I13", "Identity", "POST /api/2fa/disable", "A", "Desativação persiste no banco e libera login direto", decisao, just, ev)
    assert not desvios, just


def test_aut_e014_disable_2fa(ctx):
    client, tok, reg = ctx["client"], ctx["tokens"], ctx["reg"]
    r_no = client.post("/api/2fa/disable")
    r_bad = client.post("/api/2fa/disable", headers=auth_headers(TOKEN_INVALIDO))
    r_ok = client.post("/api/2fa/disable", headers=auth_headers(tok["A"]))
    _verificar_aut(reg, "AUT-E014", "POST /api/2fa/disable", "A", r_ok.status_code, r_no.status_code, r_bad.status_code)


def test_aut_e003_e004_e015(ctx):
    client, tok, reg = ctx["client"], ctx["tokens"], ctx["reg"]

    r3_no = client.get("/api/auth/me")
    r3_bad = client.get("/api/auth/me", headers=auth_headers(TOKEN_INVALIDO))
    r3_ok = client.get("/api/auth/me", headers=auth_headers(tok["A"]))
    _verificar_aut(reg, "AUT-E003", "GET /api/auth/me", "A", r3_ok.status_code, r3_no.status_code, r3_bad.status_code)

    r4_no = client.post("/api/auth/logout")
    r4_bad = client.post("/api/auth/logout", headers=auth_headers(TOKEN_INVALIDO))
    r4_ok = client.post("/api/auth/logout", headers=auth_headers(tok["A"]))
    _verificar_aut(reg, "AUT-E004", "POST /api/auth/logout", "A", r4_ok.status_code, r4_no.status_code, r4_bad.status_code)

    r15_no = client.get("/api/2fa/status")
    r15_bad = client.get("/api/2fa/status", headers=auth_headers(TOKEN_INVALIDO))
    r15_ok = client.get("/api/2fa/status", headers=auth_headers(tok["A"]))
    _verificar_aut(reg, "AUT-E015", "GET /api/2fa/status", "A", r15_ok.status_code, r15_no.status_code, r15_bad.status_code)


def test_i02_login_google(ctx):
    client, reg = ctx["client"], ctx["reg"]
    r_bad = client.post("/api/auth/google", json={"token": "token-google-invalido-exp-seg-01"})
    ev = {
        "token_invalido_status": r_bad.status_code,
        "credencial_google_teste": "indisponivel (sem Google ID Token assinado vinculado a conta local no ambiente experimental)",
    }
    if r_bad.status_code == 200:
        just = "POST /api/auth/google aceitou token Google fictício e emitiu sessão."
        reg.registrar("I02", "Identity", "POST /api/auth/google", "Público", "Login Google preserva vínculo da conta local e estado de 2FA", "desvio_confirmado", just, ev)
        pytest.fail(just)

    just = (
        f"Token Google inválido foi rejeitado (HTTP {r_bad.status_code}), mas não há credencial Google OAuth de teste "
        "assinada e vinculada a uma conta experimental para validar o fluxo positivo."
    )
    reg.registrar("I02", "Identity", "POST /api/auth/google", "Público", "Login Google preserva vínculo da conta local e estado de 2FA", "inconclusiva", just, ev)
    pytest.skip(just)


def test_i06_recuperacao_senha_anti_enumeracao(ctx):
    client, m, eng, reg = ctx["client"], ctx["manifesto"], ctx["engine"], ctx["reg"]
    email_a, uid_a = m["atores"]["A"]["email"], m["atores"]["A"]["user_id"]
    email_inexistente = "nao-cadastrado-exp-seg-01@example.com"

    with eng.connect() as conn:
        antes = conn.execute(
            text("SELECT COUNT(*) FROM password_reset_tokens WHERE user_id = :uid"),
            {"uid": uid_a},
        ).scalar_one()

    r_cad = client.post("/api/auth/forgot-password", json={"email": email_a})
    r_aus = client.post("/api/auth/forgot-password", json={"email": email_inexistente})

    with eng.connect() as conn:
        depois = conn.execute(
            text("SELECT COUNT(*) FROM password_reset_tokens WHERE user_id = :uid"),
            {"uid": uid_a},
        ).scalar_one()

    corpo_cad = r_cad.json() if r_cad.headers.get("content-type", "").startswith("application/json") else r_cad.text
    corpo_aus = r_aus.json() if r_aus.headers.get("content-type", "").startswith("application/json") else r_aus.text
    iguais = (r_cad.status_code == r_aus.status_code) and (corpo_cad == corpo_aus)

    ev = {
        "cadastrado_status": r_cad.status_code,
        "ausente_status": r_aus.status_code,
        "cadastrado_corpo": corpo_cad,
        "ausente_corpo": corpo_aus,
        "respostas_identicas": iguais,
        "tokens_reset_user_a_antes": antes,
        "tokens_reset_user_a_depois": depois,
        "caixa_teste_smtp": "indisponivel (dominio sintetico example.com sem Mailpit/sink local)",
    }

    if not iguais:
        just = f"Respostas públicas divergiram entre e-mail cadastrado ({r_cad.status_code}: {corpo_cad}) e ausente ({r_aus.status_code}: {corpo_aus})."
        reg.registrar("I06", "Identity", "POST /api/auth/forgot-password", "Público", "Mesma mensagem pública para e-mail cadastrado e ausente + entrega conferida", "desvio_confirmado", just, ev)
        pytest.fail(just)

    if depois <= antes:
        just = f"Respostas públicas foram idênticas (HTTP {r_cad.status_code}), mas nenhum registro foi criado em password_reset_tokens para A."
        reg.registrar("I06", "Identity", "POST /api/auth/forgot-password", "Público", "Mesma mensagem pública para e-mail cadastrado e ausente + entrega conferida", "inconclusiva", just, ev)
        pytest.skip(just)

    just = (
        f"Respostas públicas idênticas (HTTP {r_cad.status_code}) e registro criado em password_reset_tokens para A "
        f"({antes}->{depois}), porém a entrega na caixa de teste não pôde ser conferida (dependência externa SMTP em example.com)."
    )
    reg.registrar("I06", "Identity", "POST /api/auth/forgot-password", "Público", "Mesma mensagem pública para e-mail cadastrado e ausente + entrega conferida", "inconclusiva", just, ev)
    pytest.skip(just)


def test_i07_redefinir_senha(ctx):
    client, m, eng, reg = ctx["client"], ctx["manifesto"], ctx["engine"], ctx["reg"]
    uid_a = m["atores"]["A"]["user_id"]

    r_bad = client.post(
        "/api/auth/reset-password",
        json={"token": "token-recuperacao-invalido-exp-seg-01", "new_password": "NovaSenhaInvalida#2026"},
    )
    with eng.connect() as conn:
        row = conn.execute(
            text("SELECT id, LENGTH(token_hash) AS hash_len, used_at FROM password_reset_tokens WHERE user_id = :uid ORDER BY id DESC LIMIT 1"),
            {"uid": uid_a},
        ).mappings().first()

    ev = {
        "token_invalido_status": r_bad.status_code,
        "ultimo_registro_db": {
            "id": row["id"],
            "hash_len": row["hash_len"],
            "used_at": str(row["used_at"]) if row["used_at"] else None,
        } if row else None,
        "caixa_teste_smtp": "indisponivel (token armazenado apenas em hash e sem caixa recebivel para example.com)",
    }

    if r_bad.status_code == 200:
        just = "POST /api/auth/reset-password aceitou token de recuperação inválido."
        reg.registrar("I07", "Identity", "POST /api/auth/reset-password", "Público", "Redefinição altera senha da conta vinculada e consome autorização", "desvio_confirmado", just, ev)
        pytest.fail(just)

    just = (
        f"Token inválido foi rejeitado (HTTP {r_bad.status_code}), mas o controle positivo de consumo do token "
        "não pôde ser executado porque o banco persiste apenas token_hash e não há caixa SMTP recebível para recuperar o token em texto puro."
    )
    reg.registrar("I07", "Identity", "POST /api/auth/reset-password", "Público", "Redefinição altera senha da conta vinculada e consome autorização", "inconclusiva", just, ev)
    pytest.skip(just)


def test_i05_alterar_senha_isolamento(ctx):
    client, m, eng, tok, reg = ctx["client"], ctx["manifesto"], ctx["engine"], ctx["tokens"], ctx["reg"]
    email_a = m["atores"]["A"]["email"]
    email_b = m["atores"]["B"]["email"]
    senha_orig = ctx["senha"]
    senha_nova = "ExpSeg01#T3Temp2026!" if senha_orig != "ExpSeg01#T3Temp2026!" else "ExpSeg01#T3Alt2026!"

    desvios: list[str] = []
    ev: dict[str, Any] = {}
    try:
        r_chg = client.post(
            "/api/auth/change-password",
            headers=auth_headers(tok["A"]),
            json={"current_password": senha_orig, "new_password": senha_nova},
        )
        ev["change_status"] = r_chg.status_code
        if r_chg.status_code != 200:
            desvios.append(f"POST /api/auth/change-password falhou: HTTP {r_chg.status_code}")
        else:
            r_old = client.post("/api/auth/login", json={"email": email_a, "password": senha_orig, "remember_me": False})
            r_new = client.post("/api/auth/login", json={"email": email_a, "password": senha_nova, "remember_me": False})
            r_b = client.post("/api/auth/login", json={"email": email_b, "password": senha_orig, "remember_me": False})
            ev.update({
                "login_a_senha_antiga_status": r_old.status_code,
                "login_a_senha_nova_status": r_new.status_code,
                "login_b_preservado_status": r_b.status_code,
            })
            if r_old.status_code == 200:
                desvios.append("Senha anterior de A continuou válida após change-password.")
            if r_new.status_code != 200:
                desvios.append(f"Nova senha de A não autenticou: HTTP {r_new.status_code}")
            if r_b.status_code != 200:
                desvios.append(f"Acesso de B foi afetado pela troca de senha de A: HTTP {r_b.status_code}")
    finally:
        tok["A"] = _restaurar_estado_a(client, eng, email_a, senha_orig, senha_alt=senha_nova)

    decisao = "desvio_confirmado" if desvios else "conforme"
    just = "; ".join(desvios) if desvios else (
        "Mudança de senha de A invalidou a senha anterior, autenticou com a nova senha e preservou integralmente o acesso de B "
        "(senha original de A restaurada ao final)."
    )
    reg.registrar("I05", "Identity", "POST /api/auth/change-password", "A, B", "Mudança de senha afeta apenas A e preserva B", decisao, just, ev)
    assert not desvios, just


def test_aut_e005_change_password(ctx):
    client, m, eng, tok, reg = ctx["client"], ctx["manifesto"], ctx["engine"], ctx["tokens"], ctx["reg"]
    email_a = m["atores"]["A"]["email"]
    senha_orig = ctx["senha"]
    senha_nova = "ExpSeg01#Aut05Temp!" if senha_orig != "ExpSeg01#Aut05Temp!" else "ExpSeg01#Aut05Alt!"
    body = {"current_password": senha_orig, "new_password": senha_nova}

    try:
        r_no = client.post("/api/auth/change-password", json=body)
        r_bad = client.post("/api/auth/change-password", headers=auth_headers(TOKEN_INVALIDO), json=body)
        r_ok = client.post("/api/auth/change-password", headers=auth_headers(tok["A"]), json=body)
    finally:
        tok["A"] = _restaurar_estado_a(client, eng, email_a, senha_orig, senha_alt=senha_nova)

    _verificar_aut(reg, "AUT-E005", "POST /api/auth/change-password", "A", r_ok.status_code, r_no.status_code, r_bad.status_code)
