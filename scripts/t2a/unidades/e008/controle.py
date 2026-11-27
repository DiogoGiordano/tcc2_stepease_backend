from .. import suporte
from ..comum import exigir

PERFIL = "A"


def executar(r):
    res = r.pedir("POST", "/api/2fa/enable/google")
    exigir(bool(res["secret"]) and res["provisioning_uri"].startswith("otpauth://"), "Configuração incompleta")
    r.ctx["segredo_totp"] = res["secret"]
    return {"configuracao_iniciada": True}
