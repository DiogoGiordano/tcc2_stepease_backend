"""Coleta T2A (Schemathesis) — AUT-E013 (POST /api/2fa/verify/email)."""

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
from ..suporte import auth_headers, consultar_otp_email_banco  # noqa: E402

UNIDADE = UnidadeAUT(
    codigo="E013",
    modulo="Identity",
    metodo="POST",
    rota="/api/2fa/verify/email",
    prefixo_har="/api/2fa/verify/email",
    fase="examples",
    perfil="A (desafio email)",
)


def executar(ctx: ContextoT2A) -> dict:
    """Executa AUT-E013 com OTP informado/localizado ou registra inconclusividade com '000000'."""
    token_a = ctx.token_de_a()
    otp_uso = (ctx.otp_email or "").strip() or None
    if not otp_uso and ctx.user_id_a is not None:
        otp_db, candidatos = consultar_otp_email_banco(ctx.user_id_a)
        if otp_db:
            otp_uso = otp_db
            print("[AUT-E013] Código OTP em texto puro localizado no banco.")
        else:
            detalhe = ", ".join(candidatos) or "sem colunas"
            print(f"[AUT-E013] OTP em texto puro indisponível ({detalhe}).")

    codigo_real = otp_uso is not None
    codigo_enviado = otp_uso or "000000"
    tok_uso = ctx.token_2fa_email or token_a

    pasta = ctx.pasta_unidade(UNIDADE)
    contrato = gerar_contrato_isolado(
        destino=pasta / "contrato.json",
        unidade=UNIDADE,
        escopo_path=ctx.escopo_path,
        json_example={"code": codigo_enviado},
    )
    try:
        return rodar_schemathesis(
            unidade=UNIDADE,
            contrato_path=contrato,
            api_url=ctx.api,
            token=tok_uso,
            pasta_saida=pasta,
        )
    finally:
        ctx.sessao.post(f"{ctx.api}/api/2fa/disable", headers=auth_headers(token_a), timeout=10)
        if codigo_real:
            sanitizar_artefatos(pasta, [codigo_enviado])


def main() -> int:
    ctx = criar_contexto_cli(__doc__ or "", precisa_otp=True)
    try:
        imprimir_resultado_unidade(executar(ctx))
    finally:
        ctx.fechar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
