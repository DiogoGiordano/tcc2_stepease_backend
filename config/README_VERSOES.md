# Registro de ambiente ainda não concluído

`config/versoes.txt` **não foi gerado** porque o commit completo e as versões exatas do ambiente não foram fornecidos. Não preencher com suposições.

Já informado pelo responsável: Python 3.12.3, pip 24.0, tag `experimento-seguranca-v1`, Linux Mint (edição não informada), banco independente operacional (tipo/versão não informados). O identificador de commit apareceu mascarado no histórico informado e não pode ser reconstruído.

## Coleta não sensível sugerida, na worktree (raiz do backend)

```bash
git rev-parse HEAD
git describe --tags --exact-match
git status --short
git rev-parse --show-toplevel
python --version
python -m pip --version
python - <<'PYCODE'
from importlib.metadata import version, PackageNotFoundError
for p in ['fastapi','sqlalchemy','pydantic','httpx','pytest','bandit','schemathesis']:
    try: print(f'{p}={version(p)}')
    except PackageNotFoundError: print(f'{p}=NÃO INSTALADO')
PYCODE
cat /etc/os-release | grep '^PRETTY_NAME='
```

Informar separadamente tipo/versão do SGBD (sem copiar DATABASE_URL, senhas ou tokens), hostname e porta **não sensíveis** usados no ambiente isolado, e eventual versão do ZAP caso instalado. Após isso, gerar o arquivo completo.
