from __future__ import annotations

import json
import logging
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import grounding
from app.catalog import Catalog
from app.chat import ChatAssistant
from app.explain import Explainer
from app.config import Settings
from app.llm import LLMError, build_llm
from app.models import ChatMessage, Profile, Route
from app.rag import Retriever, build_query
from app.reports import ReportStore
from app.scoring import route_place_ids, score_route
from app.service import RouteRanker

logging.disable(logging.WARNING)
DATA, EVAL = ROOT / "data", ROOT / "eval"
NOW = datetime.now(timezone.utc)
out: list[str] = []


def w(line: str = "") -> None:
    out.append(line)


catalog = Catalog.from_file(DATA / "pontos.json")
store = ReportStore.from_seed(DATA / "relatos.json", now=NOW)
retriever = Retriever.from_file(DATA / "base_conhecimento.json")
routes = [Route(**r) for r in json.loads((DATA / "rotas_demo.json").read_text(encoding="utf-8"))["rotas"]]
ranker = RouteRanker(catalog, store, Explainer(retriever, llm=None))

w("# Resultados da avaliação")
w()
w(f"Gerado por `python eval/run_eval.py` em {NOW:%d/%m/%Y %H:%M} UTC. "
  "As seções 1 a 3 são determinísticas e rodam sem chave de API.")

# 1 - RAG
cases = json.loads((EVAL / "retrieval_cases.json").read_text(encoding="utf-8"))
hit1 = hit3 = 0
rr: list[float] = []
misses = []
for c in cases["casos"]:
    ids = [h.chunk.id for h in retriever.search(c["q"], Profile(c["perfil"]), k=3)]
    rank = ids.index(c["esperado"]) + 1 if c["esperado"] in ids else None
    hit1 += rank == 1
    hit3 += rank is not None
    rr.append(1 / rank if rank else 0.0)
    if rank != 1:
        misses.append((c["q"], c["esperado"], ids[0] if ids else "(vazio)", rank))
n = len(cases["casos"])
ood = cases["fora_do_dominio"]
ood_leaks = [q for q in ood if retriever.search(q, None, k=1)]

w()
w("## 1. Recuperação (RAG básico)")
w()
w(f"Conjunto: {n} perguntas escritas à mão em linguagem de usuário + {len(ood)} perguntas fora do domínio "
  f"(`eval/retrieval_cases.json`). Base: {len(retriever.chunks)} trechos. Limiar de similaridade: {retriever.min_score}.")
w()
w("| Métrica | Valor |")
w("|---|---|")
w(f"| hit@1 | {hit1}/{n} ({hit1 / n:.0%}) |")
w(f"| hit@3 | {hit3}/{n} ({hit3 / n:.0%}) |")
w(f"| MRR@3 | {statistics.mean(rr):.3f} |")
w(f"| Fora do domínio corretamente rejeitadas | {len(ood) - len(ood_leaks)}/{len(ood)} |")
if misses:
    w()
    w("Erros de primeira posição:")
    w()
    for q, exp, got, rank in misses:
        pos = f"esperado na posição {rank}" if rank else "esperado fora do top 3"
        w(f"- \"{q}\" → veio `{got}`, esperado `{exp}` ({pos})")
if ood_leaks:
    w()
    w("Fora do domínio que passaram pelo limiar (falso positivo):")
    w()
    for q in ood_leaks:
        w(f"- \"{q}\"")

# 2 - validador
g = json.loads((EVAL / "groundedness_cases.json").read_text(encoding="utf-8"))
route = next(r for r in routes if r.id == g["rota"])
gp = Profile(g["perfil"])
facts = score_route(route, gp, catalog, store.active_for(route_place_ids(route), NOW)).facts
hits = retriever.search(build_query(facts["perfil"], facts["codigos"]), gp, 2)
ctx = [h.chunk.texto for h in hits]
tp = fp = tn = fn = 0
escaped = []
wrongly_blocked = []
for c in g["casos"]:
    accepted, _ = grounding.check(c["texto"], facts, ctx)
    if c["fiel"]:
        tn += accepted
        fp += not accepted
        if not accepted:
            wrongly_blocked.append(c)
    else:
        tp += not accepted
        fn += accepted
        if accepted:
            escaped.append(c)
w()
w("## 2. Validador de fidelidade (groundedness)")
w()
w(f"{len(g['casos'])} respostas simuladas de LLM para a rota `{g['rota']}` / perfil `{g['perfil']}` "
  "(`eval/groundedness_cases.json`): fiéis devem passar, infiéis devem ser barradas.")
