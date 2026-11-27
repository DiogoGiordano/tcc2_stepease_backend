from scripts.t2a.unidades.comum import METODO_2FA, exigir

PERFIL = "A"


def executar(r):
    d = r.pedir("GET", "/api/2fa/status")
    exigir(METODO_2FA in ("desativado", "email", "google"), "METODO_2FA desconhecido")
    metodo = None if METODO_2FA == "desativado" else METODO_2FA
    exigir(d["two_factor_enabled"] is (metodo is not None) and d["two_factor_method"] == metodo,
           f"Esperado: habilitado={metodo is not None}, método={metodo!r}. "
f"API retornou: habilitado={d['two_factor_enabled']!r}, método={d['two_factor_method']!r}")
    return {"metodo": metodo, "habilitado": d["two_factor_enabled"]}
