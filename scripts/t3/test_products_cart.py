"""T3 (Pytest + HTTPX) — Unidades de Products (13) e Cart (12) do protocolo EXP-SEG-01."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.t3.helpers import (  # noqa: E402
    API_BASE_URL,
    RESULTS_T3_DIR,
    RegistradorEvidencias,
    auth_headers,
    carregar_manifesto,
    carregar_openapi,
    criar_engine,
    db_produto_meta,
    limpar_produto_descartavel,
    login_ator,
    png_1x1,
)

EVIDENCIAS_PATH = RESULTS_T3_DIR / "evidencias-products-cart.json"
TOKEN_INVALIDO = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI5OTk5OSJ9.assinatura-invalida"


@pytest.fixture(scope="module")
def ctx():
    senha = os.environ.get("SENHA_EXP") or os.environ.get("SENHA_A")
    if not senha:
        pytest.fail(
            "Senha não informada. Execute via 'python scripts/t3/executar_bloco1.py' "
            "ou defina a variável de ambiente SENHA_EXP."
        )

    manifesto = carregar_manifesto()
    openapi = carregar_openapi()
    engine = criar_engine()
    reg = RegistradorEvidencias(EVIDENCIAS_PATH)

    client = httpx.Client(base_url=API_BASE_URL, timeout=15.0)
    tokens = {}
    for alias, info in manifesto["atores"].items():
        data = login_ator(client, info["email"], senha)
        tokens[alias] = data["access_token"]

    yield {
        "client": client,
        "manifesto": manifesto,
        "openapi": openapi,
        "engine": engine,
        "tokens": tokens,
        "reg": reg,
    }
    client.close()
    engine.dispose()


def _payload_produto_base(seller_id: int, nome: str) -> dict[str, Any]:
    return {
        "name": nome,
        "size": 40,
        "price": 100,
        "stock": 10,
        "seller_id": seller_id,
        "foot_type": "pair",
        "brand": "Piloto",
        "model": "T3",
        "category": "Casual",
        "color": "Preto",
        "gender": "Unissex",
        "age_group": "Adulto",
        "image_alt": "Imagem experimental T3",
    }


def _criar_produto_descartavel(client: httpx.Client, token: str, seller_id: int, nome: str) -> httpx.Response:
    payload = _payload_produto_base(seller_id, nome)
    return client.post(
        "/api/products/",
        headers=auth_headers(token),
        data={"data": json.dumps(payload, ensure_ascii=False)},
        files=[("images", ("amostra.png", png_1x1(), "image/png"))],
    )


def _obter_carrinho(client: httpx.Client, token: str) -> dict[str, Any]:
    r = client.get("/api/cart/", headers=auth_headers(token))
    assert r.status_code == 200, f"GET /api/cart/ falhou: HTTP {r.status_code}"
    return r.json()


def _resumo_itens_cart(cart: dict[str, Any]) -> list[tuple[int, int]]:
    return sorted((item["product_id"], item["quantity"]) for item in cart.get("items", []))




def test_p01_criar_produto_autorizacao_e_vinculo(ctx):
    client, m, eng, tok, reg = ctx["client"], ctx["manifesto"], ctx["engine"], ctx["tokens"], ctx["reg"]
    loja_v1, loja_v2 = m["lojas"]["V1"], m["lojas"]["V2"]
    uid_v1 = m["atores"]["V1"]["user_id"]

    criados: list[tuple[int, str | None]] = []
    desvios: list[str] = []
    ev: dict[str, Any] = {}
    try:
        r_v1 = _criar_produto_descartavel(client, tok["V1"], loja_v1, "EXP-SEG-01 T3 P01 V1")
        ev["v1_propria_loja_status"] = r_v1.status_code
        if r_v1.status_code in (200, 201):
            body_v1 = r_v1.json()
            pid_v1 = body_v1["id"]
            criados.append((pid_v1, tok["V1"]))
            meta = db_produto_meta(eng, pid_v1)
            ev["v1_criado_id"] = pid_v1
            ev["v1_persistido_seller_id"] = meta["seller_id"] if meta else None
            ev["v1_user_id"] = uid_v1
            if not meta or meta["seller_id"] != loja_v1 or meta["seller_id"] == uid_v1:
                desvios.append(f"Vínculo seller_id incorreto: {meta}")
        else:
            desvios.append(f"V1 não conseguiu criar produto próprio: HTTP {r_v1.status_code}")

        r_a = _criar_produto_descartavel(client, tok["A"], loja_v1, "EXP-SEG-01 T3 P01 CLIENTE_A")
        ev["cliente_a_status"] = r_a.status_code
        if r_a.status_code in (200, 201):
            pid_a = r_a.json().get("id")
            if pid_a:
                criados.append((pid_a, None))
            desvios.append(f"Cliente A criou produto sem perfil de vendedor (HTTP {r_a.status_code}, id={pid_a}).")

        r_cross = _criar_produto_descartavel(client, tok["V1"], loja_v2, "EXP-SEG-01 T3 P01 CROSS_V2")
        ev["v1_loja_v2_status"] = r_cross.status_code
        if r_cross.status_code in (200, 201):
            pid_cross = r_cross.json().get("id")
            if pid_cross:
                criados.append((pid_cross, tok["V2"]))
            meta_cross = db_produto_meta(eng, pid_cross) if pid_cross else None
            ev["v1_loja_v2_seller_id_persistido"] = meta_cross["seller_id"] if meta_cross else None
            if meta_cross and meta_cross["seller_id"] == loja_v2:
                desvios.append(f"V1 criou produto vinculado à loja de V2 (seller_id={loja_v2}, id={pid_cross}).")
    finally:
        for pid, owner_tok in criados:
            limpar_produto_descartavel(client, eng, pid, owner_tok)

    decisao = "desvio_confirmado" if desvios else "conforme"
    just = "; ".join(desvios) if desvios else (
        f"V1 criou produto vinculado a sellers.id={loja_v1} (distinto de users.id={uid_v1}); "
        "Cliente A e vínculo indevido à loja de V2 foram impedidos."
    )
    reg.registrar("P01", "Products", "POST /api/products/", "V1, A", "Criação vinculada à loja do vendedor autorizado", decisao, just, ev)
    assert not desvios, just


def test_p02_listar_catalogo_publico_e_campos(ctx):
    client, m, spec, reg = ctx["client"], ctx["manifesto"], ctx["openapi"], ctx["reg"]
    p1_id, p2_id = m["produtos"]["P1"]["id"], m["produtos"]["P2"]["id"]

    r = client.get("/api/products/", params={"limit": 100})
    assert r.status_code == 200
    dados = r.json()
    itens = dados if isinstance(dados, list) else dados.get("items", [])

    prod_props = set(spec["components"]["schemas"]["ProductResponse"]["properties"].keys())
    seller_props = set(spec["components"]["schemas"]["ProductSellerOut"]["properties"].keys())

    extras_prod: set[str] = set()
    extras_seller: set[str] = set()
    ids_retornados: set[int] = set()
    for prod in itens:
        if prod.get("id") is not None:
            ids_retornados.add(prod["id"])
        extras_prod |= set(prod.keys()) - prod_props
        if isinstance(prod.get("seller"), dict):
            extras_seller |= set(prod["seller"].keys()) - seller_props

    desvios: list[str] = []
    if p1_id not in ids_retornados or p2_id not in ids_retornados:
        desvios.append(f"P1 ({p1_id}) ou P2 ({p2_id}) ausentes no catálogo público.")
    if extras_prod:
        desvios.append(f"Campos fora de ProductResponse: {sorted(extras_prod)}")
    if extras_seller:
        desvios.append(f"Campos fora de ProductSellerOut: {sorted(extras_seller)}")

    ev = {
        "status": r.status_code,
        "total_retornados": len(itens),
        "p1_presente": p1_id in ids_retornados,
        "p2_presente": p2_id in ids_retornados,
        "extras_product": sorted(extras_prod),
        "extras_seller": sorted(extras_seller),
    }
    decisao = "desvio_confirmado" if desvios else "conforme"
    just = "; ".join(desvios) if desvios else "Catálogo público retornou P1 e P2 com todos os campos dentro de ProductResponse e ProductSellerOut."
    reg.registrar("P02", "Products", "GET /api/products/", "Público", "Catálogo público conforme ProductResponse e ProductSellerOut", decisao, just, ev)
    assert not desvios, just


def test_p03_listar_meus_produtos(ctx):
    client, m, tok, reg = ctx["client"], ctx["manifesto"], ctx["tokens"], ctx["reg"]
    p1_id, p2_id = m["produtos"]["P1"]["id"], m["produtos"]["P2"]["id"]
    loja_v1 = m["lojas"]["V1"]

    r_v1 = client.get("/api/products/me", headers=auth_headers(tok["V1"]))
    r_a = client.get("/api/products/me", headers=auth_headers(tok["A"]))

    desvios: list[str] = []
    ev: dict[str, Any] = {"v1_status": r_v1.status_code, "cliente_a_status": r_a.status_code}
    if r_v1.status_code != 200:
        desvios.append(f"GET /api/products/me de V1 retornou HTTP {r_v1.status_code}")
    else:
        dados = r_v1.json()
        prods = dados if isinstance(dados, list) else dados.get("items", [])
        ids = [p.get("id") for p in prods]
        sellers = sorted({p.get("seller_id") for p in prods})
        ev["v1_product_ids"] = ids
        ev["v1_seller_ids"] = sellers
        if p1_id not in ids:
            desvios.append(f"P1 ({p1_id}) ausente na lista de V1.")
        if p2_id in ids:
            desvios.append(f"P2 ({p2_id}) de V2 vazou na lista de V1.")
        if any(s != loja_v1 for s in sellers):
            desvios.append(f"Lista de V1 contém produtos de outra loja: {sellers}")

    if r_a.status_code == 200:
        dados_a = r_a.json()
        prods_a = dados_a if isinstance(dados_a, list) else dados_a.get("items", [])
        ev["cliente_a_total_itens"] = len(prods_a)
        if prods_a:
            desvios.append(f"Cliente A recebeu produtos em /api/products/me ({len(prods_a)} itens).")

    decisao = "desvio_confirmado" if desvios else "conforme"
    just = "; ".join(desvios) if desvios else f"Consulta de V1 incluiu P1 (loja {loja_v1}), excluiu P2 e não vazou dados para Cliente A."
    reg.registrar("P03", "Products", "GET /api/products/me", "V1, A", "Consulta de V1 inclui P1 e exclui P2", decisao, just, ev)
    assert not desvios, just


def test_p04_listar_por_vendedor(ctx):
    client, m, reg = ctx["client"], ctx["manifesto"], ctx["reg"]
    p1_id, p2_id = m["produtos"]["P1"]["id"], m["produtos"]["P2"]["id"]
    loja_v1 = m["lojas"]["V1"]

    r = client.get(f"/api/products/seller/{loja_v1}")
    desvios: list[str] = []
    ev: dict[str, Any] = {"status": r.status_code, "seller_id_consultado": loja_v1}
    if r.status_code != 200:
        desvios.append(f"GET /api/products/seller/{loja_v1} retornou HTTP {r.status_code}")
    else:
        dados = r.json()
        prods = dados if isinstance(dados, list) else dados.get("items", [])
        ids = [p.get("id") for p in prods]
        sellers = sorted({p.get("seller_id") for p in prods})
        ev["product_ids"] = ids
        ev["seller_ids"] = sellers
        if p1_id not in ids:
            desvios.append(f"P1 ({p1_id}) ausente no filtro por loja {loja_v1}.")
        if p2_id in ids:
            desvios.append(f"P2 ({p2_id}) apareceu no filtro de V1.")
        if any(s != loja_v1 for s in sellers):
            desvios.append(f"Produtos de outra loja retornados: {sellers}")

    decisao = "desvio_confirmado" if desvios else "conforme"
    just = "; ".join(desvios) if desvios else f"Filtro público por vendedor (loja {loja_v1}) retornou P1 e excluiu P2."
    reg.registrar("P04", "Products", "GET /api/products/seller/{seller_id}", "Público", "Filtro por vendedor retorna P1 e exclui P2", decisao, just, ev)
    assert not desvios, just


def test_p05_consultar_produto_publico(ctx):
    client, m, spec, reg = ctx["client"], ctx["manifesto"], ctx["openapi"], ctx["reg"]
    p1_id, loja_v1 = m["produtos"]["P1"]["id"], m["lojas"]["V1"]

    r = client.get(f"/api/products/{p1_id}")
    desvios: list[str] = []
    ev: dict[str, Any] = {"status": r.status_code, "product_id": p1_id}
    if r.status_code != 200:
        desvios.append(f"GET /api/products/{p1_id} retornou HTTP {r.status_code}")
    else:
        prod = r.json()
        prod_props = set(spec["components"]["schemas"]["ProductResponse"]["properties"].keys())
        seller_props = set(spec["components"]["schemas"]["ProductSellerOut"]["properties"].keys())
        extras_prod = sorted(set(prod.keys()) - prod_props)
        seller = prod.get("seller")
        extras_seller = sorted(set(seller.keys()) - seller_props) if isinstance(seller, dict) else []
        ev.update({
            "id_retornado": prod.get("id"),
            "seller_id_retornado": prod.get("seller_id"),
            "seller_presente": seller is not None,
            "extras_product": extras_prod,
            "extras_seller": extras_seller,
        })
        if prod.get("id") != p1_id or prod.get("seller_id") != loja_v1:
            desvios.append(f"Identidade divergente: id={prod.get('id')}, seller_id={prod.get('seller_id')}")
        if extras_prod:
            desvios.append(f"Campos fora de ProductResponse: {extras_prod}")
        if extras_seller:
            desvios.append(f"Campos fora de ProductSellerOut: {extras_seller}")

    decisao = "desvio_confirmado" if desvios else "conforme"
    just = "; ".join(desvios) if desvios else "Consulta pública de P1 retornou identidade correta e campos conformes ao contrato."
    reg.registrar("P05", "Products", "GET /api/products/{product_id}", "Público", "Identidade de P1 e representação pública prevista", decisao, just, ev)
    assert not desvios, just


def test_p06_atualizar_produto_put(ctx):
    client, m, eng, tok, reg = ctx["client"], ctx["manifesto"], ctx["engine"], ctx["tokens"], ctx["reg"]
    p1_id = m["produtos"]["P1"]["id"]
    antes = db_produto_meta(eng, p1_id)
    assert antes is not None
    nome_orig = antes["name"]

    desvios: list[str] = []
    ev: dict[str, Any] = {"antes": antes}
    try:
        r_v2 = client.put(
            f"/api/products/{p1_id}",
            headers=auth_headers(tok["V2"]),
            files={"data": (None, json.dumps({"name": "INDEVIDO V2 PUT"}))},
        )
        apos_v2 = db_produto_meta(eng, p1_id)
        ev["v2_status"] = r_v2.status_code
        if r_v2.status_code not in (401, 403, 404) or apos_v2["name"] != nome_orig or apos_v2["version"] != antes["version"]:
            desvios.append(f"V2 alterou ou não foi rejeitado em PUT P1: HTTP {r_v2.status_code}, meta={apos_v2}")

        r_a = client.put(
            f"/api/products/{p1_id}",
            headers=auth_headers(tok["A"]),
            files={"data": (None, json.dumps({"name": "INDEVIDO A PUT"}))},
        )
        apos_a = db_produto_meta(eng, p1_id)
        ev["cliente_a_status"] = r_a.status_code
        if r_a.status_code not in (401, 403, 404) or apos_a["name"] != nome_orig or apos_a["version"] != antes["version"]:
            desvios.append(f"Cliente A alterou ou não foi rejeitado em PUT P1: HTTP {r_a.status_code}, meta={apos_a}")

        novo_nome = "EXP-SEG-01 P1 PUT"
        r_v1 = client.put(
            f"/api/products/{p1_id}",
            headers=auth_headers(tok["V1"]),
            files={"data": (None, json.dumps({"name": novo_nome}))},
        )
        apos_v1 = db_produto_meta(eng, p1_id)
        ev["v1_status"] = r_v1.status_code
        ev["apos_v1"] = apos_v1
        if r_v1.status_code != 200 or apos_v1["name"] != novo_nome or apos_v1["seller_id"] != antes["seller_id"]:
            desvios.append(f"PUT autorizado de V1 falhou ou alterou proprietário: HTTP {r_v1.status_code}, meta={apos_v1}")
    finally:
        client.put(
            f"/api/products/{p1_id}",
            headers=auth_headers(tok["V1"]),
            files={"data": (None, json.dumps({"name": nome_orig}))},
        )

    decisao = "desvio_confirmado" if desvios else "conforme"
    just = "; ".join(desvios) if desvios else "PUT em P1 rejeitou V2 e A preservando P1/versão, e persistiu alteração legítima de V1 mantendo proprietário."
    reg.registrar("P06", "Products", "PUT /api/products/{product_id}", "V1, V2, A", "Atualização PUT restrita ao vendedor titular", decisao, just, ev)
    assert not desvios, just


def test_p07_atualizar_produto_patch(ctx):
    client, m, eng, tok, reg = ctx["client"], ctx["manifesto"], ctx["engine"], ctx["tokens"], ctx["reg"]
    p1_id = m["produtos"]["P1"]["id"]
    antes = db_produto_meta(eng, p1_id)
    assert antes is not None
    nome_orig = antes["name"]

    desvios: list[str] = []
    ev: dict[str, Any] = {"antes": antes}
    try:
        r_v2 = client.patch(
            f"/api/products/{p1_id}",
            headers=auth_headers(tok["V2"]),
            files={"data": (None, json.dumps({"name": "INDEVIDO V2 PATCH"}))},
        )
        apos_v2 = db_produto_meta(eng, p1_id)
        ev["v2_status"] = r_v2.status_code
        if r_v2.status_code not in (401, 403, 404) or apos_v2["name"] != nome_orig:
            desvios.append(f"V2 alterou ou não foi rejeitado em PATCH P1: HTTP {r_v2.status_code}, nome={apos_v2['name']}")

        r_a = client.patch(
            f"/api/products/{p1_id}",
            headers=auth_headers(tok["A"]),
            files={"data": (None, json.dumps({"name": "INDEVIDO A PATCH"}))},
        )
        apos_a = db_produto_meta(eng, p1_id)
        ev["cliente_a_status"] = r_a.status_code
        if r_a.status_code not in (401, 403, 404) or apos_a["name"] != nome_orig:
            desvios.append(f"Cliente A alterou ou não foi rejeitado em PATCH P1: HTTP {r_a.status_code}, nome={apos_a['name']}")

        novo_nome = "EXP-SEG-01 P1 PATCH"
        r_v1 = client.patch(
            f"/api/products/{p1_id}",
            headers=auth_headers(tok["V1"]),
            files={"data": (None, json.dumps({"name": novo_nome}))},
        )
        apos_v1 = db_produto_meta(eng, p1_id)
        ev["v1_status"] = r_v1.status_code
        ev["apos_v1"] = apos_v1
        if (
            r_v1.status_code != 200
            or apos_v1["name"] != novo_nome
            or apos_v1["price"] != antes["price"]
            or apos_v1["stock"] != antes["stock"]
            or apos_v1["seller_id"] != antes["seller_id"]
        ):
            desvios.append(f"PATCH autorizado de V1 divergiu: HTTP {r_v1.status_code}, antes={antes}, depois={apos_v1}")
    finally:
        client.patch(
            f"/api/products/{p1_id}",
            headers=auth_headers(tok["V1"]),
            files={"data": (None, json.dumps({"name": nome_orig}))},
        )

    decisao = "desvio_confirmado" if desvios else "conforme"
    just = "; ".join(desvios) if desvios else "PATCH em P1 rejeitou V2 e A, atualizou o campo solicitado por V1 e preservou preço, estoque e proprietário."
    reg.registrar("P07", "Products", "PATCH /api/products/{product_id}", "V1, V2, A", "Alteração parcial PATCH restrita ao titular preservando demais campos", decisao, just, ev)
    assert not desvios, just


def test_p08_excluir_produto(ctx):
    client, m, eng, tok, reg = ctx["client"], ctx["manifesto"], ctx["engine"], ctx["tokens"], ctx["reg"]
    loja_v1 = m["lojas"]["V1"]

    r_create = _criar_produto_descartavel(client, tok["V1"], loja_v1, "EXP-SEG-01 T3 P08 DESCARTAVEL")
    assert r_create.status_code in (200, 201), f"Setup P08 falhou: HTTP {r_create.status_code}"
    pid = r_create.json()["id"]

    desvios: list[str] = []
    ev: dict[str, Any] = {"produto_teste_id": pid}
    try:
        r_v2 = client.delete(f"/api/products/{pid}", headers=auth_headers(tok["V2"]))
        existe_apos_v2 = db_produto_meta(eng, pid) is not None
        ev["v2_status"] = r_v2.status_code
        ev["existe_apos_v2"] = existe_apos_v2
        if r_v2.status_code not in (401, 403, 404) or not existe_apos_v2:
            desvios.append(f"V2 excluiu ou não foi bloqueado em DELETE produto de V1: HTTP {r_v2.status_code}, existe={existe_apos_v2}")

        if existe_apos_v2:
            r_a = client.delete(f"/api/products/{pid}", headers=auth_headers(tok["A"]))
            existe_apos_a = db_produto_meta(eng, pid) is not None
            ev["cliente_a_status"] = r_a.status_code
            ev["existe_apos_a"] = existe_apos_a
            if r_a.status_code not in (401, 403, 404) or not existe_apos_a:
                desvios.append(f"Cliente A excluiu ou não foi bloqueado em DELETE produto de V1: HTTP {r_a.status_code}, existe={existe_apos_a}")

        if db_produto_meta(eng, pid) is not None:
            r_v1 = client.delete(f"/api/products/{pid}", headers=auth_headers(tok["V1"]))
            existe_apos_v1 = db_produto_meta(eng, pid) is not None
            ev["v1_status"] = r_v1.status_code
            ev["existe_apos_v1"] = existe_apos_v1
            if r_v1.status_code not in (200, 204) or existe_apos_v1:
                desvios.append(f"DELETE autorizado de V1 falhou: HTTP {r_v1.status_code}, existe={existe_apos_v1}")
    finally:
        limpar_produto_descartavel(client, eng, pid, tok["V1"])

    decisao = "desvio_confirmado" if desvios else "conforme"
    just = "; ".join(desvios) if desvios else "DELETE preservou o produto diante de V2 e A, e removeu o registro quando executado pelo titular V1."
    reg.registrar("P08", "Products", "DELETE /api/products/{product_id}", "V1, V2, A", "Exclusão restrita ao vendedor titular", decisao, just, ev)
    assert not desvios, just



def test_c01_consultar_carrinho_titularidade(ctx):
    client, m, tok, reg = ctx["client"], ctx["manifesto"], ctx["tokens"], ctx["reg"]
    cart_a = _obter_carrinho(client, tok["A"])
    cart_b = _obter_carrinho(client, tok["B"])

    desvios: list[str] = []
    if cart_a["user_id"] != m["atores"]["A"]["user_id"]:
        desvios.append(f"Carrinho de A retornou user_id={cart_a['user_id']}")
    if cart_b["user_id"] != m["atores"]["B"]["user_id"]:
        desvios.append(f"Carrinho de B retornou user_id={cart_b['user_id']}")
    if _resumo_itens_cart(cart_a) != [(m["produtos"]["P1"]["id"], 1)]:
        desvios.append(f"Itens iniciais de A divergiram: {_resumo_itens_cart(cart_a)}")
    if _resumo_itens_cart(cart_b) != [(m["produtos"]["P2"]["id"], 2)]:
        desvios.append(f"Itens iniciais de B divergiram: {_resumo_itens_cart(cart_b)}")

    ev = {
        "carrinho_ja_existia": True,
        "cart_a": {"id": cart_a["id"], "user_id": cart_a["user_id"], "itens": _resumo_itens_cart(cart_a)},
        "cart_b": {"id": cart_b["id"], "user_id": cart_b["user_id"], "itens": _resumo_itens_cart(cart_b)},
    }
    decisao = "desvio_confirmado" if desvios else "conforme"
    just = "; ".join(desvios) if desvios else "Consultas autenticadas retornaram os carrinhos pré-existentes e exclusivos de A (1xP1) e B (2xP2)."
    reg.registrar("C01", "Cart", "GET /api/cart/", "A, B", "Consulta retorna apenas o carrinho e itens do titular", decisao, just, ev)
    assert not desvios, just


def test_c03_adicionar_item_carrinho(ctx):
    client, m, tok, reg = ctx["client"], ctx["manifesto"], ctx["tokens"], ctx["reg"]
    p2_id = m["produtos"]["P2"]["id"]
    b_antes = _resumo_itens_cart(_obter_carrinho(client, tok["B"]))

    r = client.post("/api/cart/items", headers=auth_headers(tok["A"]), json={"product_id": p2_id, "quantity": 1})
    desvios: list[str] = []
    criado_item_id = None
    ev: dict[str, Any] = {"status": r.status_code, "b_antes": b_antes}
    try:
        if r.status_code not in (200, 201):
            desvios.append(f"POST /api/cart/items por A falhou: HTTP {r.status_code}")
        else:
            criado_item_id = r.json().get("id")
            a_depois = _resumo_itens_cart(_obter_carrinho(client, tok["A"]))
            b_depois = _resumo_itens_cart(_obter_carrinho(client, tok["B"]))
            ev.update({"a_depois": a_depois, "b_depois": b_depois})
            if (p2_id, 1) not in a_depois:
                desvios.append(f"Item P2 não persistiu no carrinho de A: {a_depois}")
            if b_depois != b_antes:
                desvios.append(f"Carrinho de B foi alterado: antes={b_antes}, depois={b_depois}")
    finally:
        if criado_item_id:
            client.delete(f"/api/cart/items/{criado_item_id}", headers=auth_headers(tok["A"]))

    decisao = "desvio_confirmado" if desvios else "conforme"
    just = "; ".join(desvios) if desvios else "Adição de item por A alterou somente o carrinho de A e preservou o carrinho de B."
    reg.registrar("C03", "Cart", "POST /api/cart/items", "A, B", "Adição altera apenas o carrinho do titular", decisao, just, ev)
    assert not desvios, just


def test_c04_adicionar_em_lote_carrinho(ctx):
    client, m, tok, reg = ctx["client"], ctx["manifesto"], ctx["tokens"], ctx["reg"]
    p1_id, p2_id = m["produtos"]["P1"]["id"], m["produtos"]["P2"]["id"]
    b_antes = _resumo_itens_cart(_obter_carrinho(client, tok["B"]))

    r = client.post(
        "/api/cart/items/bulk",
        headers=auth_headers(tok["A"]),
        json=[{"product_id": p1_id, "quantity": 1}, {"product_id": p2_id, "quantity": 1}],
    )
    desvios: list[str] = []
    ev: dict[str, Any] = {"status": r.status_code, "b_antes": b_antes}
    try:
        if r.status_code not in (200, 201):
            desvios.append(f"POST /api/cart/items/bulk falhou: HTTP {r.status_code}")
        else:
            a_depois = _resumo_itens_cart(_obter_carrinho(client, tok["A"]))
            b_depois = _resumo_itens_cart(_obter_carrinho(client, tok["B"]))
            ev.update({"a_depois": a_depois, "b_depois": b_depois})
            pids_a = {pid for pid, _ in a_depois}
            if {p1_id, p2_id} - pids_a:
                desvios.append(f"Itens do lote não vinculados ao carrinho de A: {a_depois}")
            if b_depois != b_antes:
                desvios.append(f"Carrinho de B foi alterado pelo lote de A: antes={b_antes}, depois={b_depois}")
    finally:
        for it in _obter_carrinho(client, tok["A"]).get("items", []):
            if it["product_id"] == p2_id:
                client.delete(f"/api/cart/items/{it['id']}", headers=auth_headers(tok["A"]))
            elif it["product_id"] == p1_id and it["quantity"] != 1:
                client.patch(f"/api/cart/items/{it['id']}", headers=auth_headers(tok["A"]), json={"quantity": 1})

    decisao = "desvio_confirmado" if desvios else "conforme"
    just = "; ".join(desvios) if desvios else "Lote submetido por A vinculou os itens apenas ao carrinho de A e preservou B."
    reg.registrar("C04", "Cart", "POST /api/cart/items/bulk", "A, B", "Lote vinculado exclusivamente ao carrinho do titular", decisao, just, ev)
    assert not desvios, just


def test_c05_alterar_item_carrinho_titularidade(ctx):
    client, m, tok, reg = ctx["client"], ctx["manifesto"], ctx["tokens"], ctx["reg"]
    cart_a = _obter_carrinho(client, tok["A"])
    if not cart_a["items"]:
        client.post("/api/cart/items", headers=auth_headers(tok["A"]), json={"product_id": m["produtos"]["P1"]["id"], "quantity": 1})
        cart_a = _obter_carrinho(client, tok["A"])

    item_a = cart_a["items"][0]
    item_id = item_a["id"]
    qtd_antes = item_a["quantity"]

    desvios: list[str] = []
    ev: dict[str, Any] = {"item_a_id": item_id, "qtd_antes": qtd_antes}
    try:
        # 1) B tenta alterar item do carrinho de A
        r_b = client.patch(f"/api/cart/items/{item_id}", headers=auth_headers(tok["B"]), json={"quantity": 5})
        qtd_apos_b = next(i["quantity"] for i in _obter_carrinho(client, tok["A"])["items"] if i["id"] == item_id)
        ev["b_status"] = r_b.status_code
        ev["qtd_apos_b"] = qtd_apos_b
        if r_b.status_code not in (401, 403, 404) or qtd_apos_b != qtd_antes:
            desvios.append(f"B alterou item de A: HTTP {r_b.status_code}, qtd_apos_b={qtd_apos_b}")

        # 2) A altera o próprio item
        nova_qtd = qtd_antes + 1
        r_a = client.patch(f"/api/cart/items/{item_id}", headers=auth_headers(tok["A"]), json={"quantity": nova_qtd})
        qtd_apos_a = next(i["quantity"] for i in _obter_carrinho(client, tok["A"])["items"] if i["id"] == item_id)
        ev["a_status"] = r_a.status_code
        ev["qtd_apos_a"] = qtd_apos_a
        if r_a.status_code != 200 or qtd_apos_a != nova_qtd:
            desvios.append(f"A não conseguiu alterar próprio item: HTTP {r_a.status_code}, qtd={qtd_apos_a}")
    finally:
        client.patch(f"/api/cart/items/{item_id}", headers=auth_headers(tok["A"]), json={"quantity": qtd_antes})

    decisao = "desvio_confirmado" if desvios else "conforme"
    just = "; ".join(desvios) if desvios else "Tentativa de B alterar item de A foi rejeitada preservando quantidade; atualização pelo titular A funcionou."
    reg.registrar("C05", "Cart", "PATCH /api/cart/items/{item_id}", "A, B", "Somente o titular altera a quantidade do item", decisao, just, ev)
    assert not desvios, just


def test_c06_remover_item_carrinho_titularidade(ctx):
    client, m, tok, reg = ctx["client"], ctx["manifesto"], ctx["tokens"], ctx["reg"]
    p2_id = m["produtos"]["P2"]["id"]

    r_add = client.post("/api/cart/items", headers=auth_headers(tok["A"]), json={"product_id": p2_id, "quantity": 1})
    assert r_add.status_code in (200, 201)
    item_id = r_add.json()["id"]
    b_antes = _resumo_itens_cart(_obter_carrinho(client, tok["B"]))

    desvios: list[str] = []
    ev: dict[str, Any] = {"item_a_id": item_id}
    try:
        r_b = client.delete(f"/api/cart/items/{item_id}", headers=auth_headers(tok["B"]))
        ids_a_apos_b = [i["id"] for i in _obter_carrinho(client, tok["A"])["items"]]
        ev["b_status"] = r_b.status_code
        ev["existe_apos_b"] = item_id in ids_a_apos_b
        if r_b.status_code not in (401, 403, 404) or item_id not in ids_a_apos_b:
            desvios.append(f"B removeu item de A: HTTP {r_b.status_code}, existe={item_id in ids_a_apos_b}")

        if item_id in ids_a_apos_b:
            r_a = client.delete(f"/api/cart/items/{item_id}", headers=auth_headers(tok["A"]))
            ids_a_apos_a = [i["id"] for i in _obter_carrinho(client, tok["A"])["items"]]
            b_depois = _resumo_itens_cart(_obter_carrinho(client, tok["B"]))
            ev["a_status"] = r_a.status_code
            ev["existe_apos_a"] = item_id in ids_a_apos_a
            ev["b_preservado"] = b_depois == b_antes
            if r_a.status_code not in (200, 204) or item_id in ids_a_apos_a or b_depois != b_antes:
                desvios.append(f"Remoção por A falhou ou afetou B: HTTP {r_a.status_code}")
    finally:
        ids_now = [i["id"] for i in _obter_carrinho(client, tok["A"])["items"]]
        if item_id in ids_now:
            client.delete(f"/api/cart/items/{item_id}", headers=auth_headers(tok["A"]))

    decisao = "desvio_confirmado" if desvios else "conforme"
    just = "; ".join(desvios) if desvios else "Tentativa de B remover item de A foi rejeitada preservando o item; remoção por A funcionou preservando B."
    reg.registrar("C06", "Cart", "DELETE /api/cart/items/{item_id}", "A, B", "Somente o titular remove o item", decisao, just, ev)
    assert not desvios, just


def test_c02_limpar_carrinho_titularidade(ctx):
    client, m, tok, reg = ctx["client"], ctx["manifesto"], ctx["tokens"], ctx["reg"]
    p1_id = m["produtos"]["P1"]["id"]
    b_antes = _resumo_itens_cart(_obter_carrinho(client, tok["B"]))

    desvios: list[str] = []
    ev: dict[str, Any] = {"b_antes": b_antes}
    try:
        r = client.delete("/api/cart/", headers=auth_headers(tok["A"]))
        a_depois = _resumo_itens_cart(_obter_carrinho(client, tok["A"]))
        b_depois = _resumo_itens_cart(_obter_carrinho(client, tok["B"]))
        ev.update({"status": r.status_code, "a_depois": a_depois, "b_depois": b_depois})
        if r.status_code not in (200, 204) or a_depois != []:
            desvios.append(f"Limpeza do carrinho de A falhou: HTTP {r.status_code}, a_depois={a_depois}")
        if b_depois != b_antes:
            desvios.append(f"Limpeza de A afetou B: antes={b_antes}, depois={b_depois}")
    finally:
        client.post("/api/cart/items", headers=auth_headers(tok["A"]), json={"product_id": p1_id, "quantity": 1})

    decisao = "desvio_confirmado" if desvios else "conforme"
    just = "; ".join(desvios) if desvios else "Limpeza por A esvaziou apenas o carrinho de A e preservou integralmente o carrinho de B."
    reg.registrar("C02", "Cart", "DELETE /api/cart/", "A, B", "Limpeza restrita ao carrinho do titular", decisao, just, ev)
    assert not desvios, just


def _verificar_aut(
    reg: RegistradorEvidencias,
    unidade: str,
    modulo: str,
    operacao: str,
    perfil: str,
    status_valido: int,
    status_sem_auth: int,
    status_invalido: int,
    extra: dict[str, Any] | None = None,
) -> None:
    desvios: list[str] = []
    if not (200 <= status_valido < 300):
        desvios.append(f"Controle positivo falhou (HTTP {status_valido})")
    if status_sem_auth not in (401, 403):
        desvios.append(f"Chamada sem credencial não rejeitada (HTTP {status_sem_auth})")
    if status_invalido not in (401, 403):
        desvios.append(f"Credencial inválida não rejeitada (HTTP {status_invalido})")

    ev: dict[str, Any] = {
        "status_valido": status_valido,
        "status_sem_auth": status_sem_auth,
        "status_token_invalido": status_invalido,
    }
    if extra:
        ev.update(extra)

    decisao = "desvio_confirmado" if desvios else "conforme"
    just = "; ".join(desvios) if desvios else (
        f"Controle positivo HTTP {status_valido}; sem credencial HTTP {status_sem_auth}; credencial inválida HTTP {status_invalido}."
    )
    reg.registrar(unidade, modulo, operacao, perfil, "Operação protegida exige credencial válida", decisao, just, ev)
    assert not desvios, just


def test_aut_e026_criar_produto(ctx):
    client, m, eng, tok, reg = ctx["client"], ctx["manifesto"], ctx["engine"], ctx["tokens"], ctx["reg"]
    payload = _payload_produto_base(m["lojas"]["V1"], "EXP-SEG-01 T3 AUT E026")
    img = png_1x1()

    criados: list[tuple[int, str | None]] = []
    try:
        r_ok = client.post("/api/products/", headers=auth_headers(tok["V1"]), data={"data": json.dumps(payload)}, files=[("images", ("a.png", img, "image/png"))])
        if r_ok.status_code in (200, 201) and r_ok.json().get("id"):
            criados.append((r_ok.json()["id"], tok["V1"]))
        r_no = client.post("/api/products/", data={"data": json.dumps(payload)}, files=[("images", ("a.png", img, "image/png"))])
        if r_no.status_code in (200, 201) and r_no.json().get("id"):
            criados.append((r_no.json()["id"], None))
        r_bad = client.post("/api/products/", headers=auth_headers(TOKEN_INVALIDO), data={"data": json.dumps(payload)}, files=[("images", ("a.png", img, "image/png"))])
        if r_bad.status_code in (200, 201) and r_bad.json().get("id"):
            criados.append((r_bad.json()["id"], None))
    finally:
        for pid, owner_tok in criados:
            limpar_produto_descartavel(client, eng, pid, owner_tok)

    _verificar_aut(reg, "AUT-E026", "Products", "POST /api/products/", "V1", r_ok.status_code, r_no.status_code, r_bad.status_code)


def test_aut_e028_listar_meus_produtos(ctx):
    client, tok, reg = ctx["client"], ctx["tokens"], ctx["reg"]
    r_ok = client.get("/api/products/me", headers=auth_headers(tok["V1"]))
    r_no = client.get("/api/products/me")
    r_bad = client.get("/api/products/me", headers=auth_headers(TOKEN_INVALIDO))
    _verificar_aut(reg, "AUT-E028", "Products", "GET /api/products/me", "V1", r_ok.status_code, r_no.status_code, r_bad.status_code)


def test_aut_e031_atualizar_put(ctx):
    client, m, tok, reg = ctx["client"], ctx["manifesto"], ctx["tokens"], ctx["reg"]
    p1_id, nome = m["produtos"]["P1"]["id"], m["produtos"]["P1"]["name"]
    files = {"data": (None, json.dumps({"name": nome}))}

    r_ok = client.put(f"/api/products/{p1_id}", headers=auth_headers(tok["V1"]), files=files)
    r_no = client.put(f"/api/products/{p1_id}", files=files)
    r_bad = client.put(f"/api/products/{p1_id}", headers=auth_headers(TOKEN_INVALIDO), files=files)
    _verificar_aut(reg, "AUT-E031", "Products", "PUT /api/products/{product_id}", "V1", r_ok.status_code, r_no.status_code, r_bad.status_code)


def test_aut_e032_atualizar_patch(ctx):
    client, m, tok, reg = ctx["client"], ctx["manifesto"], ctx["tokens"], ctx["reg"]
    p1_id, nome = m["produtos"]["P1"]["id"], m["produtos"]["P1"]["name"]
    files = {"data": (None, json.dumps({"name": nome}))}

    r_ok = client.patch(f"/api/products/{p1_id}", headers=auth_headers(tok["V1"]), files=files)
    r_no = client.patch(f"/api/products/{p1_id}", files=files)
    r_bad = client.patch(f"/api/products/{p1_id}", headers=auth_headers(TOKEN_INVALIDO), files=files)
    _verificar_aut(reg, "AUT-E032", "Products", "PATCH /api/products/{product_id}", "V1", r_ok.status_code, r_no.status_code, r_bad.status_code)


def test_aut_e033_excluir_produto(ctx):
    client, m, eng, tok, reg = ctx["client"], ctx["manifesto"], ctx["engine"], ctx["tokens"], ctx["reg"]
    r_c = _criar_produto_descartavel(client, tok["V1"], m["lojas"]["V1"], "EXP-SEG-01 T3 AUT E033")
    assert r_c.status_code in (200, 201)
    pid = r_c.json()["id"]
    try:
        r_no = client.delete(f"/api/products/{pid}")
        r_bad = client.delete(f"/api/products/{pid}", headers=auth_headers(TOKEN_INVALIDO))
        r_ok = client.delete(f"/api/products/{pid}", headers=auth_headers(tok["V1"]))
    finally:
        limpar_produto_descartavel(client, eng, pid, tok["V1"])
    _verificar_aut(reg, "AUT-E033", "Products", "DELETE /api/products/{product_id}", "V1", r_ok.status_code, r_no.status_code, r_bad.status_code)


def test_aut_e034_consultar_carrinho(ctx):
    client, tok, reg = ctx["client"], ctx["tokens"], ctx["reg"]
    r_ok = client.get("/api/cart/", headers=auth_headers(tok["A"]))
    r_no = client.get("/api/cart/")
    r_bad = client.get("/api/cart/", headers=auth_headers(TOKEN_INVALIDO))
    _verificar_aut(reg, "AUT-E034", "Cart", "GET /api/cart/", "A", r_ok.status_code, r_no.status_code, r_bad.status_code)


def test_aut_e036_adicionar_item(ctx):
    client, m, tok, reg = ctx["client"], ctx["manifesto"], ctx["tokens"], ctx["reg"]
    body = {"product_id": m["produtos"]["P2"]["id"], "quantity": 1}
    r_no = client.post("/api/cart/items", json=body)
    r_bad = client.post("/api/cart/items", headers=auth_headers(TOKEN_INVALIDO), json=body)
    r_ok = client.post("/api/cart/items", headers=auth_headers(tok["A"]), json=body)
    if r_ok.status_code in (200, 201) and r_ok.json().get("id"):
        client.delete(f"/api/cart/items/{r_ok.json()['id']}", headers=auth_headers(tok["A"]))
    _verificar_aut(reg, "AUT-E036", "Cart", "POST /api/cart/items", "A", r_ok.status_code, r_no.status_code, r_bad.status_code)


def test_aut_e037_adicionar_lote(ctx):
    client, m, tok, reg = ctx["client"], ctx["manifesto"], ctx["tokens"], ctx["reg"]
    p2_id = m["produtos"]["P2"]["id"]
    body = [{"product_id": p2_id, "quantity": 1}]
    r_no = client.post("/api/cart/items/bulk", json=body)
    r_bad = client.post("/api/cart/items/bulk", headers=auth_headers(TOKEN_INVALIDO), json=body)
    r_ok = client.post("/api/cart/items/bulk", headers=auth_headers(tok["A"]), json=body)
    for it in _obter_carrinho(client, tok["A"]).get("items", []):
        if it["product_id"] == p2_id:
            client.delete(f"/api/cart/items/{it['id']}", headers=auth_headers(tok["A"]))
    _verificar_aut(reg, "AUT-E037", "Cart", "POST /api/cart/items/bulk", "A", r_ok.status_code, r_no.status_code, r_bad.status_code)


def test_aut_e038_atualizar_item(ctx):
    client, m, tok, reg = ctx["client"], ctx["manifesto"], ctx["tokens"], ctx["reg"]
    cart_a = _obter_carrinho(client, tok["A"])
    if not cart_a["items"]:
        client.post("/api/cart/items", headers=auth_headers(tok["A"]), json={"product_id": m["produtos"]["P1"]["id"], "quantity": 1})
        cart_a = _obter_carrinho(client, tok["A"])
    item = cart_a["items"][0]
    iid, qtd = item["id"], item["quantity"]
    r_no = client.patch(f"/api/cart/items/{iid}", json={"quantity": qtd})
    r_bad = client.patch(f"/api/cart/items/{iid}", headers=auth_headers(TOKEN_INVALIDO), json={"quantity": qtd})
    r_ok = client.patch(f"/api/cart/items/{iid}", headers=auth_headers(tok["A"]), json={"quantity": qtd})
    _verificar_aut(reg, "AUT-E038", "Cart", "PATCH /api/cart/items/{item_id}", "A", r_ok.status_code, r_no.status_code, r_bad.status_code)


def test_aut_e039_remover_item(ctx):
    client, m, tok, reg = ctx["client"], ctx["manifesto"], ctx["tokens"], ctx["reg"]
    r_add = client.post("/api/cart/items", headers=auth_headers(tok["A"]), json={"product_id": m["produtos"]["P2"]["id"], "quantity": 1})
    assert r_add.status_code in (200, 201)
    iid = r_add.json()["id"]
    r_no = client.delete(f"/api/cart/items/{iid}")
    r_bad = client.delete(f"/api/cart/items/{iid}", headers=auth_headers(TOKEN_INVALIDO))
    r_ok = client.delete(f"/api/cart/items/{iid}", headers=auth_headers(tok["A"]))
    _verificar_aut(reg, "AUT-E039", "Cart", "DELETE /api/cart/items/{item_id}", "A", r_ok.status_code, r_no.status_code, r_bad.status_code)


def test_aut_e035_limpar_carrinho(ctx):
    client, m, tok, reg = ctx["client"], ctx["manifesto"], ctx["tokens"], ctx["reg"]
    p1_id = m["produtos"]["P1"]["id"]
    try:
        r_no = client.delete("/api/cart/")
        r_bad = client.delete("/api/cart/", headers=auth_headers(TOKEN_INVALIDO))
        r_ok = client.delete("/api/cart/", headers=auth_headers(tok["A"]))
    finally:
        client.post("/api/cart/items", headers=auth_headers(tok["A"]), json={"product_id": p1_id, "quantity": 1})
    _verificar_aut(reg, "AUT-E035", "Cart", "DELETE /api/cart/", "A", r_ok.status_code, r_no.status_code, r_bad.status_code)