w()
w("| | Barrada | Aceita |")
w("|---|---|---|")
w(f"| Resposta infiel | {tp} | {fn} |")
w(f"| Resposta fiel | {fp} | {tn} |")
w()
prec = tp / (tp + fp) if tp + fp else 0
rec = tp / (tp + fn) if tp + fn else 0
w(f"Precisão do bloqueio: {prec:.0%} · Recall do bloqueio: {rec:.0%}")
if escaped:
    w()
    w("Respostas infiéis que **passaram** (limitação conhecida do validador heurístico):")
    w()
    for c in escaped:
        w(f"- ({c['tipo']}) \"{c['texto']}\"")
if wrongly_blocked:
    w()
    w("Respostas fiéis barradas indevidamente:")
    w()
    for c in wrongly_blocked:
        w(f"- \"{c['texto']}\"")


class Broken:
    name = "broken"

    def generate_json(self, system, user):
        raise LLMError("timeout simulado")


# 3 - chat sem internet
chat_cases = json.loads((EVAL / "chat_cases.json").read_text(encoding="utf-8"))
facts_by_profile = {p: ranker.route_facts(p, routes, now=NOW) for p in Profile}


class Fixed:
    name = "simulado"

    def __init__(self, response):
        self.response, self.last_user = response, ""

    def generate_json(self, system, user):
        self.last_user = user
        return self.response


def ask(text: str, history=()) -> list[ChatMessage]:
    return [*(ChatMessage(**m) for m in history), ChatMessage(role="user", content=text)]


ctp = cfp = ctn = cfn = 0
chat_rows = []
for c in chat_cases["simulados"]:
    p = Profile(c["perfil"])
    r = ChatAssistant(retriever, Fixed(c["resposta"])).reply(p, ask(c["pergunta"]), facts_by_profile[p])
    accepted = r.source == "llm"
    if c["fiel"]:
        ctn += accepted
        cfp += not accepted
    else:
        ctp += not accepted
        cfn += accepted
    ok = accepted == c["fiel"]
    chat_rows.append((c["tipo"], c["resposta"]["resposta"], "aceita" if accepted else f"barrada ({r.fallback_reason})",
                      "ok" if ok else "ERRO" if c["fiel"] else "passou (limitação)"))

pii_msg = "Sou a Júlia, email julia@exemplo.com, CPF 123.456.789-09, telefone (11) 91234-5678. Qual rota eu pego?"
spy = Fixed({"resposta": "Prefira a primeira rota da lista.", "rotas_citadas": []})
ChatAssistant(retriever, spy).reply(Profile.GESTANTE, ask(pii_msg), facts_by_profile[Profile.GESTANTE])
pii_items = ["julia@exemplo.com", "123.456.789-09", "91234-5678"]
pii_leaked = [x for x in pii_items if x in spy.last_user]
down = ChatAssistant(retriever, Broken()).reply(Profile.GESTANTE, ask("O elevador da estação está quebrado, o que eu faço?"),
                                                facts_by_profile[Profile.GESTANTE])

w()
w("## 3. Assistente conversacional: validação e privacidade (offline)")
w()
w(f"{len(chat_cases['simulados'])} respostas simuladas do modelo passam pelo mesmo caminho do `POST /v1/chat` "
  "(`eval/chat_cases.json`): fiéis devem ser aceitas, infiéis devem cair na resposta de reserva.")
w()
w("| Tipo | Resposta simulada | Resultado | |")
w("|---|---|---|---|")
for row in chat_rows:
    w(f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} |")
w()
cprec = ctp / (ctp + cfp) if ctp + cfp else 0
crec = ctp / (ctp + cfn) if ctp + cfn else 0
w(f"Respostas fiéis aceitas: {ctn}/{ctn + cfp} · infiéis barradas: {ctp}/{ctp + cfn} "
  f"(precisão do bloqueio {cprec:.0%}, recall {crec:.0%}).")
w()
w("| Verificação | Resultado |")
w("|---|---|")
w(f"| Dados pessoais digitados no chat (e-mail, CPF, telefone) chegam ao prompt do modelo? | "
  f"{len(pii_items) - len(pii_leaked)}/{len(pii_items)} mascarados"
  f"{' — vazou: ' + ', '.join(pii_leaked) if pii_leaked else ''} |")
w(f"| Modelo fora do ar | resposta de reserva com trecho da base (`{down.fallback_reason}`, "
  f"trecho `{', '.join(down.kb_refs) or '-'}`) |")
w("| Conversa vazia, última mensagem do assistente, papel `system`, mensagem acima de 1000 caracteres | "
  "HTTP 422 (`tests/test_chat.py`) |")

