import json
import re
from pathlib import Path

def _sanitizar_req(header: str) -> str:
    linhas = []
    for line in header.splitlines():
        if line.lower().startswith("authorization:"):
            linhas.append("Authorization: <REDACTED>")
        else:
            linhas.append(line)
    return "\n".join(linhas)

def _extrair_status_e_headers(res_header: str):
    linhas = res_header.splitlines()
    status = None
    if linhas:
        m = re.match(r"HTTP/\S+\s+(\d{3})", linhas[0])
        if m:
            status = int(m.group(1))
    headers = {}
    for line in linhas[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            headers.setdefault(k.strip().lower(), []).append(v.strip())
    return status, headers

def zap_pre_shutdown(zap):
    out = Path("/zap/wrk/evidencia-cache.json")
    try:
        msgs = zap.core.messages(start=0, count=500)
        capturas = []
        for msg in msgs:
            req_h = msg.get("requestHeader", "")
            res_h = msg.get("responseHeader", "")
            primeira = req_h.splitlines()[0] if req_h else ""
            if not primeira.startswith("GET "):
                continue
            alvo = None
            for rota in ("/api/auth/me", "/api/2fa/status"):
                if f" {rota} " in primeira or f"http://127.0.0.1:8000{rota} " in primeira:
                    alvo = rota
                    break
            if not alvo:
                continue
            status, headers = _extrair_status_e_headers(res_h)
            cc_vals = headers.get("cache-control", [])
            cc_joined = ", ".join(cc_vals)
            diretivas = [d.strip().lower() for d in cc_joined.split(",") if d.strip()]
            capturas.append({
                "id_zap": msg.get("id"),
                "rota": alvo,
                "request_line": primeira,
                "authorization_presente": "authorization:" in req_h.lower(),
                "status_http": status,
                "cache_control": cc_vals,
                "contem_no_store": "no-store" in diretivas,
                "request_header_sanitizado": _sanitizar_req(req_h),
                "response_header": res_h,
            })
        out.write_text(json.dumps({"total_mensagens_zap": len(msgs), "capturas": capturas}, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        Path("/zap/wrk/hook-erro.txt").write_text(repr(exc), encoding="utf-8")
