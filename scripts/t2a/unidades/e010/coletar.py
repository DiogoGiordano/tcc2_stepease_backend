"""Coleta T2A (Schemathesis) — AUT-E010 (POST /api/2fa/verify/google)."""

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
from ..contrato import gerar_contrato_isolado, sanitizar_artefatos  # noqa: E402
from ..runner import rodar_schemathesis  # noqa: E402
from ..suporte import (  # noqa: E402
    aguardar_janela_totp,
    auth_headers,
    extrair_token_desafio,
    login_local,
    totp_now,
)

UNIDADE = UnidadeAUT(
    codigo="E010",
    modulo="Identity",
    metodo="POST",
    rota="/api/2fa/verify/google",
    prefixo_har="/api/2fa/verify/google",
    fase="examples",
    perfil="A (desafio google)",
)


def executar(ctx: ContextoT2A) -> dict:
    """Abre desafio de login 2FA Google, executa AUT-E010, desativa 2FA e sanitiza evidências."""
    token_a = ctx.token_de_a()
    senha = ctx.exigir_senha("AUT-E010 login com desafio 2FA Google")

    ctx.sessao.post(f"{ctx.api}/api/2fa/disable", headers=auth_headers(token_a), timeout=10).raise_for_status()
    en = ctx.sessao.post(f"{ctx.api}/api/2fa/enable/google", headers=auth_headers(token_a), timeout=10)
    en.raise_for_status()
    secret = en.json()["secret"]

    aguardar_janela_totp()
    ctx.sessao.post(
        f"{ctx.api}/api/2fa/confirm/google",
        headers=auth_headers(token_a),
        json={"code": totp_now(secret)},
        timeout=10,
    ).raise_for_status()

    dados_login = login_local(ctx.sessao, ctx.api, EMAIL_A, senha)
    tok_desafio = extrair_token_desafio(dados_login)
    if not dados_login.get("two_factor_required") or not tok_desafio:
        raise RuntimeError("Login de A com 2FA Google não retornou token de desafio.")

    aguardar_janela_totp()
    codigo = totp_now(secret)
    pasta = ctx.pasta_unidade(UNIDADE)
    contrato = gerar_contrato_isolado(
        destino=pasta / "contrato.json",
        unidade=UNIDADE,
        escopo_path=ctx.escopo_path,
        json_example={"code": codigo},
    )
    try:
        return rodar_schemathesis(
            unidade=UNIDADE,
            contrato_path=contrato,
            api_url=ctx.api,
            token=tok_desafio,
            pasta_saida=pasta,
        )
    finally:
        ctx.sessao.post(f"{ctx.api}/api/2fa/disable", headers=auth_headers(token_a), timeout=10)
        sanitizar_artefatos(pasta, [codigo, secret, tok_desafio])


def main() -> int:
    ctx = criar_contexto_cli(__doc__ or "")
    try:
        imprimir_resultado_unidade(executar(ctx))
    finally:
        ctx.fechar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
