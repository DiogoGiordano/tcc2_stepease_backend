from .. import suporte
from ..comum import exigir

PERFIL = "V1"


def executar(r):
    p = suporte.criar_produto(r)
    r.ctx["produto_descartavel"] = p
    return {"produto_criado": p["id"], "nome": p["name"], "loja": p["seller_id"]}
