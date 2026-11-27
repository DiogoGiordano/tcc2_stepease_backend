# EXP-SEG-01 — Avaliação Experimental de Segurança da API do Inclusivo

Este repositório reúne os artefatos, scripts de execução, configurações e evidências do protocolo experimental **EXP-SEG-01**, conduzido sobre o backend da plataforma **Inclusivo** (API em Python/FastAPI) na tag `experimento-seguranca-v1`.

Na coleta original, o experimento avaliou **29 operações** dos módulos de **Identidade** (15), **Produtos** (8) e **Carrinho** (6) sob três abordagens complementares, investigando regras de autenticação, autorização (titularidade de recursos), diretivas de cache e exposição de dados:

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
│   ├── preparar_base_piloto.py              # Cria uma vez as contas, lojas, produtos e carrinhos na base experimental
│   ├── executar_piloto.py                   # Execução piloto para conferência da bancada (fora das métricas)
│   ├── filter_openapi_scope.py              # Gera o contrato OpenAPI reduzido ao escopo do experimento
│   ├── t1/executar_t1.py                    # Bandit B311 nos dois arquivos de identidade
│   ├── t2a/
│   │   ├── conferir_contrato.py             # Validação do contrato reduzido para o T2A
│   │   ├── executar_t2a.py                  # Conferência da API e do inventário AUT
│   │   └── unidades/                        # Controles positivos e coleta do Schemathesis por unidade
│   │       ├── comum.py                     # Configurações de perfis, catálogo AUT e utilitários comuns
│   │       ├── suporte.py                   # HTTP local, login, TOTP e apoio às execuções
│   │       ├── contrato.py                  # Geração de contrato.json isolado e sanitização de evidências
│   │       ├── runner.py                    # Execução do Schemathesis (ignored_auth, JSON e HAR)
│   │       ├── executar.py                  # Executor dos controles positivos do T2A
│   │       └── e003/ ... e039/              # 22 pastas por unidade (controle positivo e coletar.py)
│   ├── t2b/                                 # executar_t2b.py e hook_cache.py
│   └── t3/
│       ├── restaurar_base.py                # Recompõe a massa de T3 e grava o manifesto
│       ├── helpers.py                       # Utilitários HTTPX, autenticação e registro de evidências
│       ├── test_products_cart.py            # Casos de domínio e autenticação de Produtos e Carrinho
│       ├── test_identity.py                 # Casos de domínio, autenticação e cache do módulo de Identidade
│       ├── executar_bloco1.py               # Executor do Bloco 1 (Produtos e Carrinho)
│       ├── executar_bloco2.py               # Executor do Bloco 2 (Identidade)
│       └── consolidar_experimento.py        # Consolida T1, T2 e T3 nos relatórios finais
├── results/
│   ├── openapi_scope.json                   # Contrato OpenAPI filtrado para as operações do recorte
│   ├── t2a/ e t2a-*.{json,har}              # Relatórios JSON, tráfego HAR sanitizado e fichas de controle do T2A
│   ├── t2b/                                 # Contrato da rodada, evidências de Cache-Control e relatórios
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

Use a cópia local do backend correspondente à tag experimental. Este repositório publica os materiais da avaliação. T1 requer os fontes do backend; T2 e T3 requerem a API em execução. Para a bancada dinâmica, configure o PostgreSQL experimental, ative o ambiente virtual e suba a API em `http://127.0.0.1:8000`. Execute os comandos abaixo a partir da raiz do repositório do experimento.

Use `config/ambiente_exemplo.env` como referência para o ambiente local. O helper de T3 procura `DATABASE_URL` no ambiente, em `.env` ou em `backend/.env`. A configuração dos perfis e dos recursos de T2A fica em `scripts/t2a/unidades/comum.py`.

### 2. Preparar a bancada e gerar o contrato de escopo

