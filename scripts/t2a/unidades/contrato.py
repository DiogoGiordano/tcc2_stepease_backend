"""Geração de contratos OpenAPI isolados por unidade e sanitização de artefatos."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .comum import UnidadeAUT


def gerar_contrato_isolado(
    destino: Path,
    unidade: UnidadeAUT,
    escopo_path: Path,
    path_examples: dict[str, Any] | None = None,
    json_example: Any = None,
    multipart_example: dict[str, Any] | None = None,
    multipart_encoding: dict[str, Any] | None = None,
    images_base64: bool = False,
) -> Path:
    """Cria cópia isolada do OpenAPI contendo apenas a operação alvo e seus exemplos explícitos."""
    if not escopo_path.exists():
        raise FileNotFoundError(
            f"Contrato de escopo não encontrado em {escopo_path}. "
            "Execute 'python scripts/filter_openapi_scope.py --input config/openapi.json' antes."
        )

    contrato = json.loads(escopo_path.read_text(encoding="utf-8"))
    caminho = contrato["paths"][unidade.rota]
    metodo_l = unidade.metodo.lower()
    operacao = caminho[metodo_l]

    if path_examples:
        params = caminho.get("parameters", []) + operacao.get("parameters", [])
        for nome, valor in path_examples.items():
            param = next((p for p in params if p.get("in") == "path" and p.get("name") == nome), None)
            if param is None:
                raise ValueError(f"Parâmetro de path '{nome}' ausente em {unidade.include_name}.")
            param["example"] = valor

    if json_example is not None:
        operacao["requestBody"]["content"]["application/json"]["example"] = json_example

    if multipart_example is not None:
        formulario = operacao["requestBody"]["content"]["multipart/form-data"]
        if multipart_encoding:
            formulario["encoding"] = multipart_encoding
        formulario["example"] = multipart_example
        if images_base64:
            schema_ref = (
                contrato.get("components", {})
                .get("schemas", {})
                .get("Body_create_product_api_products__post")
            )
            if schema_ref and "images" in schema_ref.get("properties", {}):
                schema_ref["properties"]["images"]["items"]["contentEncoding"] = "base64"
                schema_ref["properties"]["images"]["items"]["contentMediaType"] = "image/png"

    caminho_filtrado: dict[str, Any] = {metodo_l: operacao}
    if "parameters" in caminho:
        caminho_filtrado["parameters"] = caminho["parameters"]
    contrato["paths"] = {unidade.rota: caminho_filtrado}

    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(contrato, ensure_ascii=False, indent=2), encoding="utf-8")
    return destino


def extrair_secret_do_har(har_path: Path) -> str | None:
    """Extrai o último campo 'secret' retornado em HTTP 200 antes da sanitização do HAR."""
    if not har_path.exists():
        return None
    har = json.loads(har_path.read_text(encoding="utf-8"))
    secret = None
    for entry in har.get("log", {}).get("entries", []):
        if entry.get("request", {}).get("method") != "POST":
            continue
        if entry.get("response", {}).get("status") != 200:
            continue
        txt = entry.get("response", {}).get("content", {}).get("text") or ""
        try:
            corpo = json.loads(txt)
        except ValueError:
            continue
        if isinstance(corpo, dict) and corpo.get("secret"):
            secret = str(corpo["secret"])
    return secret


def sanitizar_artefatos(pasta: Path, segredos_literais: list[str] | None = None) -> None:
    """Remove senhas, códigos, secrets TOTP e tokens de contrato.json e trafego.har."""
    literais = [s for s in (segredos_literais or []) if s]

    for nome in ("contrato.json", "trafego.har"):
        arq = pasta / nome
        if not arq.exists():
            continue
        txt = arq.read_text(encoding="utf-8")
        for seg in literais:
            txt = txt.replace(seg, "<REDACTED>")
        try:
            obj = json.loads(txt)
        except ValueError:
            arq.write_text(txt, encoding="utf-8")
            continue

        if nome == "contrato.json":
            for path_item in obj.get("paths", {}).values():
                for op in path_item.values():
                    if not isinstance(op, dict):
                        continue
                    ex = (
                        op.get("requestBody", {})
                        .get("content", {})
                        .get("application/json", {})
                        .get("example")
                    )
                    if isinstance(ex, dict):
                        for k in ("code", "current_password", "new_password"):
                            if k in ex and ex[k] != "000000":
                                ex[k] = "<REDACTED>"
        else:
            for entry in obj.get("log", {}).get("entries", []):
                pd = entry.get("request", {}).get("postData")
                if isinstance(pd, dict) and isinstance(pd.get("text"), str):
                    try:
                        j = json.loads(pd["text"])
                        if isinstance(j, dict):
                            for k in ("code", "current_password", "new_password"):
                                if k in j and j[k] != "000000":
                                    j[k] = "<REDACTED>"
                            pd["text"] = json.dumps(j, ensure_ascii=False)
                    except ValueError:
                        pass
                rc = entry.get("response", {}).get("content")
                if isinstance(rc, dict) and isinstance(rc.get("text"), str):
                    try:
                        j = json.loads(rc["text"])
                        if isinstance(j, dict):
                            for k in ("access_token", "two_factor_token", "secret", "provisioning_uri"):
                                if j.get(k):
                                    j[k] = "<REDACTED>"
                            rc["text"] = json.dumps(j, ensure_ascii=False)
                    except ValueError:
                        pass

        arq.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
