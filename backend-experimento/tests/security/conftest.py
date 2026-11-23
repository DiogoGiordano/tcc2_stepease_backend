"""Fixtures HTTP para o experimento de segurança.

Somente a conexão HTTP é disponibilizada nesta etapa. Contas, tokens e
recursos dependem do mapeamento do estado produzido pelos instrumentos de seed.
"""
import os
import httpx
import pytest


@pytest.fixture
def api_client():
    """Cria um cliente HTTP com URL explicitamente configurada.

    Yields:
        httpx.Client: Cliente da API experimental.

    Raises:
        RuntimeError: URL não fornecida.
    """
    base_url=os.getenv('EXPERIMENT_BASE_URL')
    if not base_url:
        raise RuntimeError('Configure EXPERIMENT_BASE_URL antes de executar Pytest.')
    with httpx.Client(base_url=base_url, timeout=15.0) as client:
        yield client
