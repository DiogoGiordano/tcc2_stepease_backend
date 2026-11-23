"""Piloto funcional EXP-SEG-01. Execute na mesma pasta em que a API importa app."""

import argparse
import json
import os
import sys
from datetime import datetime
from getpass import getpass
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, build_opener, Request

# Configuração da bancada. Edite aqui se a API, as rotas ou a carga mudarem.
BASE = "http://127.0.0.1:8000"
LOGIN = "/api/auth/login"
ME = "/api/auth/me"
PRODUTO = "/api/products/{id}"
CART = "/api/cart/"
ITEM = "/api/cart/items/{id}"
EMAIL_A = "exp-seg-01-a@example.com"
EMAIL_B = "exp-seg-01-b@example.com"
SENHA = ""
BANCO_ESPERADO = "inclusivo_experiment_backend"
def localizar_carga():
    """Localiza os IDs reais de A/P1/V1 e B/P2/V2 no banco experimental."""
    from sqlalchemy import create_engine, text
    from backend.app.core.config import settings

    consulta = text("""
        SELECT cliente.id AS usuario, c.id AS carrinho, i.id AS item,
               p.id AS produto, s.id AS loja
        FROM users AS cliente
        JOIN carts AS c ON c.user_id = cliente.id
        JOIN cart_items AS i ON i.cart_id = c.id
        JOIN products AS p ON p.id = i.product_id
        JOIN sellers AS s ON s.id = p.seller_id
        JOIN users AS vendedor ON vendedor.id = s.user_id
        WHERE cliente.email = :cliente
          AND p.name = :produto
          AND vendedor.email = :vendedor
    """)

    engine = create_engine(settings.database_url)
    try:
        with engine.connect() as db:
            banco = db.execute(text("SELECT current_database()")).scalar_one()
            if banco != BANCO_ESPERADO:
                raise RuntimeError(f"Banco conectado: {banco}. Esperado: {BANCO_ESPERADO}.")

            def localizar(cliente, produto, vendedor, quantidade_inicial):
                linhas = db.execute(consulta, {
                    "cliente": cliente,
                    "produto": produto,
                    "vendedor": vendedor,
                }).mappings().all()

                if len(linhas) != 1:
                    raise RuntimeError(
                        f"Banco {banco}: encontrei {len(linhas)} vínculos para "
                        f"{cliente} → {produto} → {vendedor}; esperado: 1."
                    )

                r = linhas[0]
                print(f"{produto}: produto={r['produto']}, loja={r['loja']}, "
                      f"carrinho={r['carrinho']}, item={r['item']}")
                ator = (r["usuario"], r["carrinho"], r["item"], r["produto"],
                        quantidade_inicial)
                return ator, r["loja"]

            a, loja_p1 = localizar(EMAIL_A, "EXP-SEG-01 P1", EMAIL_V1, 1)
            b, _ = localizar(EMAIL_B, "EXP-SEG-01 P2", EMAIL_V2, 2)
            return a, b, loja_p1
    finally:
        engine.dispose()


EMAIL_V1 = "exp-seg-01-v1@example.com"
EMAIL_V2 = "exp-seg-01-v2@example.com"
A, B, LOJA_P1 = localizar_carga()
ESTOQUE_P1 = 10
NOVA_QUANTIDADE = 3
RESULTADOS = Path("experiment/experimento-seguranca/results")
BACKUPS = Path.home() / ".local/share/exp-seg-01/backups"




