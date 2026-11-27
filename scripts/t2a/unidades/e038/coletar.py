"""Coleta T2A (Schemathesis) — AUT-E038 (PATCH /api/cart/items/{item_id})."""

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
from ..suporte import auth_headers  # noqa: E402

UNIDADE = UnidadeAUT(
    codigo="E038",
    modulo="Cart",
    metodo="PATCH",
    rota="/api/cart/items/{item_id}",
    prefixo_har="/api/cart/items/",
    fase="examples",
    perfil="A",
)


def executar(ctx: ContextoT2A) -> dict:
    """Localiza o item atual de P1 no carrinho de A e executa AUT-E038 mantendo a quantidade."""
    token_a = ctx.token_de_a()
    p1 = ctx.obter_produto_p1()
    itens = ctx.obter_carrinho_a().get("items", [])
    if not itens:
        ctx.sessao.post(
            f"{ctx.api}/api/cart/items",
            headers=auth_headers(token_a),
            json={"product_id": p1["id"], "quantity": 1},
            timeout=10,
        ).raise_for_status()
        itens = ctx.obter_carrinho_a().get("items", [])

    item = next((i for i in itens if i.get("product_id") == p1["id"]), itens[0])
    pasta = ctx.pasta_unidade(UNIDADE)
    contrato = gerar_contrato_isolado(
        destino=pasta / "contrato.json",
        unidade=UNIDADE,
        escopo_path=ctx.escopo_path,
        path_examples={"item_id": item["id"]},
        json_example={"quantity": item["quantity"]},
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
