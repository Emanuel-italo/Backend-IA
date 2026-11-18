# Resultados da avaliação

Gerado por `python eval/run_eval.py` em 18/11/2026 22:05 UTC. As seções 1 a 3 são determinísticas e rodam sem chave de API.

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

## 2. Validador de fidelidade (groundedness)

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

## 3. Assistente conversacional: validação e privacidade (offline)

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

## 4. IA generativa real

**Não executado nesta geração do relatório** (sem `--live` ou sem `LLM_API_KEY`/`LLM_MODEL`). Rode `python eval/run_eval.py --live` com a chave do grupo para preencher esta seção com a taxa de aceitação, a latência e as respostas reais das explicações e do assistente conversacional.
