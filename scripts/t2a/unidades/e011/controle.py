from .. import suporte
from ..comum import exigir

PERFIL = "A"


def executar(r):
    if r.ctx.get("google_confirmado"):
        d = r.pedir("POST", "/api/2fa/disable")
        suporte.estado(d, None)
        r.ctx.pop("google_confirmado")
    d = r.pedir("POST", "/api/2fa/enable/email")
    suporte.estado(d, "email")
    return {"metodo": "email"}
