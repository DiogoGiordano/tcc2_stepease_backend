"""Coleta T2A (Schemathesis) — AUT-E033 (DELETE /api/products/{product_id})."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[4]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from ..e026.coletar import criar_produto_descartavel
from ..comum import (
    ContextoT2A,
    UnidadeAUT,
    criar_contexto_cli,
    imprimir_resultado_unidade,
)
from ..contrato import gerar_contrato_isolado
from ..runner import rodar_schemathesis

UNIDADE = UnidadeAUT(
    codigo="E033",
    modulo="Products",
    metodo="DELETE",
    rota="/api/products/{product_id}",
    prefixo_har="/api/products/",
    fase="examples",
    perfil="V1",
)


def executar(ctx: ContextoT2A) -> dict:
    """Exclui o produto descartável criado na E026 (ou cria um novo se rodado isolado), protegendo P1."""
    token_v1 = ctx.token_de_v1()
    p1 = ctx.obter_produto_p1(usar_rota_vendedor=True)
    alvo_id = ctx.produto_descartavel_id
    if not alvo_id or alvo_id == p1["id"]:
        alvo_id = criar_produto_descartavel(ctx)["produto_criado_id"]
    if alvo_id == p1["id"]:
        raise RuntimeError(f"Abortado: recusa excluir produto de referência P1 (id={p1['id']}).")

    pasta = ctx.pasta_unidade(UNIDADE)
    contrato = gerar_contrato_isolado(
        destino=pasta / "contrato.json",
        unidade=UNIDADE,
        escopo_path=ctx.escopo_path,
        path_examples={"product_id": alvo_id},
    )
    res = rodar_schemathesis(
        unidade=UNIDADE,
        contrato_path=contrato,
        api_url=ctx.api,
        token=token_v1,
        pasta_saida=pasta,
    )
    ctx.produto_descartavel_id = None
    return res


def main() -> int:
    ctx = criar_contexto_cli(__doc__ or "")
    try:
        imprimir_resultado_unidade(executar(ctx))
    finally:
        ctx.fechar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