class SemRedirecionamento(HTTPRedirectHandler):
    """Mantém a chamada com credenciais no endereço configurado."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def requisicao(metodo, rota, corpo=None, token=None):
    """Retorna o objeto JSON em HTTP 200; mantém senhas e tokens fora do relatório."""
    headers = {"Accept": "application/json"}
    dados = None
    if corpo is not None:
        dados = json.dumps(corpo).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(BASE.rstrip("/") + rota, data=dados, headers=headers, method=metodo)
    try:
        with build_opener(SemRedirecionamento()).open(req, timeout=15) as resp:
            if resp.status != 200:
                raise RuntimeError(f"{metodo} {rota}: HTTP {resp.status}")
            return json.load(resp)
    except HTTPError as erro:
        raise RuntimeError(f"{metodo} {rota}: HTTP {erro.code}") from None


def itens_do_usuario(token):
    """Extrai o titular, o carrinho e seus itens, omitindo os demais dados."""
    cart = requisicao("GET", CART, token=token)
    return sorted([cart["user_id"], cart["id"], i["id"], i["product_id"], i["quantity"]]
                  for i in cart["items"])


def executar(completo):
    """Confere o estado inicial. No modo completo também salva, altera e restaura."""
    os.umask(0o077)
    pasta = RESULTADOS / datetime.now().astimezone().strftime("piloto-http-%Y%m%d-%H%M%S-%f")
    pasta.mkdir(parents=True)
    relatorio = {"inicio": datetime.now().astimezone().isoformat(), "api": BASE,
                 "modo": "completo" if completo else "inicial", "verificacoes": []}

    def conferir(etapa, esperado, observado):
        """Registra evidência e interrompe na primeira divergência."""
        ok = esperado == observado
        relatorio["verificacoes"].append(dict(etapa=etapa, esperado=esperado,
                                              observado=observado, ok=ok))
        if not ok:
            raise ValueError(f"{etapa}: esperado {esperado}, observado {observado}")
        print(f"OK: {etapa}")

    try:
        senha = SENHA or getpass("Senha das contas A e B: ")
        tokens = []
        for email, ator in ((EMAIL_A, A), (EMAIL_B, B)):
            resposta = requisicao("POST", LOGIN, {"email": email, "password": senha})
            token = resposta.get("access_token")
            if not token:
                raise ValueError("Login sem access_token. Confira o estado de 2FA da carga.")
            identidade = requisicao("GET", ME, token=token)
            conferir(f"Identidade {email}", [ator[0], email], [identidade["id"], identidade["email"]])
            tokens.append(token)
        produto = requisicao("GET", PRODUTO.format(id=A[3]))
        conferir("Produto P1", [A[3], LOJA_P1, ESTOQUE_P1],
                 [produto["id"], produto["seller_id"], produto["stock"]])
        inicial = [list(A), list(B)]
        conferir("Carrinhos iniciais", inicial, itens_do_usuario(tokens[0]) + itens_do_usuario(tokens[1]))
        if completo:
            esperado_a = [*A[:4], NOVA_QUANTIDADE]

            resposta = requisicao(
                "PATCH",
                ITEM.format(id=A[2]),
                corpo={"quantity": NOVA_QUANTIDADE},
                token=tokens[0],
            )
            conferir(
                "PATCH do próprio item de A",
                [A[2], NOVA_QUANTIDADE],
                [resposta["id"], resposta["quantity"]],
            )

            conferir(
                "Carrinho de A após PATCH", [esperado_a], itens_do_usuario(tokens[0])
            )
            conferir("Carrinho de B após PATCH", [list(B)], itens_do_usuario(tokens[1]))
        relatorio["resultado"] = "verificações concluídas"
    except Exception as exc:
        relatorio["resultado"] = "interrompido"
        # Drivers podem incluir parâmetros na exceção. Só os nossos erros possuem texto público.
        relatorio["erro"] = str(exc) if type(exc) in (ValueError, RuntimeError) else type(exc).__name__
        raise
    finally:
        (pasta / "ficha.json").write_text(json.dumps(relatorio, indent=2, ensure_ascii=False))
        print(f"Ficha: {pasta / 'ficha.json'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--completo", action="store_true", help="Inclui backup, restauração em cópia e PATCH.")
    try:
        executar(parser.parse_args().completo)
    except Exception as erro:
        sys.exit(f"Piloto interrompido: {erro}")
