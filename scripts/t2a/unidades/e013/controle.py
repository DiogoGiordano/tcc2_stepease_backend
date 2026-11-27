from .. import suporte
from ..comum import exigir

PERFIL = "A"


def executar(r):
    code = suporte.segredo("Código recebido por e-mail (Enter se indisponível): ")
    if not code:
        raise suporte.Inconclusiva("Sem OTP recebido; verificação positiva não executada.")
    exigir(len(code) == 6 and code.isascii() and code.isdigit(), "Esperado um código de seis dígitos")
    return suporte.verificar(r, "email", code, suporte.desafio(r, "email"))
