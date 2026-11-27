from .. import suporte
from ..comum import exigir

PERFIL = "V1"


def executar(r):
    p = r.ctx.pop("produto_descartavel", None) or suporte.criar_produto(r)
    rota = f"/api/products/{p['id']}"
    atual = r.pedir("GET", rota)
    exigir(all(atual[k] == p[k] for k in ("id", "name", "seller_id")), "Produto descartável divergente")
    r.pedir("DELETE", rota, 204)
    r.pedir("GET", rota, 404)
    return {"produto_removido": p["id"]}
