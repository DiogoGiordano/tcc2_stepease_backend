from .. import suporte
from ..comum import exigir

PERFIL = "A"


def executar(r):
    auth = suporte.desafio(r, "email")
    d = r.pedir("POST", "/api/2fa/send/email", headers=auth)
    exigir(d["success"] is True, "Envio não aceito pela API")
    return {"solicitacao_aceita": True}
