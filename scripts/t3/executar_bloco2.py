"""Executa o Bloco 2 do T3 (Identity — 27 unidades) e imprime o resumo consolidado."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from getpass import getpass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT_DIR / "results" / "t3"
EVIDENCIAS_PATH = RESULTS_DIR / "evidencias-identity.json"
JUNIT_PATH = RESULTS_DIR / "junit-identity.xml"
TEST_FILE = ROOT_DIR / "scripts" / "t3" / "test_identity.py"


def main() -> int:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    senha = os.environ.get("SENHA_EXP") or os.environ.get("SENHA_A")
    if not senha:
        senha = getpass("Senha das 4 contas experimentais (A, B, V1, V2): ")
    if not senha.strip():
        raise SystemExit("Senha vazia. Execução cancelada.")

    env = os.environ.copy()
    env["SENHA_EXP"] = senha
    py_path = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{ROOT_DIR}{os.pathsep}{py_path}" if py_path else str(ROOT_DIR)

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-v",
        "-rs",
        str(TEST_FILE),
        f"--junitxml={JUNIT_PATH}",
    ]
    resultado = subprocess.run(cmd, cwd=ROOT_DIR, env=env)

    print("\n" + "=" * 72)
    if not EVIDENCIAS_PATH.exists():
        print(f"Arquivo de evidências não encontrado: {EVIDENCIAS_PATH}")
        return resultado.returncode

    dados = json.loads(EVIDENCIAS_PATH.read_text(encoding="utf-8"))
    unidades = dados.get("unidades", [])
    contagem: dict[str, int] = {}
    print(f"RESUMO T3 — BLOCO 2 ({len(unidades)}/27 UNIDADES)")
    print("=" * 72)
    for u in unidades:
        dec = u["decisao"]
        contagem[dec] = contagem.get(dec, 0) + 1
        print(f"  {u['unidade']:10} | {dec:17} | {u['justificativa']}")
    print("-" * 72)
    print("Contagem:", contagem)
    print(f"Evidências salvas em: {EVIDENCIAS_PATH.relative_to(ROOT_DIR)}")
    print(f"Relatório JUnit em:   {JUNIT_PATH.relative_to(ROOT_DIR)}")
    return resultado.returncode


if __name__ == "__main__":
    raise SystemExit(main())
