PERFIL = "V1"


def executar(r):
    produto = r.produto_proprio()
    return {"produto": produto["id"], "loja": produto["seller_id"]}
