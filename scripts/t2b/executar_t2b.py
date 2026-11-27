"""Observa as duas respostas de cache da API local com ZAP em modo seguro."""
import argparse
import getpass
import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import requests

from hook_cache import ROTAS

RAIZ = Path(__file__).resolve().parents[2]
API = "http://127.0.0.1:8000"
IMAGEM = "ghcr.io/zaproxy/zaproxy:2.17.0"


def executar(destino):
    if destino.exists() and any(destino.iterdir()):
        raise SystemExit(f"Pasta ocupada: {destino}. Para outra rodada use --saida com uma pasta nova.")
    token = (os.getenv("TOKEN_A") or getpass.getpass("Access token de A: ")).strip()
    if not token:
        raise SystemExit("Token vazio.")
    with requests.Session() as cliente:
        cliente.trust_env = False
        me = cliente.get(API + ROTAS[0], headers={"Authorization": "Bearer " + token},
                         allow_redirects=False, timeout=10)
    if me.status_code != 200 or me.json().get("email") != "exp-seg-01-a@example.com":
        raise SystemExit("A sessão não corresponde à conta experimental A.")
    entrada = RAIZ / "results/openapi_scope.json"
    spec = json.loads(entrada.read_text(encoding="utf-8"))
    spec["paths"] = {r: {"get": spec["paths"][r]["get"]} for r in ROTAS}
    spec["servers"] = [{"url": API}]
    destino.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory() as tmp:
        pasta = Path(tmp)
        pasta.chmod(0o777)
        contrato = pasta / "contrato-cache.json"
        contrato.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
        shutil.copy(Path(__file__).with_name("hook_cache.py"), pasta)
        versao = subprocess.check_output(["docker", "run", "--rm", IMAGEM, "zap.sh", "-version"], text=True)
        cmd = ["docker", "run", "--rm", "--network", "host", "-v", f"{pasta}:/zap/wrk:rw",
               "-e", "ZAP_AUTH_HEADER_VALUE", "-e", "ZAP_AUTH_HEADER_SITE", IMAGEM, "zap-api-scan.py",
               "-t", contrato.name, "-f", "openapi", "-S", "-I", "--hook", "/zap/wrk/hook_cache.py",
               "-J", "relatorio-cache.json", "-r", "relatorio-cache.html"]
        env = dict(os.environ, ZAP_AUTH_HEADER_VALUE="Bearer " + token, ZAP_AUTH_HEADER_SITE="127.0.0.1")
        rc = subprocess.run(cmd, env=env).returncode
        nomes = [contrato.name, "relatorio-cache.json", "relatorio-cache.html", "evidencia-cache.json"]
        for nome in nomes:
            arq = pasta / nome
            if arq.is_file():
                (destino / nome).write_bytes(arq.read_bytes().replace(token.encode(), b"<REDACTED>"))
        (destino / "codigo_saida.txt").write_text(str(rc))
        (destino / "versao-zap.txt").write_text(versao)
        (destino / "data.txt").write_text(datetime.now().astimezone().isoformat())
        (destino / "commit.txt").write_bytes(subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=RAIZ))
        (destino / "entradas.sha256").write_text("".join(
            f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in (entrada, contrato)))
    print("Evidências:", destino)
    if rc or any(not (destino / n).is_file() for n in nomes):
        raise SystemExit(f"Rodada incompleta ou ZAP sinalizou falha (código {rc}). Confira os relatórios.")
    capturas = json.loads((destino / "evidencia-cache.json").read_text())["capturas"]
    for rota in ROTAS:
        validas = [c for c in capturas if c["rota"] == rota and c["authorization_presente"]
                   and c["status_http"] == 200]
        print(rota, "| respostas 200 autenticadas:", len(validas),
              "| Cache-Control:", [c["cache_control"] for c in validas])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--saida", type=Path, default=RAIZ / "results/t2b")
    executar(parser.parse_args().saida.resolve())
