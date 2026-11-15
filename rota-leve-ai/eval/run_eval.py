"""Avaliação reprodutível da funcionalidade de IA. Gera eval/RESULTADOS.md.

Uso:
    python eval/run_eval.py            # offline (determinístico, sem chave)
    python eval/run_eval.py --live     # também chama o LLM real (precisa de LLM_API_KEY e LLM_MODEL)
"""
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

from app import grounding  # noqa: E402
from app.catalog import Catalog  # noqa: E402
from app.explain import Explainer  # noqa: E402
from app.config import Settings  # noqa: E402
from app.llm import LLMError, build_llm  # noqa: E402
from app.models import Profile, Route  # noqa: E402
from app.rag import ISSUE_QUERY, Retriever, build_query  # noqa: E402
from app.reports import ReportStore  # noqa: E402
from app.scoring import RULES, route_place_ids, score_route  # noqa: E402
from app.service import RouteRanker  # noqa: E402

logging.disable(logging.WARNING)  # os fallbacks simulados não precisam poluir a saída
DATA, EVAL = ROOT / "data", ROOT / "eval"
NOW = datetime.now(timezone.utc)
out: list[str] = []


def w(line: str = "") -> None:
    out.append(line)


catalog = Catalog.from_file(DATA / "pontos.json")
store = ReportStore.from_seed(DATA / "relatos.json", now=NOW)
retriever = Retriever.from_file(DATA / "base_conhecimento.json")
routes = [Route(**r) for r in json.loads((DATA / "rotas_demo.json").read_text(encoding="utf-8"))["rotas"]]

w("# Resultados da avaliação")
w()
w(f"Gerado por `python eval/run_eval.py` em {NOW:%d/%m/%Y %H:%M} UTC. "
  "As seções 1 a 5 são determinísticas e rodam sem chave de API.")

# ---------------------------------------------------------------- 1. Recuperação (RAG)
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

# ---------------------------------------------------------------- 2. Consultas internas
EXPECTED = {
    "bloqueio": "kb-sem-rota-acessivel", "escadas": "kb-escadas-gestante", "elevador_incerto": "kb-elevador-fora",
    "caminhada_longa": "kb-caminhada-longa", "ladeira": "kb-ladeira-rampa", "calcada_ruim": "kb-calcada-ruim",
    "sem_cobertura": "kb-ponto-sem-cobertura", "sem_assento": "kb-prioridade-lei", "baldeacao": "kb-baldeacao",
    "sem_dados": "kb-sem-dados",
}
PROFILE_FOR = {"escadas": Profile.GESTANTE, "bloqueio": Profile.CADEIRANTE}
ok2 = 0
rows = []
for code, expected in EXPECTED.items():
    profile = PROFILE_FOR.get(code, Profile.IDOSO)
    ids = [h.chunk.id for h in retriever.search(build_query(RULES[profile].label, [code]), profile, k=2)]
    good = expected in ids
    ok2 += good
    rows.append((code, expected, ", ".join(ids) or "(vazio)", "ok" if good else "FALHOU"))
w()
w("## 2. Consultas que o próprio sistema gera")
w()
w("Na aplicação, a consulta ao RAG é montada a partir dos códigos de problema do score (não é texto livre do "
  "usuário). Para cada código, o trecho esperado precisa estar entre os 2 recuperados.")
w()
w(f"**Resultado: {ok2}/{len(EXPECTED)}**" + (f" (códigos sem consulta dedicada: {sorted(set(ISSUE_QUERY) - set(EXPECTED))})"
                                                if set(ISSUE_QUERY) - set(EXPECTED) else ""))
w()
w("| Código do problema | Esperado | Recuperados (top 2) | |")
w("|---|---|---|---|")
for r in rows:
    w(f"| `{r[0]}` | `{r[1]}` | {r[2]} | {r[3]} |")

