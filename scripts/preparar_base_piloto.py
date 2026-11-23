"""Cria uma vez a carga fixa do piloto EXP-SEG-01 no PostgreSQL experimental."""

from getpass import getpass

ATORES = (("A", "client"), ("B", "client"), ("V1", "seller"), ("V2", "seller"))


def email_de(alias):
    """Retorna o e-mail estável usado no login do ator."""
    return f"exp-seg-01-{alias.lower()}@example.com"


def preparar(executar, senha_hash):
    """Insere a carga e retorna os IDs dos recursos.

    Args:
        executar: Função que executa SQL parametrizado na transação corrente.
        senha_hash: Hash produzido pelo backend para a senha das contas de teste.
    Returns:
        Dicionário dos IDs alocados pelo banco.
    Raises:
        ValueError: Um dos e-mails reservados já existe.
    """
    ids = {}
    for alias, _ in ATORES:
        if executar("SELECT id FROM users WHERE email=:email", email=email_de(alias)).fetchone():
            raise ValueError(f"A conta {email_de(alias)} já existe. Carga interrompida antes da inserção.")
    for alias, papel in ATORES:
        email = email_de(alias)
        nome = f"EXP-SEG-01 {alias}"
        usuario = executar(
            """INSERT INTO users (name,email,password,type,two_factor_enabled)
               VALUES (:nome,:email,:senha,:papel,false) RETURNING id""",
            nome=nome, email=email, senha=senha_hash, papel=papel,
        ).fetchone()[0]
        ids[alias] = usuario
        if papel == "client":
            executar(
                """INSERT INTO clients (user_id,name,email,address,cpf)
                   VALUES (:usuario,:nome,:email,'Endereco de teste',:cpf)""",
                usuario=usuario, nome=nome, email=email,
                cpf={"A": "00000000191", "B": "00000000272"}[alias],
            )
        else:
            ids[f"loja-{alias}"] = executar(
                """INSERT INTO sellers (user_id,name,store,store_name,cep)
                   VALUES (:usuario,:nome,true,:nome,'01001-000') RETURNING id""",
                usuario=usuario, nome=nome,
            ).fetchone()[0]

    for cliente, vendedor, produto, quantidade in (("A", "V1", "P1", 1), ("B", "V2", "P2", 2)):
        ids[produto] = executar(
            """INSERT INTO products (name,size,price,stock,seller_id,images,version,
               foot_type,brand,model,category,gender,color,age_group)
               VALUES (:nome,40,100,10,:loja,'[]',1,'pair','Piloto',:modelo,
               'Casual','Unissex','Preto','Adulto') RETURNING id""",
            nome=f"EXP-SEG-01 {produto}", loja=ids[f"loja-{vendedor}"], modelo=produto,
        ).fetchone()[0]
        carrinho = executar(
            "INSERT INTO carts (user_id) VALUES (:usuario) RETURNING id", usuario=ids[cliente]
        ).fetchone()[0]
        ids[f"carrinho-{cliente}"] = carrinho
        ids[f"item-{cliente}"] = executar(
            """INSERT INTO cart_items (cart_id,product_id,quantity)
               VALUES (:carrinho,:produto,:quantidade) RETURNING id""",
            carrinho=carrinho, produto=ids[produto], quantidade=quantidade,
        ).fetchone()[0]
    return ids


def main():
    """Confere o banco escolhido, insere em uma transação e mostra o manifesto."""
    import json
    from sqlalchemy import create_engine, text
    from backend.app.core.config import settings
    from backend.app.core.security.passwords import hash_password

    engine = create_engine(settings.database_url)
    with engine.begin() as conexao:
        def executar(sql, **parametros):
            return conexao.execute(text(sql), parametros)

        banco = executar("SELECT current_database()").scalar_one()
        print(f"Banco configurado pela aplicação: {banco}")
        if input("Digite o nome do banco experimental para confirmar: ").strip() != banco:
            raise SystemExit("Cancelado.")
        senha = getpass("Escolha a senha local das quatro contas (8 a 72 bytes): ")
        if not 8 <= len(senha.encode()) <= 72:
            raise SystemExit("A senha precisa ter entre 8 e 72 bytes.")
        executar("SELECT pg_advisory_xact_lock(70423001)")
        ids = preparar(executar, hash_password(senha))
    print(json.dumps(ids, indent=2))
    for alias, _ in ATORES:
        print(f"{alias}: {email_de(alias)}")


if __name__ == "__main__":
    main()
