"""Hook passivo chamado pelo ZAP antes do encerramento do API Scan."""
import json
from pathlib import Path
from urllib.parse import urlsplit

ROTAS = ("/api/auth/me", "/api/2fa/status")


def zap_pre_shutdown(zap):
    capturas = []
    inicio = 0
    while True:
        lote = zap.core.messages(start=inicio, count=100)
        if not isinstance(lote, list):
            raise RuntimeError("Resposta inválida ao consultar o histórico do ZAP.")
        if not lote:
            break
        for msg in lote:
            linhas = msg["requestHeader"].splitlines()
            metodo, endereco, _ = linhas[0].split(" ", 2)
            rota = urlsplit(endereco).path
            if metodo != "GET" or rota not in ROTAS:
                continue
            resposta = msg["responseHeader"].splitlines()
            if not resposta:
                continue
            cache = [s.partition(":")[2].strip() for s in resposta[1:]
                     if s.partition(":")[0].lower() == "cache-control"]
            diretivas = {d.strip().lower() for valor in cache for d in valor.split(",")}
            capturas.append({
                "rota": rota, "status_http": int(resposta[0].split()[1]),
                "authorization_presente": any(s.lower().startswith("authorization:") for s in linhas[1:]),
                "cache_control": cache, "contem_no_store": "no-store" in diretivas,
                "id_zap": msg["id"],
            })
        inicio += len(lote)
    destino = Path("/zap/wrk/evidencia-cache.json")
    destino.write_text(json.dumps({"capturas": capturas}, ensure_ascii=False, indent=2), encoding="utf-8")