# ---------------------------------------------------------------- 3. Reordenação
ranker = RouteRanker(catalog, store, Explainer(retriever, llm=None))
baseline = [r.id for r in sorted(routes, key=lambda r: r.duration_min)]
w()
w("## 3. Reordenação por perfil (cenário de demonstração)")
w()
w(f"Linha de base (app comum, mais rápida primeiro): `{' > '.join(baseline)}`")
w()
w("| Perfil | Ordem do Rota Leve (nota) | 1ª da linha de base para este perfil |")
w("|---|---|---|")
baseline_bad = 0
for p in Profile:
    resp = ranker.rank(p, routes, now=NOW, explain=False)
    by = {r.route_id: r for r in resp.routes}
    order = " > ".join(f"{r.route_id} ({r.score}{', bloqueada' if r.blocking else ''})" for r in resp.routes)
    b = by[baseline[0]]
    baseline_bad += b.label != "recomendada"
    w(f"| {p.value} | {order} | {b.label}{' (bloqueada)' if b.blocking else ''}, nota {b.score} |")
w()
w(f"Em {baseline_bad} de {len(Profile)} perfis a rota que o app comum mostraria primeiro **não** é recomendada "
  "pelo critério de acessibilidade. Os critérios esperados (rota bloqueada no fim, relato expirado ignorado, "
  "relato não confirmado não bloqueia etc.) são verificados automaticamente em `tests/test_scoring.py`.")

# ---------------------------------------------------------------- 4. Validador de fidelidade
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
w("## 4. Validador de fidelidade (groundedness)")
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

# ---------------------------------------------------------------- 5. Falhas


class Broken:
    name = "broken"

    def generate_json(self, system, user):
        raise LLMError("timeout simulado")


class Garbage:
    name = "garbage"

    def generate_json(self, system, user):
        return {"qualquer": "coisa"}


w()
w("## 5. Situações de falha")
w()
w("| Situação | Comportamento observado |")
w("|---|---|")
for label, llm in (("LLM fora do ar (timeout)", Broken()), ("LLM devolve JSON fora do formato", Garbage())):
    rk = RouteRanker(catalog, store, Explainer(retriever, llm=llm))
    total = with_exp = 0
    reasons = set()
    for p in Profile:
        for r in rk.rank(p, routes, now=NOW, max_explained=len(routes)).routes:
            total += 1
            with_exp += bool(r.explanation and r.explanation.resumo)
            reasons.add(r.explanation.fallback_reason)
    w(f"| {label} | {with_exp}/{total} rotas continuam com explicação (template), motivo registrado: {sorted(reasons)} |")
only_blocked = [r for r in routes if r.id == "r1-metro-se"]
resp = ranker.rank(Profile.CADEIRANTE, only_blocked, now=NOW)
w(f"| Nenhuma rota acessível para o perfil | rota marcada `{resp.routes[0].label}`, resumo: \"{resp.routes[0].explanation.resumo}\" "
  f"· trechos usados: {resp.routes[0].explanation.kb_refs} |")
w("| Perfil vazio, perfil inexistente, lista de rotas vazia, rota sem trechos | HTTP 422 (`tests/test_api.py`) |")
w("| Relato expirado | ignorado no score (`tests/test_scoring.py`) |")
w("| Parada sem correspondência no catálogo | penalidade `sem_dados` + aviso, sem inventar atributos |")

# ---------------------------------------------------------------- 6. LLM real (opcional)
w()
w("## 6. IA generativa real")
w()
_live_settings = Settings(llm_timeout_s=20, llm_max_retries=1)
llm = build_llm(_live_settings) if "--live" in sys.argv else None
if llm is not None:
    model = f"{_live_settings.llm_provider}/{llm.name}"
    ex = Explainer(retriever, llm, cache_size=0)
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
    w(f"Modelo: `{model}` · {total} combinações perfil × rota.")
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
else:
    w("**Não executado nesta geração do relatório** (sem `--live` ou sem `LLM_API_KEY`/`LLM_MODEL`). "
      "Rode `python eval/run_eval.py --live` com a chave do grupo para preencher esta seção com a taxa de "
      "aceitação, a latência e amostras das respostas reais.")

(EVAL / "RESULTADOS.md").write_text("\n".join(out) + "\n", encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")  # console do Windows usa cp1252 por padrão
print("\n".join(out))
