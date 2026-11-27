"""Coleta T2A (Schemathesis) — AUT-E003 (GET /api/auth/me)."""

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

UNIDADE = UnidadeAUT(
    codigo="E003",
    modulo="Identity",
    metodo="GET",
    rota="/api/auth/me",
    prefixo_har="/api/auth/me",
    fase="coverage",
    perfil="A",
)


def executar(ctx: ContextoT2A) -> dict:
    """Executa a coleta ignored_auth na fase coverage para AUT-E003."""
    token = ctx.token_de_a()
    pasta = ctx.pasta_unidade(UNIDADE)
    return rodar_schemathesis(
        unidade=UNIDADE,
        contrato_path=ctx.escopo_path,
        api_url=ctx.api,
        token=token,
        pasta_saida=pasta,
        usar_include_name=True,
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
