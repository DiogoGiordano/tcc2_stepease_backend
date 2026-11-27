from .. import suporte
from ..comum import exigir

PERFIL = "A"


def executar(r):
    d = r.pedir("POST", "/api/2fa/disable")
    suporte.estado(d, None)
    suporte.estado(r.pedir("GET", "/api/2fa/status"), None)
    r.ctx.pop("google_confirmado", None)
    r.ctx.pop("segredo_totp", None)
    return {"habilitado": False}
