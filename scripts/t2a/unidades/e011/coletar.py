"""Coleta T2A (Schemathesis) — AUT-E011 (POST /api/2fa/enable/email)."""

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
    codigo="E011",
    modulo="Identity",
    metodo="POST",
    rota="/api/2fa/enable/email",
    prefixo_har="/api/2fa/enable/email",
    fase="coverage",
    perfil="A",
    rate_limit="1/s",
)


def executar(ctx: ContextoT2A) -> dict:
    """Desativa 2FA prévio para transição limpa e executa AUT-E011 em fase coverage."""
    token_a = ctx.token_de_a()
    ctx.sessao.post(f"{ctx.api}/api/2fa/disable", headers=auth_headers(token_a), timeout=10)
    pasta = ctx.pasta_unidade(UNIDADE)
    return rodar_schemathesis(
        unidade=UNIDADE,
        contrato_path=ctx.escopo_path,
        api_url=ctx.api,
        token=token_a,
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
