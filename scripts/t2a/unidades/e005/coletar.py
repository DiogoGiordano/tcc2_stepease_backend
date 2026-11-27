"""Coleta T2A (Schemathesis) — AUT-E005 (POST /api/auth/change-password)."""

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
from ..suporte import auth_headers, login_local  # noqa: E402

UNIDADE = UnidadeAUT(
    codigo="E005",
    modulo="Identity",
    metodo="POST",
    rota="/api/auth/change-password",
    prefixo_har="/api/auth/change-password",
    fase="examples",
    perfil="A",
)


def executar(ctx: ContextoT2A) -> dict:
    """Testa troca de senha via contrato isolado, restaura senha original e sanitiza evidências."""
    token_a = ctx.token_de_a()
    senha_atual = ctx.exigir_senha("AUT-E005 troca e restauração de senha de A")
    nova_senha = "ExpSeg01#Temp2026!" if senha_atual != "ExpSeg01#Temp2026!" else "ExpSeg01#Alt2026!"

    ctx.sessao.post(f"{ctx.api}/api/2fa/disable", headers=auth_headers(token_a), timeout=10)
    pasta = ctx.pasta_unidade(UNIDADE)
    contrato = gerar_contrato_isolado(
        destino=pasta / "contrato.json",
        unidade=UNIDADE,
        escopo_path=ctx.escopo_path,
        json_example={"current_password": senha_atual, "new_password": nova_senha},
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
        r_rest = ctx.sessao.post(
            f"{ctx.api}/api/auth/change-password",
            headers=auth_headers(token_a),
            json={"current_password": nova_senha, "new_password": senha_atual},
            timeout=10,
        )
        if r_rest.status_code != 200:
            try:
                tok_nova = login_local(ctx.sessao, ctx.api, EMAIL_A, nova_senha).get("access_token")
                if tok_nova:
                    r_rest = ctx.sessao.post(
                        f"{ctx.api}/api/auth/change-password",
                        headers=auth_headers(tok_nova),
                        json={"current_password": nova_senha, "new_password": senha_atual},
                        timeout=10,
                    )
            except RuntimeError:
                pass
        check = ctx.sessao.post(
            f"{ctx.api}/api/auth/login",
            json={"email": EMAIL_A, "password": senha_atual, "remember_me": False},
            timeout=10,
        )
        print(f"[AUT-E005] Restauração senha -> HTTP {r_rest.status_code} | Login original -> HTTP {check.status_code}")
        sanitizar_artefatos(pasta, [senha_atual, nova_senha])


def main() -> int:
    ctx = criar_contexto_cli(__doc__ or "")
    try:
        imprimir_resultado_unidade(executar(ctx))
    finally:
        ctx.fechar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
