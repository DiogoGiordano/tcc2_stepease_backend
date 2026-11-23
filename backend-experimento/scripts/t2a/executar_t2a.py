import csv
import json
import subprocess
import sys
from pathlib import Path

from conferir_contrato import extrair_operacoes


PASTA_SCRIPT = Path(__file__).resolve().parent
RAIZ = PASTA_SCRIPT.parents[1]
INVENTARIO = RAIZ / "config" / "inventario_rotas_escopo.csv"
ESCOPO = RAIZ / "results" / "openapi_scope.json"
API = "http://127.0.0.1:8000"

IDS_AUT = (
    "E003", "E004", "E005", "E008", "E009", "E010", "E011", "E012",
    "E013", "E014", "E015", "E026", "E028", "E031", "E032", "E033",
    "E034", "E035", "E036", "E037", "E038", "E039",
)


def conferir_unidades():
    with ESCOPO.open(encoding="utf-8") as arquivo:
        publicadas_no_escopo = extrair_operacoes(json.load(arquivo))

    unidades = {}
    with INVENTARIO.open(encoding="utf-8-sig", newline="") as arquivo:
        leitor = csv.DictReader(arquivo, delimiter=";")
        if not {"id", "metodo", "rota"}.issubset(leitor.fieldnames or []):
            raise ValueError(f"Cabeçalho inesperado em {INVENTARIO.name}")

        for linha in leitor:
            unidade = linha["id"].strip()
            if unidade not in IDS_AUT:
                continue
            if unidade in unidades:
                raise ValueError(f"ID duplicado no inventário: {unidade}")
            unidades[unidade] = (linha["metodo"].strip().upper(), linha["rota"].strip())

    conferidas = set()
    for unidade in IDS_AUT:
        if unidade not in unidades:
            raise ValueError(f"AUT-{unidade} ausente no inventário")
        operacao = unidades[unidade]
        metodo, rota = operacao
        if operacao not in publicadas_no_escopo:
            raise ValueError(f"AUT-{unidade} ausente no contrato: {metodo} {rota}")
        if operacao in conferidas:
            raise ValueError(f"Operação associada a dois IDs AUT: {metodo} {rota}")
        conferidas.add(operacao)
        print(f"AUT-{unidade}  {metodo:6} {rota}")

    print(f"Unidades AUT conferidas: {len(conferidas)}/{len(IDS_AUT)}")


def main():
    print("Conferindo o contrato publicado pela API...", flush=True)
    resultado = subprocess.run([
        sys.executable,
        str(PASTA_SCRIPT / "conferir_contrato.py"),
        "--escopo", str(ESCOPO),
        "--api", API,
    ])
    if resultado.returncode != 0:
        return resultado.returncode

    print(f"\nConferindo as unidades AUT em {INVENTARIO.name}...")
    try:
        conferir_unidades()
    except (OSError, ValueError, csv.Error) as erro:
        print(f"Conferência interrompida: {erro}", file=sys.stderr)
        return 1

    print("Preparação do T2A concluída. Coleta do Schemathesis pendente.")
    return 0


if __name__ == "__main__":
    sys.exit(main())