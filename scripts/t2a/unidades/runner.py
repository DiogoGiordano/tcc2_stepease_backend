"""Execução do Schemathesis (ignored_auth) e classificação de evidências JSON + HAR."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from .comum import ROOT_DIR, UnidadeAUT


def resolver_schemathesis() -> str:
    """Localiza o binário do Schemathesis na .venv ativa ou no PATH."""
    na_venv = Path(sys.executable).parent / "schemathesis"
    if na_venv.exists():
        return str(na_venv)
    no_path = shutil.which("schemathesis")
    if no_path:
        return no_path
    raise RuntimeError(
        "Executável 'schemathesis' não encontrado. "
        "Instale na .venv com: python -m pip install 'schemathesis==4.33.4'"
    )


def rodar_schemathesis(
    unidade: UnidadeAUT,
    contrato_path: Path,
    api_url: str,
    token: str,
    pasta_saida: Path,
    usar_include_name: bool = False,
) -> dict[str, Any]:
    """Invoca o Schemathesis salvando relatorio.json e trafego.har e retorna o resumo classificado."""
    pasta_saida.mkdir(parents=True, exist_ok=True)
    rel_p = pasta_saida / "relatorio.json"
    har_p = pasta_saida / "trafego.har"

    cmd = [
        resolver_schemathesis(),
        "run",
        str(contrato_path),
        "--url",
        api_url.rstrip("/"),
        "-H",
        f"Authorization: Bearer {token.strip()}",
        "--phases",
        unidade.fase,
        "--checks",
        "ignored_auth",
        "--output-sanitize",
        "true",
        "--report",
        "json,har",
        "--report-json-path",
        str(rel_p),
        "--report-har-path",
        str(har_p),
    ]
    if usar_include_name:
        cmd.extend(["--include-name", unidade.include_name])
    if unidade.rate_limit:
        cmd.extend(["--rate-limit", unidade.rate_limit])

    subprocess.run(cmd, cwd=ROOT_DIR)
    return analisar_evidencia(unidade, rel_p, har_p)


def analisar_evidencia(
    unidade: UnidadeAUT,
    relatorio_path: Path,
    har_path: Path,
) -> dict[str, Any]:
    """Classifica a unidade AUT lendo relatorio.json e trafego.har."""
    if not relatorio_path.exists() or not har_path.exists():
        return {
            "unidade": unidade.id_completo,
            "modulo": unidade.modulo,
            "operacao": unidade.include_name,
            "fase": unidade.fase,
            "decisao": "nao_executada",
            "ok_2xx": 0,
            "rej_sem_auth": 0,
            "rej_com_auth": 0,
            "erros_422": 0,
            "erros_429": 0,
            "erros_500": 0,
            "falhas_schemathesis": 0,
            "nota": "Relatório JSON ou HAR ausente.",
            "linhas_http": [],
        }

    rel = json.loads(relatorio_path.read_text(encoding="utf-8"))
    har = json.loads(har_path.read_text(encoding="utf-8"))
    entries = har.get("log", {}).get("entries", [])

    ok_2xx = 0
    rej_sem_auth = 0
    rej_com_auth = 0
    erros_422 = 0
    erros_429 = 0
    erros_500 = 0
    linhas_http: list[str] = []

    for i, entry in enumerate(entries, 1):
        req, res = entry.get("request", {}), entry.get("response", {})
        if req.get("method") != unidade.metodo:
            continue
        url = req.get("url", "")
        if unidade.prefixo_har not in url:
            continue

        status = res.get("status", 0)
        auth_vals = [
            h.get("value", "")
            for h in req.get("headers", [])
            if h.get("name", "").lower() == "authorization"
        ]
        tem_auth = bool(auth_vals)

        if 200 <= status < 300 and tem_auth:
            ok_2xx += 1
        elif status in (401, 403) and not tem_auth:
            rej_sem_auth += 1
        elif status in (401, 403) and tem_auth:
            rej_com_auth += 1
        elif status == 422:
            erros_422 += 1
        elif status == 429:
            erros_429 += 1
        elif status >= 500:
            erros_500 += 1

        auth_txt = (
            "ausente"
            if not tem_auth
            else (f"presente ({auth_vals[0]})" if "[Filtered]" in auth_vals[0] else "presente (<REDACTED>)")
        )
        corpo = (res.get("content", {}).get("text") or "").replace("\n", " ")[:180]
        linhas_http.append(f"[{i}] {req.get('method')} {url} | Auth: {auth_txt} | HTTP {status} | {corpo}")

    tested = rel.get("operations", {}).get("tested", 0)
    falhas = rel.get("failures", [])

    if tested == 0:
        decisao = "nao_executada"
        nota = "Schemathesis registrou operations.tested = 0."
    elif falhas:
        decisao = "desvio_confirmado"
        nota = f"Schemathesis reportou {len(falhas)} falha(s) em ignored_auth."
    elif ok_2xx > 0 and rej_sem_auth > 0 and rej_com_auth > 0:
        decisao = "conforme"
        nota = (
            f"HAR confirmou 2xx autenticado ({ok_2xx}x), 401/403 sem auth ({rej_sem_auth}x) "
            f"e 401/403 credencial rejeitada ({rej_com_auth}x); 0 falhas."
        )
    else:
        decisao = "inconclusiva"
        nota = (
            f"Sem tríade completa no HAR (2xx={ok_2xx}, sem_auth={rej_sem_auth}, "
            f"rejeitada={rej_com_auth}, 422={erros_422}, 429={erros_429})."
        )

    return {
        "unidade": unidade.id_completo,
        "modulo": unidade.modulo,
        "operacao": unidade.include_name,
        "fase": unidade.fase,
        "decisao": decisao,
        "ok_2xx": ok_2xx,
        "rej_sem_auth": rej_sem_auth,
        "rej_com_auth": rej_com_auth,
        "erros_422": erros_422,
        "erros_429": erros_429,
        "erros_500": erros_500,
        "falhas_schemathesis": len(falhas),
        "seed": rel.get("seed"),
        "nota": nota,
        "linhas_http": linhas_http,
    }
