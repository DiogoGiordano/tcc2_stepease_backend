from .. import suporte
from ..comum import exigir

PERFIL = "A"


def executar(r):
    auth = suporte.desafio(r, "google")
    return suporte.verificar(r, "google", suporte.totp(r), auth)
