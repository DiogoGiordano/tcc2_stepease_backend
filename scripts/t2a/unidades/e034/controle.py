PERFIL = "A"


def executar(r):
    c = r.carrinho()
    return {"carrinho": c["id"], "titular": c["user_id"], "itens": len(c["items"])}
