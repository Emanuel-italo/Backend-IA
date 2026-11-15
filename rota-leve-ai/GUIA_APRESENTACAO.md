# Guia de apresentação (uso interno do grupo)

A apresentação presencial vale 30% da nota e tem 4 critérios de 25 pontos. Este arquivo é material de estudo; pode ser removido do repositório antes da entrega.

## 1. Funcionamento — roteiro de demo (3 a 4 min)

1. **Cena.** "A Júlia está grávida de 8 meses e vai ao pré-natal." Mostre a ordem do app comum: `python scripts/demo.py gestante` imprime na primeira linha a ordem por tempo, com o metrô via Sé em 1º.
2. **Mesma busca no Rota Leve.** O ônibus direto sobe para 1º; o metrô via Sé cai para 3º com "-36: elevador fora de operação, 3 lances de escada". Leia a explicação gerada.
3. **Troque o perfil:** `python scripts/demo.py cadeirante`. A mesma rota vira bloqueada e vai para o fim. O perfil muda a resposta.
4. **API integrada.** Abra `http://localhost:8000/docs`, execute `POST /v1/routes/rank`. Mostre `source: "llm"` e `kb_refs` (de onde veio a dica).
5. **Falha ao vivo.** Suba a API com uma chave inválida (`GEMINI_API_KEY=x`) e repita: a resposta vem igual, com `source: "template_fallback"` e `fallback_reason: "llm_indisponivel"`.

Antes do dia: rode a demo com a chave real pelo menos duas vezes e tenha um print de reserva, caso a rede da sala falhe.

## 2. Domínio técnico — o que cada integrante precisa saber explicar

- **Quem decide e quem redige.** O score (regras) decide a ordem. O LLM só escreve o texto a partir dos fatos. Se o LLM sumir, a ordenação não muda.
- **O que é o RAG aqui.** Os códigos de problema da rota viram uma consulta; o TF-IDF devolve até 2 trechos da base; eles entram no prompt como CONTEXTO; a dica só pode sair dali.
- **Por que TF-IDF e não embeddings.** Base de 13 trechos, determinístico, offline, avaliável. Limite: não entende sinônimo distante.
- **Por que regras e não ML no score.** Sem dados rotulados reais, um modelo treinado em dados sintéticos só reaprenderia as nossas regras.
- **Validação.** Todo número do texto precisa existir nos fatos ou no contexto; frases que contradizem bloqueio ou elevador fora são barradas. Recall de 70%: saiba citar os 3 tipos que escapam.
- **Relatos.** Ativo < 72 h desde a última confirmação; 2+ confirmações = confirmado e pode bloquear; 1 = incerto, meia penalidade.
- **Privacidade.** Só o tipo de perfil chega ao serviço e ao provedor do modelo.

Perguntas prováveis e resposta curta:

| Pergunta | Resposta |
|---|---|
| E se o modelo inventar um elevador? | Número inventado e contradição literal são barrados; paráfrase pode passar. Por isso a nota e o `breakdown` (que não vêm do LLM) aparecem sempre junto do texto. |
| Por que a temperatura não está configurada? | Os modelos Gemini atuais não aceitam mais parâmetros de amostragem. A consistência vem do prompt restrito, da saída em JSON e da validação. |
| Como sabem que o RAG funciona? | 22 perguntas anotadas: hit@3 de 100%, hit@1 de 86%. E 10 de 10 nas consultas que o sistema realmente gera. |
| Isso escala? | O serviço não guarda estado; sobe N réplicas em contêiner. Gargalo é a chamada ao LLM, limitada às 3 melhores rotas e com cache. |
| De onde vêm os dados reais? | Rotas: Google Directions. Relatos: API .NET. Catálogo: dados abertos + gestor. No repositório são sintéticos e isso está declarado. |

## 3. Capacidade de adaptação — mudanças que o professor pode propor

Para cada uma: **onde mexe** e **o que não muda**.

| Mudança proposta | Como adaptar |
|---|---|
| "Adicionem o perfil pessoa com deficiência visual." | Novo valor em `Profile` (`models.py`) + uma linha em `RULES` (`scoring.py`). Provavelmente novos atributos no catálogo (piso tátil, semáforo sonoro) e novos tipos de relato. Novos trechos na base com `perfis: ["deficiencia_visual"]`. API, RAG e LLM não mudam. |
| "Troquem o Gemini por um modelo local ou outro provedor." | Nova classe com o método `generate_json(system, user)` em `llm.py` e a escolha em `main.get_ranker`. Prompt, validação e fallback continuam iguais. |
| "A base de conhecimento passou a ter 5 mil documentos." | Trocar a implementação de `Retriever` por embeddings + banco vetorial (Azure AI Search, pgvector), mantendo `search(query, profile, k)`. Reavaliar com `eval/run_eval.py`. Acrescentar divisão dos documentos em trechos. |
| "O usuário quer perguntar em texto livre ('tem banheiro na estação?')." | Novo endpoint que usa o mesmo `Retriever` com a pergunta do usuário e o mesmo fluxo prompt → validação. Atenção ao limiar fora do domínio (hoje 7 de 8) e a ataques por prompt. |
| "Usem a foto do relato." | Novo módulo de visão (modelo multimodal ou classificador pré-treinado) que devolve o `kind` do relato. Entra antes do score, na API de relatos; o score já consome `kind`. |
| "Considerem chuva." | Buscar o clima em uma API, passar um indicador para `score_route` e aumentar a penalidade de `sem_cobertura` e de caminhada. É mais um fato no dicionário `facts`, então o LLM passa a mencioná-lo. |
| "Quero a explicação em espanhol/inglês." | Parâmetro `lang` na requisição, repassado ao prompt; o template de fallback precisa de tradução. Fatos e validação de números não mudam. |
| "O relato precisa de 3 confirmações para bloquear." | Constante `CONFIRMED_MIN` em `reports.py`. Os testes de `test_scoring.py` mostram o que muda. |
| "Rodem sem internet (comunidade com conectividade ruim)." | Score, ordenação, RAG e template já funcionam offline. Só a redação pelo LLM depende de rede; o fallback cobre. |

## 4. Participação

Sugestão de divisão para todos falarem: (1) problema e cena; (2) demo; (3) arquitetura e fluxo; (4) RAG e avaliação; (5) limitações, privacidade e a resposta à mudança proposta.
