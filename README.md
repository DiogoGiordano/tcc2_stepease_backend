# EXP-SEG-01 — Avaliação Experimental de Segurança da API do Inclusivo

Este repositório reúne os artefatos, scripts de execução, configurações e evidências do protocolo experimental **EXP-SEG-01**, conduzido sobre o backend da plataforma **Inclusivo** (API em Python/FastAPI) na tag `experimento-seguranca-v1`.

O experimento avaliou **29 operações** dos módulos de **Identidade** (15), **Produtos** (8) e **Carrinho** (6) sob três abordagens complementares, investigando regras de autenticação, autorização (titularidade de recursos), diretivas de cache e exposição de dados:

| Tratamento | Abordagem | Instrumentos | Unidades conclusivas (M3) | Desvios confirmados (M1) |
| :--- | :--- | :--- | :---: | :---: |
| **T1** | Análise estática de código (regra `B311`) | Bandit `1.9.4` | 2 / 2 (100,0%) | 0 |
| **T2 (T2A + T2B)** | Avaliação dinâmica por contrato e cabeçalhos HTTP | Schemathesis `4.33.4` + OWASP ZAP `2.17.0` | 22 / 24 (91,7%) | 0 |
| **T3** | Testes dinâmicos guiados por regras de domínio | pytest `9.2.0` + HTTPX | 46 / 52 (88,5%) | 0 |

---

## Estrutura do repositório

```text
.
├── config/                                  # Inventário de rotas, contrato OpenAPI, casos, atores e .env de exemplo
│   ├── README_VERSOES.md                    # Registro das versões do ambiente e ferramentas
│   ├── ambiente_exemplo.env                 # Modelo de variáveis de ambiente (copiar para .env local)
│   ├── inventario_rotas.csv                 # Inventário completo das operações da API
│   ├── inventario_rotas_escopo.csv          # Recorte oficial das 29 operações avaliadas
│   ├── casos_seguranca.csv                  # Catálogo das unidades de avaliação
│   ├── atores_modelo.json                   # Perfis experimentais (compradores A/B e vendedores V1/V2)
│   ├── massa_dados_modelo.json              # Estado inicial de lojas, produtos e carrinhos
│   ├── openapi.json                         # Contrato OpenAPI completo da API
│   └── operacoes_escopo.json                # Definição das operações selecionadas para o recorte
├── scripts/
│   ├── preparar_base_piloto.py              # Prepara/restaura contas, lojas, produtos e carrinhos na base experimental
│   ├── executar_piloto.py                   # Execução piloto para conferência da bancada (fora das métricas)
│   ├── filter_openapi_scope.py              # Gera o contrato OpenAPI reduzido ao escopo do experimento
│   ├── t2a/
│   │   ├── conferir_contrato.py             # Validação do contrato reduzido para o T2A
│   │   └── executar_t2a.py                  # Execução do Schemathesis (verificação ignored_auth)
│   └── t3/
│       ├── helpers.py                       # Utilitários HTTPX, autenticação e registro de evidências
│       ├── test_products_cart.py            # Casos de domínio e autenticação de Produtos e Carrinho
│       ├── test_identity.py                 # Casos de domínio, autenticação e cache do módulo de Identidade
│       ├── executar_bloco1.py               # Executor do Bloco 1 (Produtos e Carrinho)
│       ├── executar_bloco2.py               # Executor do Bloco 2 (Identidade)
│       └── consolidar_experimento.py        # Consolida T1, T2 e T3 nos relatórios finais
├── results/
│   ├── openapi_scope.json                   # Contrato OpenAPI filtrado para as operações do recorte
│   ├── t2a/ e t2a-*.{json,har}              # Relatórios JSON e tráfego HAR (credenciais ocultadas) do T2A
│   ├── t2b/                                 # Hook ZAP (hook_cache.py), evidências de Cache-Control e relatórios
│   ├── t3/                                  # Relatórios JUnit, evidências JSON e registro de restauração da base
│   ├── consolidacao_exp_seg_01.json         # Consolidação estruturada do experimento
│   └── consolidacao_exp_seg_01.md           # Síntese legível dos resultados consolidados
└── experiment/experimento-seguranca/results/
    ├── piloto-http-*/                       # Registros das rodadas piloto da bancada
    └── t1-bandit-20261121-201526/           # Evidências da análise estática (bandit.json, hashes e metadados)
```

---

## Pré-requisitos

Ambiente de referência utilizado na coleta (detalhes completos em `config/README_VERSOES.md`):