1. Somente na primeira preparação, com o backend importável e antes de existirem os e-mails reservados, crie os atores experimentais (**A**, **B**, **V1**, **V2**), lojas, produtos e carrinhos iniciais:
   ```bash
   python scripts/preparar_base_piloto.py
   ```
2. *(Opcional)* Execute o piloto para confirmar conectividade, autenticação e estado inicial da bancada:
   ```bash
   python scripts/executar_piloto.py
   ```
3. Gere o contrato OpenAPI restrito às operações do experimento (`results/openapi_scope.json`):
   ```bash
   python scripts/filter_openapi_scope.py --input config/openapi.json
   ```

### 3. Executar os tratamentos

#### T1 — Análise estática (`Bandit`)

Com o backend em `backend/app/`, instale a versão usada na coleta e execute:

```bash
python -m pip install 'bandit==1.9.4' &&
python scripts/t1/executar_t1.py
```

Se o código estiver em outro checkout, passe `--backend` com o caminho do diretório que contém `app/`. O executor registra o HEAD desse checkout e os hashes dos arquivos lidos. T1 funciona com a API e o banco desligados.

| Unidade | Arquivo em `app/modules/identity/application/use_cases/` |
|---|---|
| EST-E006 | `request_identity_password_reset.py` |
| EST-E012 | `send_identity_email_two_factor.py` |

Cada rodada cria uma pasta `experiment/experimento-seguranca/results/t1-bandit-*/` com o relatório, a versão, os hashes, o commit, a data e o código do Bandit. O terminal mostra linhas processadas e alertas B311 por unidade. O executor normaliza caminhos com e sem `./`. Código 0 indica coleta completa sem alertas; 1 indica achados do Bandit; 2 indica erro ou cobertura incompleta.

#### T2A — Controles positivos e coleta do Schemathesis

O T2A abrange **22 operações** protegidas por autenticação dos módulos de identidade (11), produtos (5) e carrinho (6), organizadas por unidade em `scripts/t2a/unidades/`. A execução divide-se em **conferência do contrato**, **controles positivos** (via `executar.py`) e **coleta do Schemathesis** (via `coletar.py` dentro de cada unidade).

Execute os comandos na raiz do projeto, com o ambiente virtual ativo e a API experimental disponível em `http://127.0.0.1:8000`. A sequência abaixo considera o cliente A com o segundo fator desativado, o produto P1 no carrinho de A com quantidade 1 e o produto P2 no carrinho de B com quantidade 2.

##### 1. Conferir o contrato e o inventário

```bash
python scripts/t2a/executar_t2a.py
```

O resultado esperado é a presença das 29 operações do escopo no contrato publicado e a identificação das 22 unidades AUT no inventário.

##### 2. Controles positivos (`scripts.t2a.unidades.executar`)

Os controles positivos confirmam que o usuário autorizado consegue executar cada operação com a massa experimental e geram fichas individuais `controle-positivo-*.json`. Eles **não** executam o Schemathesis.

> Antes dos blocos com alteração de dados, faça um backup do banco experimental (por exemplo, via **Backup…** em formato **Custom** no pgAdmin) caso deseje repetir a rodada com os mesmos dados e IDs.

- **Leitura (identidade, 2FA, produtos e carrinho):**
  ```bash
  METODO_2FA=desativado python -m scripts.t2a.unidades.executar E003 E015 E028 E034
  ```
  O executor utiliza as contas A e V1 (solicita a senha no terminal ou usa `TOKEN_A`/`TOKEN_V1` quando exportados). `METODO_2FA=desativado` informa o estado esperado pela E015 na base inicial.

- **Atualização de produto e item do carrinho:**
  ```bash
  python -m scripts.t2a.unidades.executar E031 E032 E038
  ```
  E031 e E032 reenviam o nome atual de P1 (`PUT`/`PATCH`); E038 localiza o item de P1 no carrinho de A e reenvia sua quantidade atual.

