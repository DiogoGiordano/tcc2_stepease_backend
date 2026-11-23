import argparse
import json
import sys
from http.client import HTTPException
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


RAIZ_PROJETO = Path(__file__).resolve().parents[2]
ESCOPO_PADRAO = RAIZ_PROJETO / "results" / "openapi_scope.json"
API_PADRAO = "http://127.0.0.1:8000"
TOTAL_ESPERADO = 29
METODOS_HTTP = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}


def extrair_operacoes(contrato):
    if not isinstance(contrato, dict) or not isinstance(contrato.get("paths"), dict):
        raise ValueError("O contrato precisa conter um objeto 'paths'.")

    operacoes = set()
    for caminho, definicao in contrato["paths"].items():
        if caminho.startswith("x-"):
            continue
        if not caminho.startswith("/") or not isinstance(definicao, dict):
            raise ValueError(f"Entrada inválida em 'paths': {caminho}")

        for metodo in METODOS_HTTP.intersection(definicao):
            if not isinstance(definicao[metodo], dict):
                raise ValueError(f"Operação inválida: {metodo.upper()} {caminho}")
            operacoes.add((metodo.upper(), caminho))

    return operacoes


def main():
    parser = argparse.ArgumentParser(
        description="Confere as operações do escopo no OpenAPI publicado pela API."
    )
    parser.add_argument("--escopo", type=Path, default=ESCOPO_PADRAO)
    parser.add_argument("--api", default=API_PADRAO)
    args = parser.parse_args()

    print(f"Contrato de escopo: {args.escopo}")
    try:
        with args.escopo.open(encoding="utf-8") as arquivo:
            previstas = extrair_operacoes(json.load(arquivo))
    except (OSError, ValueError) as erro:
        print(f"Erro ao ler o contrato de escopo: {erro}", file=sys.stderr)
        return 2

    print(f"Operações no escopo: {len(previstas)}")
    if len(previstas) != TOTAL_ESPERADO:
        print(f"Conferência interrompida: o estudo prevê {TOTAL_ESPERADO} operações.")
        return 1

    url = f"{args.api.rstrip('/')}/openapi.json"
    print(f"Consultando: {url}")
    try:
        with urlopen(url, timeout=10) as resposta:
            publicadas = extrair_operacoes(json.load(resposta))
    except (URLError, OSError, HTTPException, ValueError) as erro:
        print(f"Erro ao obter o contrato da API: {erro}", file=sys.stderr)
        return 2

    ausentes = previstas - publicadas
    print(f"Operações do escopo publicadas: {len(previstas) - len(ausentes)}/{len(previstas)}")

    if ausentes:
        for metodo, caminho in sorted(ausentes):
            print(f"AUSENTE: {metodo} {caminho}")
        return 1

    print("OK: todas as operações do escopo constam no contrato publicado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())