from .. import suporte
from ..comum import exigir

PERFIL = "A"


def executar(r):
    code = suporte.totp(r)
    d = r.pedir("POST", "/api/2fa/confirm/google", json={"code": code})
    suporte.estado(d, "google")
    r.ctx["google_confirmado"] = True
    return {"metodo": "google"}
