"""Coleta T2A (Schemathesis) — AUT-E031 (PUT /api/products/{product_id})."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[4]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import json  # noqa: E402

from ..comum import (  # noqa: E402
    ContextoT2A,
    UnidadeAUT,
    criar_contexto_cli,
    imprimir_resultado_unidade,
)
from ..contrato import gerar_contrato_isolado  # noqa: E402
from ..runner import rodar_schemathesis  # noqa: E402

UNIDADE = UnidadeAUT(
    codigo="E031",
    modulo="Products",
    metodo="PUT",
    rota="/api/products/{product_id}",
    prefixo_har="/api/products/",
    fase="examples",
    perfil="V1",
)


def executar(ctx: ContextoT2A) -> dict:
    """Gera contrato isolado com P1 (preservando o nome atual) e executa AUT-E031."""
    token_v1 = ctx.token_de_v1()
    p1 = ctx.obter_produto_p1(usar_rota_vendedor=True)
    pasta = ctx.pasta_unidade(UNIDADE)
    contrato = gerar_contrato_isolado(
        destino=pasta / "contrato.json",
        unidade=UNIDADE,
        escopo_path=ctx.escopo_path,
        path_examples={"product_id": p1["id"]},
        multipart_example={"data": json.dumps({"name": p1["name"]}, ensure_ascii=False)},
    )
    return rodar_schemathesis(
        unidade=UNIDADE,
        contrato_path=contrato,
        api_url=ctx.api,
        token=token_v1,
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
