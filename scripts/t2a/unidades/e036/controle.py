from scripts.t2a.unidades.comum import P2, exigir

PERFIL = "A"


def executar(r):
    c = r.carrinho()
    antes = sum(i["quantity"] for i in c["items"] if i["product_id"] == P2)
    corpo = {"product_id": P2, "quantity": 1}
    d = r.pedir("POST", "/api/cart/items", 201, json=corpo)
    exigir(d["product_id"] == P2, "Produto devolvido diverge de P2")
    apos = sum(i["quantity"] for i in r.carrinho()["items"] if i["product_id"] == P2)
    exigir(apos == antes + 1, "A releitura não confirmou o acréscimo de uma unidade")
    return {"produto": P2, "antes": antes, "depois": apos}
