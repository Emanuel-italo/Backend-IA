# Resultados da avaliação

Gerado por `python eval/run_eval.py` em 18/11/2026 00:31 UTC. As seções 1 a 6 são determinísticas e rodam sem chave de API.

## 1. Recuperação (RAG básico)

Conjunto: 22 perguntas escritas à mão em linguagem de usuário + 8 perguntas fora do domínio (`eval/retrieval_cases.json`). Base: 13 trechos. Limiar de similaridade: 0.15.

| Métrica | Valor |
|---|---|
| hit@1 | 19/22 (86%) |
| hit@3 | 22/22 (100%) |
| MRR@3 | 0.932 |
| Fora do domínio corretamente rejeitadas | 7/8 |

Erros de primeira posição:

- "elevador parado no metrô e estou com carrinho de bebê" → veio `kb-onibus-acessivel`, esperado `kb-elevador-fora` (esperado na posição 2)
- "tenho direito a sentar no ônibus estando grávida?" → veio `kb-escadas-gestante`, esperado `kb-prioridade-lei` (esperado na posição 2)
- "como funciona o atende da sptrans" → veio `kb-elevador-fora`, esperado `kb-sem-rota-acessivel` (esperado na posição 2)

Fora do domínio que passaram pelo limiar (falso positivo):

- "previsão do tempo para amanhã"

## 2. Consultas que o próprio sistema gera

Na aplicação, a consulta ao RAG é montada a partir dos códigos de problema do score (não é texto livre do usuário). Para cada código, o trecho esperado precisa estar entre os 2 recuperados.

**Resultado: 10/10** (códigos sem consulta dedicada: ['escada_rolante'])

| Código do problema | Esperado | Recuperados (top 2) | |
|---|---|---|---|
| `bloqueio` | `kb-sem-rota-acessivel` | kb-sem-rota-acessivel, kb-onibus-acessivel | ok |
| `escadas` | `kb-escadas-gestante` | kb-escadas-gestante, kb-elevador-fora | ok |
| `elevador_incerto` | `kb-elevador-fora` | kb-elevador-fora | ok |
| `caminhada_longa` | `kb-caminhada-longa` | kb-caminhada-longa | ok |
| `ladeira` | `kb-ladeira-rampa` | kb-ladeira-rampa | ok |
| `calcada_ruim` | `kb-calcada-ruim` | kb-calcada-ruim | ok |
| `sem_cobertura` | `kb-ponto-sem-cobertura` | kb-ponto-sem-cobertura | ok |
| `sem_assento` | `kb-prioridade-lei` | kb-prioridade-lei, kb-baldeacao | ok |
| `baldeacao` | `kb-baldeacao` | kb-baldeacao | ok |
| `sem_dados` | `kb-sem-dados` | kb-sem-dados | ok |

## 3. Reordenação por perfil (cenário de demonstração)

Linha de base (app comum, mais rápida primeiro): `r1-metro-se > r4-metro-ladeira > r2-onibus-direto > r3-metro-onibus`

| Perfil | Ordem do Rota Leve (nota) | 1ª da linha de base para este perfil |
|---|---|---|
| gestante | r2-onibus-direto (100) > r3-metro-onibus (83) > r1-metro-se (59) > r4-metro-ladeira (48) | com_ressalvas, nota 59 |
| cadeirante | r2-onibus-direto (100) > r3-metro-onibus (90) > r4-metro-ladeira (34) > r1-metro-se (25, bloqueada) | nao_recomendada (bloqueada), nota 25 |
| carrinho | r2-onibus-direto (100) > r3-metro-onibus (88) > r4-metro-ladeira (54) > r1-metro-se (25, bloqueada) | nao_recomendada (bloqueada), nota 25 |
| idoso | r2-onibus-direto (100) > r3-metro-onibus (73) > r1-metro-se (58) > r4-metro-ladeira (42) | com_ressalvas, nota 58 |
| mobilidade_temporaria | r2-onibus-direto (93) > r3-metro-onibus (65) > r1-metro-se (34) > r4-metro-ladeira (32) | nao_recomendada, nota 34 |

Em 5 de 5 perfis a rota que o app comum mostraria primeiro **não** é recomendada pelo critério de acessibilidade. Os critérios esperados (rota bloqueada no fim, relato expirado ignorado, relato não confirmado não bloqueia etc.) são verificados automaticamente em `tests/test_scoring.py`.

