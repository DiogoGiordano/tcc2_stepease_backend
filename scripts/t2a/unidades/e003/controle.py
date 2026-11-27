from scripts.t2a.unidades.comum import CLIENTE, EMAIL_A, exigir

PERFIL = "A"


def executar(r):
    d = r.pedir("GET", "/api/auth/me")
    exigir((d["id"], d["email"], d["type"]) == (CLIENTE, EMAIL_A, "client"), "Identidade inesperada")
    return {"user_id": d["id"], "tipo": d["type"]}
