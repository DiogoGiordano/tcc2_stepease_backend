"""Utilitários compartilhados da suíte T3 (EXP-SEG-01)."""

from __future__ import annotations

import json
import os
import struct
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import create_engine, text

API_BASE_URL = "http://127.0.0.1:8000"
ROOT_DIR = Path(__file__).resolve().parents[2]
RESULTS_T3_DIR = ROOT_DIR / "results" / "t3"
OPENAPI_SCOPE_PATH = ROOT_DIR / "results" / "openapi_scope.json"
RESTAURACAO_PATH = RESULTS_T3_DIR / "restauracao-base.json"


def ler_database_url() -> str:
    """Resolve DATABASE_URL do ambiente ou dos arquivos .env da worktree."""
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        for candidato in (ROOT_DIR / ".env", ROOT_DIR / "backend" / ".env"):
            if not candidato.exists():
                continue
            for linha in candidato.read_text(encoding="utf-8").splitlines():
                linha = linha.strip()
                if linha.startswith("DATABASE_URL=") and not linha.startswith("#"):
                    valor = linha.split("=", 1)[1].strip().strip('"').strip("'")
                    if valor:
                        url = valor
                        break
            if url:
                break
    if not url:
        raise RuntimeError("DATABASE_URL não encontrada no ambiente nem em .env / backend/.env.")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


def criar_engine():
    """Cria engine SQLAlchemy para conferência de persistência no banco experimental."""
    return create_engine(ler_database_url())


def carregar_manifesto() -> dict[str, Any]:
    """Lê o manifesto gerado na restauração da base experimental."""
    if not RESTAURACAO_PATH.exists():
        raise FileNotFoundError(
            f"Manifesto não encontrado em {RESTAURACAO_PATH}. Execute a restauração da base primeiro."
        )
    return json.loads(RESTAURACAO_PATH.read_text(encoding="utf-8"))


def carregar_openapi() -> dict[str, Any]:
    """Lê o contrato OpenAPI reduzido do experimento."""
    return json.loads(OPENAPI_SCOPE_PATH.read_text(encoding="utf-8"))


def png_1x1() -> bytes:
    """Gera uma imagem PNG válida de 1x1 pixel para testes de upload multipart."""
    def _chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00\xff\x00\x00")
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")


def auth_headers(token: str) -> dict[str, str]:
    """Monta o cabeçalho Authorization Bearer."""
    return {"Authorization": f"Bearer {token.strip()}"}


def login_ator(client: httpx.Client, email: str, password: str) -> dict[str, Any]:
    """Executa login local de um ator da massa de referência."""
    resp = client.post(
        "/api/auth/login",
        json={"email": email, "password": password, "remember_me": False},
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Login falhou para {email}: HTTP {resp.status_code} | {resp.text[:200]}")
    return resp.json()


def db_produto_meta(engine, product_id: int) -> dict[str, Any] | None:
    """Consulta metadados persistidos de um produto no PostgreSQL experimental."""
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, name, seller_id, price, stock, version FROM products WHERE id = :pid"),
            {"pid": product_id},
        ).mappings().first()
        return dict(row) if row else None


def limpar_produto_descartavel(
    client: httpx.Client,
    engine,
    product_id: int,
    owner_token: str | None = None,
) -> None:
    """Remove produto descartável criado nos testes, preservando P1 (27) e P2 (28)."""
    if product_id in (27, 28):
        raise ValueError("Recusado apagar produto de referência P1/P2.")
    if owner_token:
        try:
            client.delete(f"/api/products/{product_id}", headers=auth_headers(owner_token))
        except httpx.HTTPError:
            pass
    if db_produto_meta(engine, product_id) is not None:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM cart_items WHERE product_id = :pid"), {"pid": product_id})
            conn.execute(text("DELETE FROM products WHERE id = :pid"), {"pid": product_id})


class RegistradorEvidencias:
    """Mantém e persiste o registro sanitizado das unidades T3."""

    def __init__(self, destino: Path):
        self.destino = destino
        self.destino.parent.mkdir(parents=True, exist_ok=True)
        self.registros: dict[str, dict[str, Any]] = {}
        if self.destino.exists():
            try:
                dados = json.loads(self.destino.read_text(encoding="utf-8"))
                for item in dados.get("unidades", []):
                    self.registros[item["unidade"]] = item
            except ValueError:
                pass

    def registrar(
        self,
        unidade: str,
        modulo: str,
        operacao: str,
        perfil: str,
        regra: str,
        decisao: str,
        justificativa: str,
        evidencia: dict[str, Any],
    ) -> None:
        self.registros[unidade] = {
            "unidade": unidade,
            "tratamento": "T3",
            "instrumento": "pytest+httpx",
            "modulo": modulo,
            "operacao": operacao,
            "data_utc": datetime.now(timezone.utc).isoformat(),
            "perfil": perfil,
            "regra": regra,
            "decisao": decisao,
            "justificativa": justificativa,
            "evidencia": evidencia,
        }
        self._salvar()

    def _salvar(self) -> None:
        payload = {
            "atualizado_em": datetime.now(timezone.utc).isoformat(),
            "total_unidades": len(self.registros),
            "unidades": [self.registros[k] for k in sorted(self.registros)],
        }
        self.destino.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