## 4. Validador de fidelidade (groundedness)

16 respostas simuladas de LLM para a rota `r1-metro-se` / perfil `cadeirante` (`eval/groundedness_cases.json`): fiéis devem passar, infiéis devem ser barradas.

| | Barrada | Aceita |
|---|---|---|
| Resposta infiel | 7 | 3 |
| Resposta fiel | 0 | 6 |

Precisão do bloqueio: 100% · Recall do bloqueio: 70%

Respostas infiéis que **passaram** (limitação conhecida do validador heurístico):

- (entidade) "A rota passa pela Estação Luz, que tem elevadores novos."
- (parafrase) "O elevador da Sé já voltou a operar, então o acesso está liberado."
- (conselho) "Como você tem uma lesão na coluna, evite esta rota."

## 5. Situações de falha

| Situação | Comportamento observado |
|---|---|
| LLM fora do ar (timeout) | 20/20 rotas continuam com explicação (template), motivo registrado: ['llm_indisponivel'] |
| LLM devolve JSON fora do formato | 20/20 rotas continuam com explicação (template), motivo registrado: ['formato_invalido'] |
| Nenhuma rota acessível para o perfil | rota marcada `nao_recomendada`, resumo: "Esta rota não é indicada para pessoa em cadeira de rodas: há um trecho sem acesso adequado. São 22 min de viagem e 600 m de caminhada." · trechos usados: ['kb-sem-rota-acessivel', 'kb-onibus-acessivel'] |
| Perfil vazio, perfil inexistente, lista de rotas vazia, rota sem trechos | HTTP 422 (`tests/test_api.py`) |
| Relato expirado | ignorado no score (`tests/test_scoring.py`) |
| Parada sem correspondência no catálogo | penalidade `sem_dados` + aviso, sem inventar atributos |

## 6. Assistente conversacional: validação e privacidade (offline)

9 respostas simuladas do modelo passam pelo mesmo caminho do `POST /v1/chat` (`eval/chat_cases.json`): fiéis devem ser aceitas, infiéis devem cair na resposta de reserva.

| Tipo | Resposta simulada | Resultado | |
|---|---|---|---|
| fiel | A rota com menos caminhada é Ônibus 701A direto, com 350 m a pé. | aceita | ok |
| fiel | Ônibus 701A direto leva 31 min. | aceita | ok |
| número dito pela pessoa | Com 8 meses, evite Metrô até Anhangabaú + caminhada, que tem 950 m a pé. | aceita | ok |
| fora do escopo | Só consigo ajudar com rotas e acessibilidade no transporte público. | aceita | ok |
| distância inventada | Ônibus 701A direto tem só 120 m de caminhada. | barrada (numero_nao_fundamentado:120) | ok |
| tempo inventado | Pela Sé você chega em 12 min. | barrada (numero_nao_fundamentado:12) | ok |
| contradiz rota bloqueada | Metrô Linha 3-Vermelha até a Sé é totalmente acessível para você. | barrada (contradiz_bloqueio:totalmente acessivel) | ok |
| contradiz relato de elevador | Na Sé o elevador em operação facilita a sua ida. | barrada (contradiz_elevador:elevador em operacao) | ok |
| estação inventada, sem número | A estação Paraíso tem elevador novo e é uma boa alternativa. | aceita | passou (limitação) |

Respostas fiéis aceitas: 4/4 · infiéis barradas: 4/5 (precisão do bloqueio 100%, recall 80%).

| Verificação | Resultado |
|---|---|
| Dados pessoais digitados no chat (e-mail, CPF, telefone) chegam ao prompt do modelo? | 3/3 mascarados |
| Modelo fora do ar | resposta de reserva com trecho da base (`llm_indisponivel`, trecho `kb-elevador-fora`) |
| Conversa vazia, última mensagem do assistente, papel `system`, mensagem acima de 1000 caracteres | HTTP 422 (`tests/test_chat.py`) |

## 7. IA generativa real

**Não executado nesta geração do relatório** (sem `--live` ou sem `LLM_API_KEY`/`LLM_MODEL`). Rode `python eval/run_eval.py --live` com a chave do grupo para preencher esta seção com a taxa de aceitação, a latência e as respostas reais das explicações e do assistente conversacional.