- **Adição e remoção de P2 no carrinho de A:**
  ```bash
  python -m scripts.t2a.unidades.executar E036 E037 E039
  ```
  E036 adiciona 1 unidade de P2, E037 acrescenta outra em lote e E039 remove a linha de P2, mantendo apenas P1 no carrinho de A.

- **Criação e exclusão de produto temporário:**
  ```bash
  python -m scripts.t2a.unidades.executar E026 E033
  ```
  Execute juntas para que E033 receba o ID criado pela E026. Em caso de `422` na E026, o bloco é interrompido e o fluxo de identidade pode seguir separadamente.

- **Fluxo de segundo fator:**
  ```bash
  python -m scripts.t2a.unidades.executar E008 E009 E010 E011 E012 E013 E014
  ```
  Mantenha as sete unidades na mesma invocação para compartilhar os dados temporários do 2FA. Na E013, pressione Enter caso o código por e-mail não esteja disponível (a ficha registra como inconclusivo e segue para a E014, que desativa o 2FA).

- **Troca e restauração da senha de A:**
  ```bash
  python -m scripts.t2a.unidades.executar E005
  ```
  Informe a senha atual e uma senha temporária; o controle efetua a troca e solicita a restauração da senha original.

- **Limpeza do carrinho e logout:**
  ```bash
  python -m scripts.t2a.unidades.executar E035 E004
  ```
  E035 esvazia o carrinho de A (por isso fica após os demais controles de carrinho) e E004 registra o logout.

##### 3. Coleta do Schemathesis por unidade (`scripts.t2a.unidades.eXXX.coletar`)

Cada unidade possui um módulo `coletar.py` próprio que executa o `schemathesis run` com `--checks ignored_auth --output-sanitize true --report json,har` (10 unidades em `--phases coverage` sobre `results/openapi_scope.json` e 12 em `--phases examples` com `contrato.json` isolado, incluindo as inconclusivas `e026` e `e013`), gerando `relatorio.json`, `trafego.har` e, quando aplicável, `contrato.json`.

Execute cada unidade como módulo (`-m`) a partir da raiz do repositório, informando `--saida` com uma pasta nova para preservar `results/t2a/`:

```bash
SAIDA="results/t2a-repeticao-$(date +%Y%m%d-%H%M%S)"

# Exemplos com perfil V1 (leitura em coverage e atualização em examples)
python -m scripts.t2a.unidades.e028.coletar --saida "$SAIDA"
python -m scripts.t2a.unidades.e032.coletar --saida "$SAIDA"

# Exemplos com perfil A (inserção e remoção no carrinho)
python -m scripts.t2a.unidades.e036.coletar --saida "$SAIDA"
python -m scripts.t2a.unidades.e039.coletar --saida "$SAIDA"
```

Os scripts utilizam `TOKEN_A` ou `TOKEN_V1` quando exportados no ambiente ou solicitam a senha do perfil no terminal. Para uma coleta completa de todas as 22 unidades, siga a ordem de dependências:

1. **Leitura:** `e003`, `e015`, `e028`, `e034`
2. **Produtos:** `e031`, `e032`, `e026` (cria produto descartável) antes de `e033` (remove o descartável)
3. **Carrinho:** `e038`, `e036`, `e037`, `e039` antes de `e035` (esvazia o carrinho de A)
4. **Identidade com mutação:** `e008`, `e009`, `e010`, `e011`, `e012`, `e013`, `e014`, `e005` e `e004`

As unidades sensíveis (`e005`, `e008`, `e009`, `e010` e `e013`) sanitizam segredos, senhas e tokens (`<REDACTED>`) nos artefatos gravados e restauram o 2FA e a senha original da conta A ao final da execução.

##### 4. Localizar as evidências e preparar a próxima rodada

