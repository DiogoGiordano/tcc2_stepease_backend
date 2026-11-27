"""Coleta T2A (Schemathesis) — AUT-E012 (POST /api/2fa/send/email)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[4]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from ..comum import (  # noqa: E402
    EMAIL_A,
    ContextoT2A,
    UnidadeAUT,
    criar_contexto_cli,
    imprimir_resultado_unidade,
)
from ..runner import rodar_schemathesis  # noqa: E402
from ..suporte import auth_headers, extrair_token_desafio, login_local  # noqa: E402

UNIDADE = UnidadeAUT(
    codigo="E012",
    modulo="Identity",
    metodo="POST",
    rota="/api/2fa/send/email",
    prefixo_har="/api/2fa/send/email",
    fase="coverage",
    perfil="A (desafio email)",
    rate_limit="1/s",
)


def executar(ctx: ContextoT2A) -> dict:
    """Ativa 2FA por e-mail, obtém token de desafio e executa AUT-E012 em coverage."""
    token_a = ctx.token_de_a()
    senha = ctx.exigir_senha("AUT-E012 login com desafio 2FA e-mail")
    ctx.sessao.post(f"{ctx.api}/api/2fa/enable/email", headers=auth_headers(token_a), timeout=10).raise_for_status()

    dados_login = login_local(ctx.sessao, ctx.api, EMAIL_A, senha)
    tok_desafio = extrair_token_desafio(dados_login)
    if not dados_login.get("two_factor_required") or not tok_desafio:
        raise RuntimeError("Login de A com 2FA e-mail não retornou token de desafio.")
    ctx.token_2fa_email = tok_desafio

    pasta = ctx.pasta_unidade(UNIDADE)
    return rodar_schemathesis(
        unidade=UNIDADE,
        contrato_path=ctx.escopo_path,
        api_url=ctx.api,
        token=tok_desafio,
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
