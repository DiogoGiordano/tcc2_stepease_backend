"""Coleta T2A (Schemathesis) — AUT-E009 (POST /api/2fa/confirm/google)."""

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
from ..contrato import gerar_contrato_isolado, sanitizar_artefatos  # noqa: E402
from ..runner import rodar_schemathesis  # noqa: E402
from ..suporte import aguardar_janela_totp, auth_headers, totp_now  # noqa: E402

UNIDADE = UnidadeAUT(
    codigo="E009",
    modulo="Identity",
    metodo="POST",
    rota="/api/2fa/confirm/google",
    prefixo_har="/api/2fa/confirm/google",
    fase="examples",
    perfil="A",
)


def executar(ctx: ContextoT2A) -> dict:
    """Confirma 2FA Google usando o secret de E008 (ou gera novo se rodado isoladamente)."""
    token_a = ctx.token_de_a()
    if not ctx.google_secret:
        ctx.sessao.post(f"{ctx.api}/api/2fa/disable", headers=auth_headers(token_a), timeout=10)
        en = ctx.sessao.post(f"{ctx.api}/api/2fa/enable/google", headers=auth_headers(token_a), timeout=10)
        en.raise_for_status()
        ctx.google_secret = en.json()["secret"]

    aguardar_janela_totp()
    codigo = totp_now(ctx.google_secret)
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
            token=token_a,
            pasta_saida=pasta,
        )
    finally:
        sanitizar_artefatos(pasta, [codigo])


def main() -> int:
    ctx = criar_contexto_cli(__doc__ or "")
    try:
        imprimir_resultado_unidade(executar(ctx))
    finally:
        ctx.fechar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
