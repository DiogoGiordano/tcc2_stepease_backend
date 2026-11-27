from scripts.t2a.unidades.comum import CLIENTE, EMAIL_A, exigir

PERFIL = "A"


def executar(r):
    d = r.pedir("GET", "/api/auth/me")
    exigir((d["id"], d["email"]) == (CLIENTE, EMAIL_A), "Sessão diferente de A")
    resposta = r.pedir("POST", "/api/auth/logout")
    exigir(isinstance(resposta.get("message"), str) and resposta["message"].strip(), "Mensagem de logout ausente")
    return {"user_id": d["id"], "mensagem": resposta["message"]}
