from .. import suporte
from ..comum import exigir

PERFIL = "A"


def executar(r):
    antes = r.carrinho()
    r.pedir("DELETE", "/api/cart/", 204)
    depois = r.carrinho()
    exigir(depois["id"] == antes["id"] and depois["items"] == [], "Limpeza não confirmada")
    return {"carrinho": depois["id"], "itens_antes": len(antes["items"]), "itens_depois": 0}
