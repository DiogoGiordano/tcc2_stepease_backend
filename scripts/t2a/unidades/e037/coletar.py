"""Coleta T2A (Schemathesis) — AUT-E037 (POST /api/cart/items/bulk)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[4]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from ..comum import (  # noqa: E402
    ContextoT2A,
    UnidadeAUT,
    criar_contexto_cli,
    imprimir_resultado_unidade,
)
from ..contrato import gerar_contrato_isolado  # noqa: E402
from ..runner import rodar_schemathesis  # noqa: E402

UNIDADE = UnidadeAUT(
    codigo="E037",
    modulo="Cart",
    metodo="POST",
    rota="/api/cart/items/bulk",
    prefixo_har="/api/cart/items/bulk",
    fase="examples",
    perfil="A",
)


def executar(ctx: ContextoT2A) -> dict:
    """Gera contrato isolado com lista contendo P1 (quantity=1) e executa AUT-E037."""
    token_a = ctx.token_de_a()
    p1 = ctx.obter_produto_p1()
    pasta = ctx.pasta_unidade(UNIDADE)
    contrato = gerar_contrato_isolado(
        destino=pasta / "contrato.json",
        unidade=UNIDADE,
        escopo_path=ctx.escopo_path,
        json_example=[{"product_id": p1["id"], "quantity": 1}],
    )
    return rodar_schemathesis(
        unidade=UNIDADE,
        contrato_path=contrato,
        api_url=ctx.api,
        token=token_a,
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
