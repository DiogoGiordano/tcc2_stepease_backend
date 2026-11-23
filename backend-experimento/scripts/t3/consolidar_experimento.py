"""Consolida T1 (Bandit), T2 (Schemathesis + ZAP) e T3 (Pytest + HTTPX) para M1, M2 e M3 do EXP-SEG-01."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT_DIR / "results"

UNIDADES_DOMINIO = (
    [f"I{i:02d}" for i in range(1, 15)]
    + [f"P{i:02d}" for i in range(1, 9)]
    + [f"C{i:02d}" for i in range(1, 7)]
)
UNIDADES_AUT = [
    "AUT-E003", "AUT-E004", "AUT-E005", "AUT-E008", "AUT-E009", "AUT-E010",
    "AUT-E011", "AUT-E012", "AUT-E013", "AUT-E014", "AUT-E015", "AUT-E026",
    "AUT-E028", "AUT-E031", "AUT-E032", "AUT-E033", "AUT-E034", "AUT-E035",
    "AUT-E036", "AUT-E037", "AUT-E038", "AUT-E039",
]
UNIDADES_CACHE = ["CACHE-E003", "CACHE-E015"]
UNIDADES_EST = ["EST-E006", "EST-E012"]
CATALOGO_54 = UNIDADES_DOMINIO + UNIDADES_AUT + UNIDADES_CACHE + UNIDADES_EST

ROTAS_AUT: dict[str, tuple[str, str]] = {
    "AUT-E003": ("GET", "/api/auth/me"),
    "AUT-E004": ("POST", "/api/auth/logout"),
    "AUT-E005": ("POST", "/api/auth/change-password"),
    "AUT-E008": ("POST", "/api/2fa/enable/google"),
    "AUT-E009": ("POST", "/api/2fa/confirm/google"),
    "AUT-E010": ("POST", "/api/2fa/verify/google"),
    "AUT-E011": ("POST", "/api/2fa/enable/email"),
    "AUT-E012": ("POST", "/api/2fa/send/email"),
    "AUT-E013": ("POST", "/api/2fa/verify/email"),
    "AUT-E014": ("POST", "/api/2fa/disable"),
    "AUT-E015": ("GET", "/api/2fa/status"),
    "AUT-E026": ("POST", "/api/products/"),
    "AUT-E028": ("GET", "/api/products/me"),
    "AUT-E031": ("PUT", "/api/products/"),
    "AUT-E032": ("PATCH", "/api/products/"),
    "AUT-E033": ("DELETE", "/api/products/"),
    "AUT-E034": ("GET", "/api/cart/"),
    "AUT-E035": ("DELETE", "/api/cart/"),
    "AUT-E036": ("POST", "/api/cart/items"),
    "AUT-E037": ("POST", "/api/cart/items/bulk"),
    "AUT-E038": ("PATCH", "/api/cart/items/"),
    "AUT-E039": ("DELETE", "/api/cart/items/"),
}


def _carregar_t1() -> dict[str, dict[str, Any]]:
    pastas = sorted((ROOT_DIR / "experiment" / "experimento-seguranca" / "results").glob("t1-bandit-*"))
    if not pastas:
        return {u: {"decisao": "nao_executada", "origem": "T1-Bandit", "nota": "Pasta t1-bandit-* não localizada"} for u in UNIDADES_EST}

    pasta = pastas[-1]
    bandit_json = pasta / "bandit.json"
    dados = json.loads(bandit_json.read_text(encoding="utf-8"))
    alertas_b311 = [r for r in dados.get("results", []) if r.get("test_id") == "B311"]
    erros = dados.get("errors", [])
    arquivos = list(dados.get("metrics", {}).keys())

    res: dict[str, dict[str, Any]] = {}
    for uid in UNIDADES_EST:
        if erros:
            dec, nota = "inconclusiva", f"Bandit reportou erros de execução: {erros}"
        elif alertas_b311:
            dec, nota = "desvio_confirmado", f"{len(alertas_b311)} alerta(s) B311 no bandit.json"
        else:
            dec = "conforme"
            n_arqs = len(arquivos) - 1 if "_totals" in arquivos else len(arquivos)
            nota = f"Bandit B311 processou {n_arqs} arquivo(s) sem erros e com 0 alertas."
        res[uid] = {"decisao": dec, "origem": "T1-Bandit", "evidencia": str(bandit_json.relative_to(ROOT_DIR)), "nota": nota}
    return res


def _localizar_arquivos_t2a(unidade: str) -> tuple[Path | None, Path | None]:
    slug = unidade.lower()
    codigo = slug.replace("aut-", "")
    candidatos = [
        (RESULTS_DIR / "t2a" / slug / "relatorio.json", RESULTS_DIR / "t2a" / slug / "trafego.har"),
        (RESULTS_DIR / "t2a" / slug / f"t2a-{codigo}.json", RESULTS_DIR / "t2a" / slug / f"t2a-{codigo}.har"),
        (RESULTS_DIR / f"t2a-{codigo}-complemento.json", RESULTS_DIR / f"t2a-{codigo}-complemento.har"),
        (RESULTS_DIR / f"t2a-{codigo}.json", RESULTS_DIR / f"t2a-{codigo}.har"),
    ]
    for rel_p, har_p in candidatos:
        if rel_p.exists() and har_p.exists():
            return rel_p, har_p
    return None, None


def _carregar_t2a() -> tuple[dict[str, dict[str, Any]], list[str]]:
    res: dict[str, dict[str, Any]] = {}
    observacoes_adicionais: list[str] = []

    for uid in UNIDADES_AUT:
        rel_p, har_p = _localizar_arquivos_t2a(uid)
        if not rel_p or not har_p:
            res[uid] = {"decisao": "nao_executada", "origem": "T2A-Schemathesis", "nota": "Relatório/HAR não localizado."}
            continue

        rel = json.loads(rel_p.read_text(encoding="utf-8"))
        har = json.loads(har_p.read_text(encoding="utf-8"))
        metodo_esperado, prefixo_rota = ROTAS_AUT[uid]

        falhas = rel.get("failures", [])
        tested = rel.get("operations", {}).get("tested", 0)
        entries = har.get("log", {}).get("entries", [])

        ok_2xx = 0
        rej_sem_auth = 0
        rej_com_auth = 0
        erros_500 = 0

        for e in entries:
            req, resp = e.get("request", {}), e.get("response", {})
            if req.get("method") != metodo_esperado:
                continue
            url = req.get("url", "")
            if prefixo_rota not in url:
                continue
            st = resp.get("status", 0)
            tem_auth = any(h.get("name", "").lower() == "authorization" for h in req.get("headers", []))
            if 200 <= st < 300 and tem_auth:
                ok_2xx += 1
            elif st in (401, 403) and not tem_auth:
                rej_sem_auth += 1
            elif st in (401, 403) and tem_auth:
                rej_com_auth += 1
            elif st >= 500:
                erros_500 += 1

        if erros_500:
            observacoes_adicionais.append(
                f"T2A ({uid}): observada(s) {erros_500} resposta(s) HTTP 500 no HAR ({har_p.relative_to(ROOT_DIR)})."
            )

        if tested == 0:
            dec, nota = "nao_executada", "Schemathesis registrou Tested: 0."
        elif falhas:
            dec, nota = "desvio_confirmado", f"Schemathesis reportou {len(falhas)} falha(s) em ignored_auth."
        elif ok_2xx > 0 and rej_sem_auth > 0 and rej_com_auth > 0:
            dec = "conforme"
            nota = f"HAR registrou 2xx autenticado ({ok_2xx}x), 401/403 sem auth ({rej_sem_auth}x) e 401/403 credencial rejeitada ({rej_com_auth}x); 0 falhas."
        else:
            dec = "inconclusiva"
            nota = f"Sem controle positivo completo no HAR (2xx={ok_2xx}, 401_sem_auth={rej_sem_auth}, 401_rejeitada={rej_com_auth})."

        res[uid] = {
            "decisao": dec,
            "origem": "T2A-Schemathesis",
            "evidencia": f"{rel_p.relative_to(ROOT_DIR)}, {har_p.relative_to(ROOT_DIR)}",
            "nota": nota,
        }
    return res, observacoes_adicionais


def _carregar_t2b() -> tuple[dict[str, dict[str, Any]], list[str]]:
    res: dict[str, dict[str, Any]] = {}
    observacoes: list[str] = []
    ev_p = RESULTS_DIR / "t2b" / "evidencia-cache.json"
    rel_p = RESULTS_DIR / "t2b" / "relatorio-cache.json"

    mapa_rotas = {"CACHE-E003": "/api/auth/me", "CACHE-E015": "/api/2fa/status"}
    if not ev_p.exists():
        return {u: {"decisao": "nao_executada", "origem": "T2B-ZAP", "nota": "evidencia-cache.json não encontrado."} for u in UNIDADES_CACHE}, observacoes

    ev = json.loads(ev_p.read_text(encoding="utf-8"))
    por_rota = {c["rota"]: c for c in ev.get("capturas", [])}
    for uid, rota in mapa_rotas.items():
        cap = por_rota.get(rota)
        if not cap:
            res[uid] = {"decisao": "nao_executada", "origem": "T2B-ZAP", "nota": f"Rota {rota} não capturada pelo ZAP."}
        elif cap.get("status_http") == 200 and cap.get("contem_no_store"):
            res[uid] = {
                "decisao": "conforme",
                "origem": "T2B-ZAP",
                "evidencia": str(ev_p.relative_to(ROOT_DIR)),
                "nota": f"ZAP observou HTTP 200 com Cache-Control={cap.get('cache_control')} (no-store=True).",
            }
        elif cap.get("status_http") == 200:
            res[uid] = {
                "decisao": "desvio_confirmado",
                "origem": "T2B-ZAP",
                "evidencia": str(ev_p.relative_to(ROOT_DIR)),
                "nota": f"ZAP observou HTTP 200 sem diretiva no-store (Cache-Control={cap.get('cache_control')}).",
            }
        else:
            res[uid] = {
                "decisao": "inconclusiva",
                "origem": "T2B-ZAP",
                "evidencia": str(ev_p.relative_to(ROOT_DIR)),
                "nota": f"ZAP observou HTTP {cap.get('status_http')} em {rota}.",
            }

    if rel_p.exists():
        rel = json.loads(rel_p.read_text(encoding="utf-8"))
        for site in rel.get("site", []):
            for a in site.get("alerts", []):
                if not str(a.get("riskdesc", "")).startswith("Informational"):
                    observacoes.append(
                        f"T2B-ZAP alerta [{a.get('pluginid')}] {a.get('riskdesc')}: {a.get('name')} (x{a.get('count')})."
                    )
    return res, observacoes


def _carregar_t3() -> dict[str, dict[str, Any]]:
    res: dict[str, dict[str, Any]] = {}
    for nome in ("evidencias-products-cart.json", "evidencias-identity.json"):
        arq = RESULTS_DIR / "t3" / nome
        if not arq.exists():
            continue
        dados = json.loads(arq.read_text(encoding="utf-8"))
        for u in dados.get("unidades", []):
            res[u["unidade"]] = {
                "decisao": u["decisao"],
                "origem": "T3-Pytest+HTTPX",
                "evidencia": str(arq.relative_to(ROOT_DIR)),
                "nota": u["justificativa"],
            }
    return res


def _contabilizar_m3(unidades_planejadas: list[str], mapa: dict[str, dict[str, Any]]) -> dict[str, Any]:
    conforme = []
    desvio = []
    inconclusiva = []
    nao_executada = []
    for u in unidades_planejadas:
        dec = mapa.get(u, {}).get("decisao", "nao_executada")
        if dec == "conforme":
            conforme.append(u)
        elif dec == "desvio_confirmado":
            desvio.append(u)
        elif dec == "inconclusiva":
            inconclusiva.append(u)
        else:
            nao_executada.append(u)
    n = len(conforme) + len(desvio)
    total = len(unidades_planejadas)
    return {
        "n": n,
        "N": total,
        "fracao": f"{n}/{total}",
        "percentual": round((n / total) * 100, 1) if total else None,
        "conforme": conforme,
        "desvio_confirmado": desvio,
        "inconclusiva": inconclusiva,
        "nao_executada": nao_executada,
    }


def main() -> int:
    t1 = _carregar_t1()
    t2a, obs_t2a = _carregar_t2a()
    t2b, obs_t2b = _carregar_t2b()
    t2 = {**t2a, **t2b}
    t3 = _carregar_t3()

    plan_t1 = UNIDADES_EST
    plan_t2 = UNIDADES_AUT + UNIDADES_CACHE
    plan_t3 = UNIDADES_DOMINIO + UNIDADES_AUT + UNIDADES_CACHE

    m3_t1 = _contabilizar_m3(plan_t1, t1)
    m3_t2 = _contabilizar_m3(plan_t2, t2)
    m3_t3 = _contabilizar_m3(plan_t3, t3)

    intersecao_interpretavel = [
        u for u in plan_t2
        if t2.get(u, {}).get("decisao") in ("conforme", "desvio_confirmado")
        and t3.get(u, {}).get("decisao") in ("conforme", "desvio_confirmado")
    ]
    desvios_t1 = m3_t1["desvio_confirmado"]
    desvios_t2 = m3_t2["desvio_confirmado"]
    desvios_t3 = m3_t3["desvio_confirmado"]
    desvios_totais = sorted(set(desvios_t1 + desvios_t2 + desvios_t3))

    consolidacao = {
        "gerado_em_utc": datetime.now(timezone.utc).isoformat(),
        "estudo": "EXP-SEG-01",
        "m3": {"T1": m3_t1, "T2": m3_t2, "T3": m3_t3},
        "m1_desvios_unidades": {
            "T1": desvios_t1,
            "T2": desvios_t2,
            "T3": desvios_t3,
            "total_unidades_com_desvio": len(desvios_totais),
        },
        "m2_intersecao_t2_t3": {
            "planejadas_em_comum": len(plan_t2),
            "efetivamente_comparaveis": len(intersecao_interpretavel),
            "unidades_comparaveis": intersecao_interpretavel,
        },
        "observacoes_adicionais_fora_denominador": obs_t2a + obs_t2b,
        "matriz_54": [
            {
                "unidade": u,
                "T1": t1[u]["decisao"] if u in plan_t1 else "nao_aplicavel",
                "T2": t2.get(u, {}).get("decisao", "nao_executada") if u in plan_t2 else "nao_aplicavel",
                "T3": t3.get(u, {}).get("decisao", "nao_executada") if u in plan_t3 else "nao_aplicavel",
                "detalhe_T2": t2.get(u, {}).get("nota") if u in plan_t2 else None,
                "detalhe_T3": t3.get(u, {}).get("nota") if u in plan_t3 else None,
            }
            for u in CATALOGO_54
        ],
    }

    out_json = RESULTS_DIR / "consolidacao_exp_seg_01.json"
    out_json.write_text(json.dumps(consolidacao, ensure_ascii=False, indent=2), encoding="utf-8")

    linhas = [
        "# Consolidação EXP-SEG-01 (T1, T2 e T3)",
        "",
        "## Resumo M3 (Cobertura Interpretável)",
        "",
        "| Abordagem | n/N | % | Conformes | Desvios | Inconclusivas | Não executadas |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
        f"| **T1 (Bandit)** | {m3_t1['fracao']} | {m3_t1['percentual']}% | {len(m3_t1['conforme'])} | {len(m3_t1['desvio_confirmado'])} | {len(m3_t1['inconclusiva'])} | {len(m3_t1['nao_executada'])} |",
        f"| **T2 (Schemathesis + ZAP)** | {m3_t2['fracao']} | {m3_t2['percentual']}% | {len(m3_t2['conforme'])} | {len(m3_t2['desvio_confirmado'])} | {len(m3_t2['inconclusiva'])} | {len(m3_t2['nao_executada'])} |",
        f"| **T3 (Pytest + HTTPX)** | {m3_t3['fracao']} | {m3_t3['percentual']}% | {len(m3_t3['conforme'])} | {len(m3_t3['desvio_confirmado'])} | {len(m3_t3['inconclusiva'])} | {len(m3_t3['nao_executada'])} |",
        "",
        "## Interseção Comparável T2 × T3 (M2)",
        "- Planejadas em comum: **24** (22 AUT + 2 CACHE)",
        f"- Efetivamente comparáveis: **{len(intersecao_interpretavel)}/24**",
        f"- Inconclusivas em T2: {', '.join(m3_t2['inconclusiva']) or 'nenhuma'}",
        f"- Inconclusivas em T3: {', '.join(m3_t3['inconclusiva']) or 'nenhuma'}",
        "",
        "## Sinais Adicionais (fora do denominador M3)",
    ]
    for obs in consolidacao["observacoes_adicionais_fora_denominador"] or ["Nenhum sinal adicional registrado."]:
        linhas.append(f"- {obs}")

    linhas += [
        "",
        "## Matriz Completa (54 Unidades)",
        "",
        "| Unidade | T1 | T2 | T3 |",
        "| :--- | :--- | :--- | :--- |",
    ]
    for row in consolidacao["matriz_54"]:
        linhas.append(f"| {row['unidade']} | {row['T1']} | {row['T2']} | {row['T3']} |")

    out_md = RESULTS_DIR / "consolidacao_exp_seg_01.md"
    out_md.write_text("\n".join(linhas) + "\n", encoding="utf-8")

    print("=" * 72)
    print("CONSOLIDAÇÃO EXP-SEG-01 GERADA COM SUCESSO")
    print("=" * 72)
    print(f"T1 (Bandit):             M3 = {m3_t1['fracao']} | desvios={len(desvios_t1)} | inconclusivas={m3_t1['inconclusiva']}")
    print(f"T2 (Schemathesis + ZAP): M3 = {m3_t2['fracao']} | desvios={len(desvios_t2)} | inconclusivas={m3_t2['inconclusiva']}")
    print(f"T3 (Pytest + HTTPX):     M3 = {m3_t3['fracao']} | desvios={len(desvios_t3)} | inconclusivas={m3_t3['inconclusiva']}")
    print(f"Interseção T2 × T3:      {len(intersecao_interpretavel)}/24 unidades efetivamente comparáveis")
    print(f"Desvios confirmados:     {desvios_totais or 'nenhum (0)'}")
    print("-" * 72)
    print("Observações adicionais:")
    for obs in consolidacao["observacoes_adicionais_fora_denominador"]:
        print("  -", obs)
    print("-" * 72)
    print(f"JSON salvo em: {out_json.relative_to(ROOT_DIR)}")
    print(f"MD salvo em:   {out_md.relative_to(ROOT_DIR)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