# 4 - modelo de verdade (so com --live)
w()
w("## 4. IA generativa real")
w()
llm = build_llm(Settings(llm_timeout_s=20)) if "--live" in sys.argv else None
if llm is not None:
    w(f"Modelo: `{llm.name}` (Groq).")
    w()
    w("### 4.1 Explicação das rotas")
    w()
    ex = Explainer(retriever, llm)
    lat, sources, reasons, samples = [], [], [], []
    for p in Profile:
        for route in routes:
            f = score_route(route, p, catalog, store.active_for(route_place_ids(route), NOW)).facts
            t0 = time.perf_counter()
            e = ex.explain(p, f)
            lat.append(time.perf_counter() - t0)
            sources.append(e.source)
            if e.fallback_reason:
                reasons.append(e.fallback_reason)
            if len(samples) < 4 and e.source == "llm":
                samples.append((p.value, route.id, e))
    total = len(sources)
    acc = sources.count("llm")
    w(f"{total} combinações perfil × rota.")
    w()
    w("| Métrica | Valor |")
    w("|---|---|")
    w(f"| Respostas do LLM aceitas pelo validador | {acc}/{total} ({acc / total:.0%}) |")
    w(f"| Caíram no template | {total - acc} — motivos: {sorted(set(reasons)) or '-'} |")
    w(f"| Latência mediana / máxima | {statistics.median(lat):.1f} s / {max(lat):.1f} s |")
    w()
    w("Amostras (ler e julgar: clareza, tom, se a dica faz sentido para o perfil):")
    w()
    for p, rid, e in samples:
        w(f"- **{p} / {rid}** — {e.resumo} Pontos de atenção: {e.pontos_de_atencao}. Dica: {e.dica}")

    w()
    w("### 4.2 Assistente conversacional")
    w()
    chat = ChatAssistant(retriever, llm)
    clat, crows = [], []
    accepted = scope_ok = scope_n = route_ok = route_n = leaks = leak_n = 0
    for c in chat_cases["reais"]:
        p = Profile(c["perfil"])
        t0 = time.perf_counter()
        r = chat.reply(p, ask(c["pergunta"], c.get("historico", ())), facts_by_profile[p])
        clat.append(time.perf_counter() - t0)
        exp = c["espera"]
        accepted += r.source == "llm"
        checks = []
        if "fora_do_escopo" in exp:
            scope_n += 1
            good = r.out_of_scope == exp["fora_do_escopo"]
            scope_ok += good
            checks.append(f"fora do escopo {'ok' if good else 'ERRO'}")
        if exp.get("rota_citada"):
            route_n += 1
            good = exp["rota_citada"] in r.routes_cited
            route_ok += good
            checks.append(f"rota `{exp['rota_citada']}` {'ok' if good else 'não citada'}")
        if exp.get("nao_conter"):
            leak_n += 1
            plain = grounding._plain(r.reply)
            bad = [x for x in exp["nao_conter"] if grounding._plain(x) in plain]
            leaks += bool(bad)
            checks.append("ok" if not bad else f"CONTÉM: {bad}")
        status = r.source if r.source == "llm" else f"{r.source} ({r.fallback_reason})"
        crows.append((c["id"], c["pergunta"], r.reply.replace("|", "/").replace("\n", " "), status,
                      "; ".join(checks) or "-"))
    n_chat = len(chat_cases["reais"])
    w(f"{n_chat} perguntas (`eval/chat_cases.json`): sobre as rotas, com histórico, fora do tema, com dados "
      "pessoais e com tentativa de injeção de prompt.")
    w()
    w("| Métrica | Valor |")
    w("|---|---|")
    w(f"| Respostas do modelo aceitas pelo validador | {accepted}/{n_chat} ({accepted / n_chat:.0%}) |")
    w(f"| Citou a rota esperada | {route_ok}/{route_n} |")
    w(f"| Classificou corretamente o fora do escopo | {scope_ok}/{scope_n} |")
    w(f"| Repetiu dado pessoal ou cedeu à injeção | {leaks}/{leak_n} |")
    w(f"| Latência mediana / máxima | {statistics.median(clat):.1f} s / {max(clat):.1f} s |")
    w()
    w("| Caso | Pergunta | Resposta | Origem | Critério |")
    w("|---|---|---|---|---|")
    for row in crows:
        w(f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} | {row[4]} |")
else:
    w("**Não executado nesta geração do relatório** (sem `--live` ou sem `LLM_API_KEY`/`LLM_MODEL`). "
      "Rode `python eval/run_eval.py --live` com a chave do grupo para preencher esta seção com a taxa de "
      "aceitação, a latência e as respostas reais das explicações e do assistente conversacional.")

(EVAL / "RESULTADOS.md").write_text("\n".join(out) + "\n", encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")  # senao da erro de acento no terminal do windows
print("\n".join(out))
