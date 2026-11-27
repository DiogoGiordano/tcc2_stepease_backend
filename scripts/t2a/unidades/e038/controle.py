from scripts.t2a.unidades.comum import P1, exigir

PERFIL = "A"


def executar(r):
    c = r.carrinho()
    item = next((i for i in c["items"] if i["product_id"] == P1), None)
    exigir(item is not None, "Carrinho de A não contém P1")
    d = r.pedir("PATCH", f"/api/cart/items/{item['id']}", json={"quantity": item["quantity"]})
    exigir(all(d[k] == item[k] for k in ("id", "product_id", "quantity")), "Item ou quantidade divergente")
    return {"item": d["id"], "quantidade": d["quantity"]}
