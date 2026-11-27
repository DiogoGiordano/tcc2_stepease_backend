from .. import suporte
from ..comum import exigir

PERFIL = "A"


def executar(r):
    c = r.carrinho()
    item = next((i for i in c["items"] if i["product_id"] == suporte.P2), None)
    if item is None:
        item = r.pedir("POST", "/api/cart/items", 201, json={"product_id": suporte.P2, "quantity": 1})
    exigir(item["product_id"] == suporte.P2, "Produto divergente")
    r.pedir("DELETE", f"/api/cart/items/{item['id']}", 204)
    exigir(all(i["id"] != item["id"] for i in r.carrinho()["items"]), "Item ainda presente")
    return {"item_removido": item["id"], "produto": suporte.P2}
