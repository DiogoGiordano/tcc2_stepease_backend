"""Gera contrato OpenAPI restrito aos pares (método, rota) do inventário.

Args:
    --input: Caminho do JSON completo.
    --config: Caminho da configuração das operações selecionadas.
    --output: Destino do contrato reduzido.

Returns:
    None: Persiste JSON do contrato reduzido.

Raises:
    ValueError: Operações ausentes ou contrato vazio.
    FileNotFoundError: Arquivos de entrada inexistentes.
"""
import argparse
import json
from pathlib import Path

METHODS = {'get', 'post', 'put', 'patch', 'delete', 'head', 'options', 'trace'}
ROOT = Path(__file__).resolve().parents[1]


def filter_contract(input_path: Path, config_path: Path, output_path: Path) -> int:
    """Filtra operações sem perder os componentes globais referenciados.

    Args:
        input_path: Contrato OpenAPI original.
        config_path: Relação de operações selecionadas.
        output_path: Destino do resultado.

    Returns:
        int: Quantidade de operações preservadas.

    Raises:
        ValueError: Operações selecionadas não são encontradas.
    """
    schema = json.loads(input_path.read_text(encoding='utf-8'))
    selection = json.loads(config_path.read_text(encoding='utf-8'))
    wanted = {(x['rota'], x['metodo'].lower()) for x in selection['operacoes']}
    found = set()
    filtered = {}
    for path, path_item in schema['paths'].items():
        operations = {}
        for key, data in path_item.items():
            if key.lower() in METHODS and (path, key.lower()) in wanted:
                operations[key] = data
                found.add((path, key.lower()))
        if operations:
            metadata = {key: data for key, data in path_item.items() if key.lower() not in METHODS}
            filtered[path] = {**metadata, **operations}
    missing = wanted - found
    if missing:
        raise ValueError(f'Operações ausentes do OpenAPI: {sorted(missing)}')
    if not found:
        raise ValueError('A seleção não contém operações válidas.')
    schema['paths'] = filtered
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return len(found)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT / 'results/openapi_full.json')
    parser.add_argument('--config', type=Path, default=ROOT / 'config/operacoes_escopo.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'results/openapi_scope.json')
    args = parser.parse_args()
    print(f'{filter_contract(args.input, args.config, args.output)} operações exportadas para {args.output}')
