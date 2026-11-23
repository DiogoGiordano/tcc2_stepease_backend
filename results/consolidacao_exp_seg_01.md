# Consolidação EXP-SEG-01 (T1, T2 e T3)

## Resumo M3 (Cobertura Interpretável)

| Abordagem | n/N | % | Conformes | Desvios | Inconclusivas | Não executadas |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **T1 (Bandit)** | 2/2 | 100.0% | 2 | 0 | 0 | 0 |
| **T2 (Schemathesis + ZAP)** | 22/24 | 91.7% | 22 | 0 | 2 | 0 |
| **T3 (Pytest + HTTPX)** | 46/52 | 88.5% | 46 | 0 | 6 | 0 |

## Interseção Comparável T2 × T3 (M2)
- Planejadas em comum: **24** (22 AUT + 2 CACHE)
- Efetivamente comparáveis: **22/24**
- Inconclusivas em T2: AUT-E013, AUT-E026
- Inconclusivas em T3: I02, I06, I07, I11, I12, AUT-E013

## Sinais Adicionais (fora do denominador M3)
- T2A (AUT-E028): observada(s) 2 resposta(s) HTTP 500 no HAR (results/t2a-e028.har).
- T2B-ZAP alerta [90004] Low (Medium): Cross-Origin-Resource-Policy Header Missing or Invalid (x2).
- T2B-ZAP alerta [10021] Low (Medium): X-Content-Type-Options Header Missing (x2).

## Matriz Completa (54 Unidades)

| Unidade | T1 | T2 | T3 |
| :--- | :--- | :--- | :--- |
| I01 | nao_aplicavel | nao_aplicavel | conforme |
| I02 | nao_aplicavel | nao_aplicavel | inconclusiva |
| I03 | nao_aplicavel | nao_aplicavel | conforme |
| I04 | nao_aplicavel | nao_aplicavel | conforme |
| I05 | nao_aplicavel | nao_aplicavel | conforme |
| I06 | nao_aplicavel | nao_aplicavel | inconclusiva |
| I07 | nao_aplicavel | nao_aplicavel | inconclusiva |
| I08 | nao_aplicavel | nao_aplicavel | conforme |
| I09 | nao_aplicavel | nao_aplicavel | conforme |
| I10 | nao_aplicavel | nao_aplicavel | conforme |
| I11 | nao_aplicavel | nao_aplicavel | inconclusiva |
| I12 | nao_aplicavel | nao_aplicavel | inconclusiva |
| I13 | nao_aplicavel | nao_aplicavel | conforme |
| I14 | nao_aplicavel | nao_aplicavel | conforme |
| P01 | nao_aplicavel | nao_aplicavel | conforme |
| P02 | nao_aplicavel | nao_aplicavel | conforme |
| P03 | nao_aplicavel | nao_aplicavel | conforme |
| P04 | nao_aplicavel | nao_aplicavel | conforme |
| P05 | nao_aplicavel | nao_aplicavel | conforme |
| P06 | nao_aplicavel | nao_aplicavel | conforme |
| P07 | nao_aplicavel | nao_aplicavel | conforme |
| P08 | nao_aplicavel | nao_aplicavel | conforme |
| C01 | nao_aplicavel | nao_aplicavel | conforme |
| C02 | nao_aplicavel | nao_aplicavel | conforme |
| C03 | nao_aplicavel | nao_aplicavel | conforme |
| C04 | nao_aplicavel | nao_aplicavel | conforme |
| C05 | nao_aplicavel | nao_aplicavel | conforme |
| C06 | nao_aplicavel | nao_aplicavel | conforme |
| AUT-E003 | nao_aplicavel | conforme | conforme |
| AUT-E004 | nao_aplicavel | conforme | conforme |
| AUT-E005 | nao_aplicavel | conforme | conforme |
| AUT-E008 | nao_aplicavel | conforme | conforme |
| AUT-E009 | nao_aplicavel | conforme | conforme |
| AUT-E010 | nao_aplicavel | conforme | conforme |
| AUT-E011 | nao_aplicavel | conforme | conforme |
| AUT-E012 | nao_aplicavel | conforme | conforme |
| AUT-E013 | nao_aplicavel | inconclusiva | inconclusiva |
| AUT-E014 | nao_aplicavel | conforme | conforme |
| AUT-E015 | nao_aplicavel | conforme | conforme |
| AUT-E026 | nao_aplicavel | inconclusiva | conforme |
| AUT-E028 | nao_aplicavel | conforme | conforme |
| AUT-E031 | nao_aplicavel | conforme | conforme |
| AUT-E032 | nao_aplicavel | conforme | conforme |
| AUT-E033 | nao_aplicavel | conforme | conforme |
| AUT-E034 | nao_aplicavel | conforme | conforme |
| AUT-E035 | nao_aplicavel | conforme | conforme |
| AUT-E036 | nao_aplicavel | conforme | conforme |
| AUT-E037 | nao_aplicavel | conforme | conforme |
| AUT-E038 | nao_aplicavel | conforme | conforme |
| AUT-E039 | nao_aplicavel | conforme | conforme |
| CACHE-E003 | nao_aplicavel | conforme | conforme |
| CACHE-E015 | nao_aplicavel | conforme | conforme |
| EST-E006 | conforme | nao_aplicavel | nao_aplicavel |
| EST-E012 | conforme | nao_aplicavel | nao_aplicavel |
