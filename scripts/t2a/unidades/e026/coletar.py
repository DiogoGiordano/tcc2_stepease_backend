"""Coleta T2A (Schemathesis) — AUT-E026 (POST /api/products/)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[4]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import base64  # noqa: E402
import json  # noqa: E402
from datetime import datetime  # noqa: E402

from ..comum import (  # noqa: E402
    ContextoT2A,
    UnidadeAUT,
    criar_contexto_cli,
    imprimir_resultado_unidade,
)
from ..contrato import gerar_contrato_isolado  # noqa: E402
from ..runner import rodar_schemathesis  # noqa: E402
from ..suporte import auth_headers, png_1x1  # noqa: E402

UNIDADE = UnidadeAUT(
    codigo="E026",
    modulo="Products",
    metodo="POST",
    rota="/api/products/",
    prefixo_har="/api/products/",
    fase="examples",
    perfil="V1",
)


def criar_produto_descartavel(ctx: ContextoT2A) -> dict:
    """Cria produto descartável via controle positivo HTTP (também usado como alvo da E033)."""
    token_v1 = ctx.token_de_v1()
    p1 = ctx.obter_produto_p1(usar_rota_vendedor=True)
    pasta = ctx.pasta_unidade(UNIDADE)

    img_bytes = png_1x1()
    (pasta / "amostra.png").write_bytes(img_bytes)

    ignorar = {"id", "seller_cep", "images", "image_url", "created_at", "updated_at"}
    payload = {k: v for k, v in p1.items() if k not in ignorar and v is not None}
    payload["name"] = "EXP-SEG-01 T2A E026"
    payload["image_alt"] = "Imagem de teste experimental E026"

    resp = ctx.sessao.post(
        f"{ctx.api}/api/products/",
        headers=auth_headers(token_v1),
        data={"data": json.dumps(payload, ensure_ascii=False)},
        files=[("images", ("amostra.png", img_bytes, "image/png"))],
        timeout=15,
        allow_redirects=False,
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Criação descartável E026 falhou: HTTP {resp.status_code} | {resp.text[:250]}")

    criado = resp.json()
    ficha = {
        "unidade": "AUT-E026",
        "perfil": "V1",
        "metodo": "POST",
        "rota": "/api/products/",
        "data_local": datetime.now().astimezone().isoformat(),
        "status": resp.status_code,
        "produto_criado_id": criado.get("id"),
        "loja_id": criado.get("seller_id"),
        "payload_data": payload,
        "controle_confirmado": True,
    }
    (pasta / "controle-positivo-coleta.json").write_text(
        json.dumps(ficha, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    ctx.produto_descartavel_id = criado.get("id")
    return ficha


def executar(ctx: ContextoT2A) -> dict:
    """Prepara contrato multipart da AUT-E026 e registra o comportamento no Schemathesis."""
    ficha = criar_produto_descartavel(ctx)
    pasta = ctx.pasta_unidade(UNIDADE)

    payload = dict(ficha["payload_data"])
    payload["name"] = "EXP-SEG-01 T2A E026 ST"
    img_b64 = base64.b64encode((pasta / "amostra.png").read_bytes()).decode("ascii")

    contrato = gerar_contrato_isolado(
        destino=pasta / "contrato.json",
        unidade=UNIDADE,
        escopo_path=ctx.escopo_path,
        multipart_example={"data": json.dumps(payload, ensure_ascii=False), "images": [img_b64]},
        multipart_encoding={"images": {"contentType": "image/png"}},
        images_base64=True,
    )
    return rodar_schemathesis(
        unidade=UNIDADE,
        contrato_path=contrato,
        api_url=ctx.api,
        token=ctx.token_de_v1(),
        pasta_saida=pasta,
    )


def main() -> int:
    ctx = criar_contexto_cli(__doc__ or "")
    try:
        imprimir_resultado_unidade(executar(ctx))
    finally:
        ctx.fechar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
