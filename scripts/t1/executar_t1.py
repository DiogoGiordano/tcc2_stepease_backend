"""Executa Bandit B311 nas duas unidades estáticas do EXP-SEG-01."""
import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

RAIZ = Path(__file__).resolve().parents[2]
CASOS = Path("app/modules/identity/application/use_cases")
ALVOS = {
    "EST-E006": CASOS / "request_identity_password_reset.py",
    "EST-E012": CASOS / "send_identity_email_two_factor.py",
}
SAIDA = RAIZ / "experiment/experimento-seguranca/results"


def executar(backend):
    for caminho in ALVOS.values():
        if not (backend / caminho).is_file():
            raise ValueError(f"Arquivo ausente: {backend / caminho}. Confira --backend.")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=backend, text=True)
    bandit = [sys.executable, "-m", "bandit"]
    versao = subprocess.check_output([*bandit, "--version"], text=True)
    agora = datetime.now().astimezone()
    destino = SAIDA / agora.strftime("t1-bandit-%Y%m%d-%H%M%S-%f")
    SAIDA.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=SAIDA) as tmp:
        pasta = Path(tmp)
        hashes = []
        for caminho in ALVOS.values():
            digest = hashlib.sha256((backend / caminho).read_bytes()).hexdigest()
            hashes.append(f"{digest}  {caminho}")
        metadados = {
            "commit.txt": commit.strip(), "versao.txt": versao.strip(),
            "arquivos.sha256": "\n".join(hashes), "data.txt": agora.isoformat(),
        }
        relatorio = pasta / "bandit.json"
        processo = subprocess.run(
            [*bandit, "-t", "B311", "-f", "json", "-o", str(relatorio), *map(str, ALVOS.values())],
            cwd=backend,
        )
        metadados["codigo_saida.txt"] = str(processo.returncode)
        for nome, valor in metadados.items():
            (pasta / nome).write_text(valor + "\n", encoding="utf-8")
        dados = json.loads(relatorio.read_text(encoding="utf-8"))
        metricas = {
            (backend / nome).resolve(): m for nome, m in dados["metrics"].items()
            if nome != "_totals"
        }
        completa = not dados["errors"]
        for unidade, caminho in ALVOS.items():
            alvo = (backend / caminho).resolve()
            if alvo not in metricas:
                completa = False
                print(f"{unidade}: arquivo ausente nas métricas")
                continue
            alertas = sum(
                achado["test_id"] == "B311" and (backend / achado["filename"]).resolve() == alvo
                for achado in dados["results"]
            )
            print(f"{unidade}: {metricas[alvo]['loc']} linhas | {alertas} alerta(s) B311")
        pasta.rename(destino)
    print(f"Evidências: {destino}")
    return processo.returncode if completa else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", type=Path, default=RAIZ / "backend",
                        help="Diretório do backend que contém app/ (padrão: backend/).")
    try:
        sys.exit(executar(parser.parse_args().backend.resolve()))
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as erro:
        print(f"T1 interrompido: {erro}", file=sys.stderr)
        sys.exit(2)
