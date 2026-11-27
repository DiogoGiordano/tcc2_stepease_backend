"""Orquestrador da coleta Schemathesis (T2A) — chama cada unidade em sua própria pasta.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from getpass import getpass
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from .comum import (  # noqa: E402
    API_PADRAO,
    CONFERENCIA_SCRIPT,
    DEFAULT_SAIDA_DIR,
    OPENAPI_SCOPE_PATH,
    ContextoT2A,
    imprimir_resultado_unidade,
)

BLOCOS: dict[str, tuple[str, ...]] = {
    "leitura": ("E003", "E015", "E028", "E034"),
    "products": ("E028", "E031", "E032", "E026", "E033"),
    "cart": ("E034", "E038", "E036", "E037", "E039", "E035"),
    "identity": ("E003", "E015", "E004", "E014", "E008", "E009", "E010", "E011", "E012", "E013", "E005"),
    "todos": (
        "E003", "E015", "E028", "E034",
        "E031", "E032", "E026", "E033",
        "E038", "E036", "E037", "E039", "E035",
        "E004", "E014", "E008", "E009", "E010", "E011", "E012", "E013", "E005",
    ),
}

TODOS_IDS = set(BLOCOS["todos"])


def carregar_modulo_unidade(codigo: str):
    """Importa dinamicamente scripts.t2a.eXXX.coletar."""
    cod = codigo.upper().replace("AUT-", "")
    if cod not in TODOS_IDS:
        raise ValueError(f"Unidade AUT desconhecida: {codigo}")
    return importlib.import_module(f"scripts.t2a.unidades.{cod.lower()}.coletar")

def _rodar_conferencia() -> bool:
    if not CONFERENCIA_SCRIPT.exists():
        return True
    print("Conferindo contrato e inventário via scripts/t2a/executar_t2a.py...", flush=True)
    return subprocess.run([sys.executable, str(CONFERENCIA_SCRIPT)], cwd=ROOT_DIR).returncode == 0


def _salvar_resumo(resultados: list[dict[str, Any]], saida_dir: Path) -> None:
    contagem: dict[str, int] = {}
    sinais_500: list[str] = []

    print("\n" + "=" * 84)
    print(f"RESUMO DA COLETA T2A — SCHEMATHESIS ({len(resultados)} UNIDADES)")
    print("=" * 84)
    for r in resultados:
        dec = r["decisao"]
        contagem[dec] = contagem.get(dec, 0) + 1
        if r.get("erros_500"):
            sinais_500.append(f"{r['unidade']} ({r['operacao']}): {r['erros_500']}x HTTP 500")
        imprimir_resultado_unidade(r)

    print("-" * 84)
    print("Contagem:", contagem)
    if sinais_500:
        print("Sinais adicionais (fora do denominador M3):", "; ".join(sinais_500))

    resumo_path = saida_dir / "resumo-schemathesis.json"
    resumo_path.parent.mkdir(parents=True, exist_ok=True)
    resumo_path.write_text(
        json.dumps(
            {
                "gerado_em_utc": datetime.now(timezone.utc).isoformat(),
                "total_unidades": len(resultados),
                "contagem": contagem,
                "sinais_adicionais_500": sinais_500,
                "unidades": resultados,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Resumo salvo em: {resumo_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "unidades",
        nargs="*",
        help="IDs opcionais na mesma sintaxe de unidades/executar.py (ex.: E003 E015 E028).",
    )
    parser.add_argument("--bloco", choices=tuple(BLOCOS.keys()), default="todos", help="Bloco padrão quando nenhum ID é passado.")
    parser.add_argument("--api", default=API_PADRAO, help=f"URL base da API (padrão: {API_PADRAO}).")
    parser.add_argument("--escopo", type=Path, default=OPENAPI_SCOPE_PATH, help="Contrato OpenAPI reduzido.")
    parser.add_argument("--saida", type=Path, default=DEFAULT_SAIDA_DIR, help="Pasta raiz de saída (padrão: results/t2a).")
    parser.add_argument("--pular-conferencia", action="store_true", help="Não chama scripts/t2a/executar_t2a.py antes.")
    parser.add_argument("--otp-email", default=os.environ.get("OTP_EMAIL_E013"), help="Código OTP de 6 dígitos para E013 (opcional).")
    parser.add_argument("--restaurar-carrinho", action="store_true", help="Readiciona 1xP1 após E035.")
    args = parser.parse_args()

    if not args.pular_conferencia and not _rodar_conferencia():
        print("Conferência prévia falhou.", file=sys.stderr)
        return 1

    fila = [u.upper().replace("AUT-", "") for u in args.unidades] if args.unidades else list(BLOCOS[args.bloco])
    invalidas = [u for u in fila if u not in TODOS_IDS]
    if invalidas:
        print(f"Unidades inválidas: {', '.join(invalidas)}", file=sys.stderr)
        return 2

    token_a = os.environ.get("TOKEN_A", "").strip() or None
    token_v1 = os.environ.get("TOKEN_V1", "").strip() or None
    senha = (os.environ.get("SENHA_EXP") or os.environ.get("SENHA_A") or "").strip() or None
    precisa_senha = any(u in ("E005", "E010", "E012") for u in fila) or not (token_a and token_v1)
    if precisa_senha and not senha:
        senha = getpass("Senha das contas experimentais (A e V1): ").strip() or None

    saida = args.saida if args.saida.is_absolute() else (ROOT_DIR / args.saida)
    escopo = args.escopo if args.escopo.is_absolute() else (ROOT_DIR / args.escopo)

    ctx = ContextoT2A(
        api_url=args.api,
        saida_dir=saida,
        escopo_path=escopo,
        senha=senha,
        token_a=token_a,
        token_v1=token_v1,
        otp_email=args.otp_email,
        restaurar_carrinho=args.restaurar_carrinho,
    )

    resultados: list[dict[str, Any]] = []
    try:
        for cod in fila:
            mod = carregar_modulo_unidade(cod)
            u = mod.UNIDADE
            print(f"\n{'=' * 72}\n[{u.id_completo}] {u.include_name} | fase={u.fase} | perfil={u.perfil}\n{'=' * 72}")
            resultados.append(mod.executar(ctx))
    finally:
        ctx.fechar()

    _salvar_resumo(resultados, saida)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