- **Sistema:** Linux (testado em Linux Mint)
- **Backend alvo:** API do Inclusivo na tag `experimento-seguranca-v1` (Python `3.12.3`, FastAPI `0.141.1`)
- **Banco de dados:** instância **PostgreSQL dedicada** ao experimento
- **Ferramentas de avaliação:**
  - `bandit` (`1.9.4`)
  - `schemathesis` (`4.33.4`)
  - `OWASP ZAP` (`2.17.0`)
  - `pytest` (`9.2.0`) e `httpx`

---

## Como reproduzir o experimento (visão geral)

> **Importante:** execute sempre contra um banco PostgreSQL dedicado e local, nunca contra bases de produção.

### 1. Configurar ambiente e subir a API alvo

1. Clone o backend do Inclusivo na tag `experimento-seguranca-v1` e suba o serviço localmente conectado ao banco experimental.
2. Copie o arquivo de variáveis de exemplo e preencha os dados da bancada local (URL da API, credenciais de teste e conexão):
   ```bash
   cp config/ambiente_exemplo.env .env
   ```
   *(O arquivo `.env` não é versionado.)*

### 2. Preparar a bancada e gerar o contrato de escopo

1. Popule/restaure os atores experimentais (**A**, **B**, **V1**, **V2**), lojas, produtos e carrinhos iniciais:
   ```bash
   python scripts/preparar_base_piloto.py
   ```
2. *(Opcional)* Execute o piloto para confirmar conectividade, autenticação e estado inicial da bancada:
   ```bash
   python scripts/executar_piloto.py
   ```
3. Gere o contrato OpenAPI restrito às operações do experimento (`results/openapi_scope.json`):
   ```bash
   python scripts/filter_openapi_scope.py
   ```

### 3. Executar os tratamentos

#### T1 — Análise estática (`Bandit`)
Executa a regra `B311` sobre os dois casos de uso de geração de credenciais do módulo de identidade (`request_identity_password_reset.py` e `send_identity_email_two_factor.py`) no repositório do backend, exportando o relatório em JSON e os hashes SHA-256 dos arquivos analisados.

#### T2A — Testes por contrato (`Schemathesis`)
Valida o contrato reduzido e executa a checagem `ignored_auth` nas operações protegidas, gerando os relatórios JSON e os registros de tráfego HAR em `results/t2a/`:
```bash
python scripts/t2a/conferir_contrato.py
python scripts/t2a/executar_t2a.py
```

#### T2B — Inspeção de cabeçalhos HTTP (`OWASP ZAP`)
Executa o ZAP contra as operações autenticadas `GET /api/auth/me` e `GET /api/2fa/status` utilizando o script de hook `results/t2b/hook_cache.py` e o contrato `results/t2b/contrato-cache.json`, verificando a diretiva `Cache-Control: no-store` e salvando as evidências em `results/t2b/`.

#### T3 — Testes guiados por regras de domínio (`pytest` + `HTTPX`)
Restaure o estado inicial da bancada antes de executar os dois blocos de domínio:
```bash
python scripts/preparar_base_piloto.py
python scripts/t3/executar_bloco1.py   # Bloco 1: Produtos e Carrinho (evidencias-products-cart.json e junit-products-cart.xml)
python scripts/t3/executar_bloco2.py   # Bloco 2: Identidade (evidencias-identity.json e junit-identity.xml)
```

### 4. Consolidar os resultados

Reúne os registros de T1, T2 e T3 nos artefatos finais `results/consolidacao_exp_seg_01.json` e `results/consolidacao_exp_seg_01.md`:
```bash
python scripts/t3/consolidar_experimento.py
```

---

## Limitações conhecidas na reprodução

- **Fluxos dependentes de e-mail e provedor externo:** sem uma caixa de captura de e-mail para leitura de códigos/tokens gerados (armazenados em hash no banco) e sem um token válido de login com Google, as unidades `I02`, `I06`, `I07`, `I11`, `I12` e `AUT-E013` executam controles parciais e são registradas como **inconclusivas** (`skipped` no pytest).
- **Criação de produto no T2A (`AUT-E026`):** o envio `multipart/form-data` no exemplo gerado pelo Schemathesis resulta em HTTP `422` (permanecendo inconclusivo em T2A), sendo avaliado de forma conclusiva em T3 com imagem válida.
- **Observações adicionais:** duas respostas HTTP `500` em `GET /api/products/me` (`results/t2a-e028.har`) e alertas informativos/baixos de cabeçalhos do ZAP (`10021` e `90004` em `results/t2b/relatorio-cache.json`) permanecem documentados como achados paralelos fora das regras primárias avaliadas.