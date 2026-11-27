import json

from scripts.t2a.unidades.comum import exigir

PERFIL = "V1"


def executar(r):
    p = r.produto_proprio()
    campo = json.dumps({"name": p["name"]}, ensure_ascii=False)
    rota = f"/api/products/{p['id']}"
    d = r.pedir("PUT", rota, files={"data": (None, campo)})
    exigir(all(d[k] == p[k] for k in ("name", "id", "seller_id")), "Produto divergente após a atualização")
    return {"produto": d["id"], "loja": d["seller_id"], "nome": d["name"]}
