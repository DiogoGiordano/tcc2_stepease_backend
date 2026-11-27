from .. import suporte
from ..comum import exigir

PERFIL = "A"


def executar(r):
    atual = suporte.senha(r)
    temporaria = suporte.segredo("Senha temporária de A (guarde até a restauração): ")
    exigir(temporaria != atual and 8 <= len(temporaria.encode()) <= 72, "Senha temporária inválida")
    rota = "/api/auth/change-password"
    res = r.pedir("POST", rota, json={"current_password": atual, "new_password": temporaria})
    exigir(res["success"] is True, "Troca de senha não confirmada")
    print("Senha temporária aplicada. Restaurando a original.")
    try:
        res = r.pedir("POST", rota, json={"current_password": temporaria, "new_password": atual})
        exigir(res["success"] is True, "Restauração não confirmada")
    except Exception as erro:
        raise ValueError("Confira a senha atual de A: a restauração não foi confirmada.") from erro
    return {"senha_restaurada": True}
