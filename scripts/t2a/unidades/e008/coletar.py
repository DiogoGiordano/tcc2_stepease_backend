"""Coleta T2A (Schemathesis) — AUT-E008 (POST /api/2fa/enable/google)."""

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
from ..contrato import extrair_secret_do_har, sanitizar_artefatos  # noqa: E402
from ..runner import rodar_schemathesis  # noqa: E402

UNIDADE = UnidadeAUT(
    codigo="E008",
    modulo="Identity",
    metodo="POST",
    rota="/api/2fa/enable/google",
    prefixo_har="/api/2fa/enable/google",
    fase="coverage",
    perfil="A",
    rate_limit="1/s",
)


def executar(ctx: ContextoT2A) -> dict:
    """Executa AUT-E008, guarda o secret TOTP em memória para E009 e sanitiza o HAR."""
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
    secret = extrair_secret_do_har(pasta / "trafego.har")
    if secret:
        ctx.google_secret = secret
    sanitizar_artefatos(pasta, [secret] if secret else None)
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
