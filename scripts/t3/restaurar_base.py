"""Restaura a massa experimental no PostgreSQL para o T3 e gera results/t3/restauracao-base.json."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.t3.helpers import RESTAURACAO_PATH, criar_engine  # noqa: E402

BANCO_PADRAO = "inclusivo_experiment_backend"

ATORES_EMAILS: dict[str, str] = {
    "A": "exp-seg-01-a@example.com",
    "B": "exp-seg-01-b@example.com",
    "V1": "exp-seg-01-v1@example.com",
    "V2": "exp-seg-01-v2@example.com",
}

PRODUTOS_REF: dict[str, tuple[str, str]] = {
    "P1": ("EXP-SEG-01 P1", "V1"),
    "P2": ("EXP-SEG-01 P2", "V2"),
}


def restaurar_base(banco_esperado: str, destino: Path = RESTAURACAO_PATH) -> dict[str, Any]:
    """Confere o banco, desativa 2FA, repõe estoque de P1/P2 em 10 e recria itens de A (1xP1) e B (2xP2)."""
    engine = criar_engine()
    try:
        with engine.begin() as conn:
            banco_atual = conn.execute(text("SELECT current_database()")).scalar_one()
            if banco_atual != banco_esperado:
                raise RuntimeError(
                    f"Banco conectado '{banco_atual}' difere do esperado '{banco_esperado}'. Operação abortada."
                )

            atores: dict[str, dict[str, Any]] = {}
            for alias, email in ATORES_EMAILS.items():
                row = conn.execute(
                    text("SELECT id, email, type FROM users WHERE email = :email"),
                    {"email": email},
                ).mappings().first()
                if row is None:
                    raise RuntimeError(
                        f"Conta experimental {alias} ({email}) não encontrada. "
                        "Execute 'python scripts/preparar_base_piloto.py' primeiro."
                    )
                atores[alias] = {
                    "user_id": int(row["id"]),
                    "email": str(row["email"]),
                    "type": str(row["type"]),
                }

            # 1. Desativar 2FA nas quatro contas experimentais
            for info in atores.values():
                conn.execute(
                    text("UPDATE users SET two_factor_enabled = false, two_factor_method = NULL WHERE id = :uid"),
                    {"uid": info["user_id"]},
                )

            # 2. Localizar lojas de V1 e V2
            lojas: dict[str, int] = {}
            for alias in ("V1", "V2"):
                seller_id = conn.execute(
                    text("SELECT id FROM sellers WHERE user_id = :uid ORDER BY id LIMIT 1"),
                    {"uid": atores[alias]["user_id"]},
                ).scalar_one_or_none()
                if seller_id is None:
                    raise RuntimeError(f"Loja do vendedor {alias} não encontrada na tabela sellers.")
                lojas[alias] = int(seller_id)

            # 3. Localizar P1 e P2 e repor estoque para 10
            produtos: dict[str, dict[str, Any]] = {}
            for cod, (nome, vendedor) in PRODUTOS_REF.items():
                row = conn.execute(
                    text(
                        "SELECT id, name, seller_id FROM products "
                        "WHERE name = :nome AND seller_id = :sid ORDER BY id LIMIT 1"
                    ),
                    {"nome": nome, "sid": lojas[vendedor]},
                ).mappings().first()
                if row is None:
                    raise RuntimeError(
                        f"Produto {cod} ('{nome}') vinculado à loja {lojas[vendedor]} ({vendedor}) não encontrado."
                    )
                pid = int(row["id"])
                conn.execute(
                    text("UPDATE products SET stock = 10 WHERE id = :pid"),
                    {"pid": pid},
                )
                produtos[cod] = {
                    "id": pid,
                    "name": str(row["name"]),
                    "seller_id": int(row["seller_id"]),
                    "stock": 10,
                }

            # 4. Garantir carrinhos de A e B e recriar itens iniciais (A=1xP1, B=2xP2)
            carrinhos: dict[str, dict[str, int]] = {}
            for alias, prod_cod, qtd in (("A", "P1", 1), ("B", "P2", 2)):
                uid = atores[alias]["user_id"]
                cart_id = conn.execute(
                    text("SELECT id FROM carts WHERE user_id = :uid ORDER BY id LIMIT 1"),
                    {"uid": uid},
                ).scalar_one_or_none()
                if cart_id is None:
                    cart_id = conn.execute(
                        text("INSERT INTO carts (user_id) VALUES (:uid) RETURNING id"),
                        {"uid": uid},
                    ).scalar_one()
                cart_id = int(cart_id)

                conn.execute(text("DELETE FROM cart_items WHERE cart_id = :cid"), {"cid": cart_id})
                item_id = conn.execute(
                    text(
                        "INSERT INTO cart_items (cart_id, product_id, quantity) "
                        "VALUES (:cid, :pid, :qtd) RETURNING id"
                    ),
                    {"cid": cart_id, "pid": produtos[prod_cod]["id"], "qtd": qtd},
                ).scalar_one()

                carrinhos[alias] = {
                    "cart_id": cart_id,
                    "item_id": int(item_id),
                    "product_id": produtos[prod_cod]["id"],
                    "quantity": qtd,
                }

        manifesto: dict[str, Any] = {
            "banco": banco_atual,
            "restaurado_em_utc": datetime.now(timezone.utc).isoformat(),
            "atores": atores,
            "lojas": lojas,
            "produtos": produtos,
            "carrinhos": carrinhos,
        }
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(json.dumps(manifesto, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return manifesto
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--banco",
        default=BANCO_PADRAO,
        help=f"Nome esperado do banco PostgreSQL experimental (padrão: {BANCO_PADRAO}).",
    )
    parser.add_argument(
        "--saida",
        type=Path,
        default=RESTAURACAO_PATH,
        help="Caminho do manifesto JSON gerado (padrão: results/t3/restauracao-base.json).",
    )
    args = parser.parse_args()

    saida = args.saida if args.saida.is_absolute() else (ROOT_DIR / args.saida)
    manifesto = restaurar_base(args.banco, saida)

    print(f"Base restaurada no banco: {manifesto['banco']}")
    print("  Lojas:    ", manifesto["lojas"])
    print("  Produtos: ", {k: (v["id"], f"stock={v['stock']}") for k, v in manifesto["produtos"].items()})
    print(
        "  Carrinhos:",
        {k: f"cart={v['cart_id']} item={v['item_id']} qtd={v['quantity']}" for k, v in manifesto["carrinhos"].items()},
    )
    print(f"Manifesto salvo em: {saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())