"""Configuração, modelo de unidade AUT e contexto compartilhado do T2A."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from getpass import getpass
from pathlib import Path
from typing import Any

from .suporte import auth_headers, criar_sessao_http, login_local

ROOT_DIR = Path(__file__).resolve().parents[3]
RESULTS_DIR = ROOT_DIR / "results"
DEFAULT_SAIDA_DIR = RESULTS_DIR / "t2a"
OPENAPI_SCOPE_PATH = RESULTS_DIR / "openapi_scope.json"
CONFERENCIA_SCRIPT = ROOT_DIR / "scripts" / "t2a" / "executar_t2a.py"

API_PADRAO = "http://127.0.0.1:8000"
EMAIL_A = "exp-seg-01-a@example.com"
EMAIL_V1 = "exp-seg-01-v1@example.com"
NOME_PRODUTO_P1 = "EXP-SEG-01 P1"


@dataclass(frozen=True)
class UnidadeAUT:
    """Metadados de uma unidade AUT do protocolo EXP-SEG-01."""

    codigo: str
    modulo: str
    metodo: str
    rota: str
    prefixo_har: str
    fase: str
    perfil: str
    rate_limit: str | None = None

    @property
    def id_completo(self) -> str:
        return f"AUT-{self.codigo}"

    @property
    def slug(self) -> str:
        return f"aut-{self.codigo.lower()}"

    @property
    def pacote(self) -> str:
        return f"aut_{self.codigo.lower()}"

    @property
    def include_name(self) -> str:
        return f"{self.metodo} {self.rota}"


class ContextoT2A:
    """Mantém sessões HTTP, tokens e estado temporário compartilhado entre unidades."""

    def __init__(
        self,
        api_url: str = API_PADRAO,
        saida_dir: Path = DEFAULT_SAIDA_DIR,
        escopo_path: Path = OPENAPI_SCOPE_PATH,
        senha: str | None = None,
        token_a: str | None = None,
        token_v1: str | None = None,
        otp_email: str | None = None,
        restaurar_carrinho: bool = False,
    ) -> None:
        self.api = api_url.rstrip("/")
        self.saida_dir = saida_dir
        self.escopo_path = escopo_path
        self.senha = senha
        self.token_a = token_a
        self.token_v1 = token_v1
        self.otp_email = otp_email
        self.restaurar_carrinho = restaurar_carrinho

        self.sessao = criar_sessao_http()
        self.user_id_a: int | None = None
        self.p1_meta: dict[str, Any] | None = None
        self.produto_descartavel_id: int | None = None
        self.google_secret: str | None = None
        self.token_2fa_email: str | None = None

    def fechar(self) -> None:
        self.sessao.close()

    def pasta_unidade(self, unidade: UnidadeAUT) -> Path:
        pasta = self.saida_dir / unidade.slug
        pasta.mkdir(parents=True, exist_ok=True)
        return pasta

    def exigir_senha(self, motivo: str) -> str:
        if not self.senha:
            self.senha = getpass(f"Senha das contas experimentais ({motivo}): ").strip()
        if not self.senha:
            raise RuntimeError(f"Senha obrigatória não informada ({motivo}).")
        return self.senha

    def token_de_a(self) -> str:
        if self.token_a:
            r = self.sessao.get(f"{self.api}/api/auth/me", headers=auth_headers(self.token_a), timeout=10)
            if r.status_code == 200:
                self.user_id_a = r.json().get("id")
                return self.token_a

        senha = self.exigir_senha("conta A")
        dados = login_local(self.sessao, self.api, EMAIL_A, senha)
        if dados.get("two_factor_required"):
            raise RuntimeError(
                "Conta A está com 2FA ativo e sem TOKEN_A válido. "
                "Desative o 2FA ou restaure a base antes de coletar."
            )
        tok = dados.get("access_token")
        if not tok:
            raise RuntimeError("Login de A não retornou access_token.")
        self.token_a = tok
        me = self.sessao.get(f"{self.api}/api/auth/me", headers=auth_headers(tok), timeout=10)
        if me.status_code == 200:
            self.user_id_a = me.json().get("id")
        return tok

    def token_de_v1(self) -> str:
        if self.token_v1:
            r = self.sessao.get(f"{self.api}/api/auth/me", headers=auth_headers(self.token_v1), timeout=10)
            if r.status_code == 200:
                return self.token_v1

        senha = self.exigir_senha("conta V1")
        dados = login_local(self.sessao, self.api, EMAIL_V1, senha)
        tok = dados.get("access_token")
        if not tok:
            raise RuntimeError("Login de V1 não retornou access_token.")
        self.token_v1 = tok
        return tok

    def obter_produto_p1(self, usar_rota_vendedor: bool = False) -> dict[str, Any]:
        if self.p1_meta is not None:
            return self.p1_meta

        if not usar_rota_vendedor:
            r_pub = self.sessao.get(
                f"{self.api}/api/products/", params={"limit": 100}, timeout=10, allow_redirects=False
            )
            if r_pub.status_code == 200:
                dados = r_pub.json()
                itens = dados if isinstance(dados, list) else dados.get("items", [])
                p1 = next((p for p in itens if p.get("name") == NOME_PRODUTO_P1), None)
                if p1 is not None:
                    self.p1_meta = p1
                    return p1

        tok_v1 = self.token_de_v1()
        resp = self.sessao.get(
            f"{self.api}/api/products/me", headers=auth_headers(tok_v1), timeout=10, allow_redirects=False
        )
        resp.raise_for_status()
        dados = resp.json()
        produtos = dados if isinstance(dados, list) else dados.get("items", [])
        if not produtos:
            raise RuntimeError("Nenhum produto encontrado para V1 em GET /api/products/me.")
        p1 = next((p for p in produtos if p.get("name") == NOME_PRODUTO_P1), produtos[0])
        self.p1_meta = p1
        return p1

    def obter_carrinho_a(self) -> dict[str, Any]:
        tok_a = self.token_de_a()
        resp = self.sessao.get(
            f"{self.api}/api/cart/", headers=auth_headers(tok_a), timeout=10, allow_redirects=False
        )
        resp.raise_for_status()
        return resp.json()


def criar_contexto_cli(
    descricao: str,
    precisa_otp: bool = False,
    aceita_restaurar_carrinho: bool = False,
) -> ContextoT2A:
    """Cria ContextoT2A para execução direta de um script individual aut_eXXX/coletar.py."""
    parser = argparse.ArgumentParser(description=descricao)
    parser.add_argument("--api", default=API_PADRAO, help=f"URL base da API (padrão: {API_PADRAO}).")
    parser.add_argument("--escopo", type=Path, default=OPENAPI_SCOPE_PATH, help="Contrato OpenAPI reduzido.")
    parser.add_argument("--saida", type=Path, default=DEFAULT_SAIDA_DIR, help="Pasta raiz de saída (padrão: results/t2a).")
    if precisa_otp:
        parser.add_argument("--otp-email", default=os.environ.get("OTP_EMAIL_E013"), help="Código OTP de 6 dígitos (opcional).")
    if aceita_restaurar_carrinho:
        parser.add_argument("--restaurar-carrinho", action="store_true", help="Readiciona 1xP1 ao carrinho de A após o teste.")
    args = parser.parse_args()

    saida = args.saida if args.saida.is_absolute() else (ROOT_DIR / args.saida)
    escopo = args.escopo if args.escopo.is_absolute() else (ROOT_DIR / args.escopo)

    return ContextoT2A(
        api_url=args.api,
        saida_dir=saida,
        escopo_path=escopo,
        senha=(os.environ.get("SENHA_EXP") or os.environ.get("SENHA_A") or "").strip() or None,
        token_a=os.environ.get("TOKEN_A", "").strip() or None,
        token_v1=os.environ.get("TOKEN_V1", "").strip() or None,
        otp_email=getattr(args, "otp_email", None),
        restaurar_carrinho=getattr(args, "restaurar_carrinho", False),
    )


def imprimir_resultado_unidade(res: dict[str, Any]) -> None:
    """Exibe resumo padronizado de uma unidade após sua coleta."""
    extra_500 = f" | HTTP 500={res['erros_500']}" if res.get("erros_500") else ""
    print(
        f"[{res['unidade']}] {res['decisao']} | 2xx={res['ok_2xx']} "
        f"| sem_auth={res['rej_sem_auth']} | inv={res['rej_com_auth']}{extra_500}"
    )
    print(f"  Nota: {res['nota']}")
