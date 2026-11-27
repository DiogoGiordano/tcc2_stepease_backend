"""Coleta T2A (Schemathesis) — AUT-E035 (DELETE /api/cart/)."""

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
from ..runner import rodar_schemathesis  # noqa: E402
from ..suporte import auth_headers  # noqa: E402

UNIDADE = UnidadeAUT(
    codigo="E035",
    modulo="Cart",
    metodo="DELETE",
    rota="/api/cart/",
    prefixo_har="/api/cart/",
    fase="coverage",
    perfil="A",
    rate_limit="2/s",
)


def executar(ctx: ContextoT2A) -> dict:
    """Executa AUT-E035 (esvazia o carrinho de A) e opcionalmente restaura 1xP1."""
    token_a = ctx.token_de_a()
    pasta = ctx.pasta_unidade(UNIDADE)
    res = rodar_schemathesis(
        unidade=UNIDADE,
        contrato_path=ctx.escopo_path,
        api_url=ctx.api,
        token=token_a,
        pasta_saida=pasta,
        usar_include_name=True,
    )
    if ctx.restaurar_carrinho:
        p1 = ctx.obter_produto_p1()
        ctx.sessao.post(
            f"{ctx.api}/api/cart/items",
            headers=auth_headers(token_a),
            json={"product_id": p1["id"], "quantity": 1},
            timeout=10,
        )
    return res


def main() -> int:
    ctx = criar_contexto_cli(__doc__ or "", aceita_restaurar_carrinho=True)
    try:
        imprimir_resultado_unidade(executar(ctx))
    finally:
        ctx.fechar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