Cada unidade salva seus artefatos em `results/t2a/aut-eXXX/` (`controle-positivo-*.json` na etapa de controles positivos; `relatorio.json`, `trafego.har` e, quando aplicável, `contrato.json` na coleta do Schemathesis). Parte dos relatórios históricos da coleta original do Schemathesis foi salva diretamente em `results/`, com nomes como `t2a-e015.json` e `t2a-e015.har`.

Se a próxima rodada exigir a mesma linha de base, restaure o backup do banco feito antes das mutações. O script `preparar_base_piloto.py` serve apenas para a criação inicial da massa e interrompe a execução quando encontra as contas experimentais já cadastradas.

#### T2B — Inspeção de cabeçalhos HTTP (`OWASP ZAP`)

Com Docker disponível no Linux e uma sessão válida da conta A, execute em uma pasta nova para preservar a coleta original:

```bash
python scripts/t2b/executar_t2b.py --saida "results/t2b-repeticao-$(date +%Y%m%d-%H%M%S)"
```

O executor lê `TOKEN_A` ou pede o token, restringe o contrato aos GETs `/api/auth/me` e `/api/2fa/status` e carrega o hook de `scripts/t2b/`. Em `evidencia-cache.json`, confira para cada rota uma resposta autenticada HTTP 200 e a presença de `no-store` em `Cache-Control`. O consolidador utiliza a coleta de `results/t2b/`; uma repetição em outra pasta deve ser analisada separadamente.

#### T3 — Testes guiados por regras de domínio (pytest + HTTPX)

Para uma nova campanha, preserve primeiro os arquivos anteriores de `results/t3/`: os executores reutilizam nomes fixos. Com as quatro contas existentes e as senhas válidas, execute:

```bash
python scripts/t3/restaurar_base.py --banco inclusivo_experiment_backend
```

Use o nome efetivo do PostgreSQL experimental. O script confere o banco conectado, desativa o 2FA das quatro contas, repõe o estoque de P1/P2 em 10 e recria os itens de A e B com quantidades 1 e 2. Os novos IDs ficam em `results/t3/restauracao-base.json`. As senhas precisam estar corretas antes da restauração.

```bash
python scripts/t3/executar_bloco1.py
python scripts/t3/executar_bloco2.py
```

O bloco 1 avalia 25 unidades de produtos e carrinho. O bloco 2 avalia 27 de identidade. Ambos usam pytest e produzem evidências JSON e relatórios JUnit em `results/t3/`.

### 4. Consolidar os resultados

Reúne os registros de T1, T2 e T3 nos artefatos finais `results/consolidacao_exp_seg_01.json` e `results/consolidacao_exp_seg_01.md`:

```bash
python scripts/t3/consolidar_experimento.py
```

---

O consolidador seleciona a última pasta de T1 pelo nome e aplica a presença de erros ou alertas do relatório às duas unidades. Em uma nova rodada, confira as métricas e os achados por arquivo antes de aceitar as classificações de T1. Para comparar campanhas, conserve os artefatos de entrada de cada rodada.

## Limitações conhecidas na reprodução

- **Fluxos dependentes de e-mail e provedor externo:** sem uma caixa de captura de e-mail para leitura de códigos/tokens gerados (armazenados em hash no banco) e sem um token válido de login com Google, as unidades `I02`, `I06`, `I07`, `I11`, `I12` e `AUT-E013` executam controles parciais e são registradas como **inconclusivas** (`skipped` no pytest).
- **Criação de produto no T2A (`AUT-E026`):** o envio `multipart/form-data` no exemplo gerado pelo Schemathesis resulta em HTTP `422` (permanecendo inconclusivo em T2A), sendo avaliado de forma conclusiva em T3 com imagem válida.
- **Observações adicionais:** duas respostas HTTP `500` em `GET /api/products/me` (`results/t2a-e028.har`) e alertas informativos/baixos de cabeçalhos do ZAP (`10021` e `90004` em `results/t2b/relatorio-cache.json`) permanecem documentados como achados paralelos fora das regras primárias avaliadas.