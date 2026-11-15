"""Demo de linha de comando: cenário da Júlia (gestante) e comparação com outros perfis.

Uso:  python scripts/demo.py [perfil]      (perfil padrão: gestante)
Com GEMINI_API_KEY definida, as explicações vêm do LLM; sem ela, do template.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import get_ranker  # noqa: E402
from app.models import Profile, Route  # noqa: E402

profile = Profile(sys.argv[1]) if len(sys.argv) > 1 else Profile.GESTANTE
ranker = get_ranker()
raw = json.loads((Path(__file__).resolve().parent.parent / "data" / "rotas_demo.json").read_text(encoding="utf-8"))
routes = [Route(**r) for r in raw["rotas"]]

print(f"\nOrdem do app comum (mais rápida primeiro): {[r.id for r in sorted(routes, key=lambda r: r.duration_min)]}")
resp = ranker.rank(profile, routes)
print(f"Ordem do Rota Leve para o perfil '{profile.value}':\n")
for i, r in enumerate(resp.routes, 1):
    print(f"{i}. [{r.score:>3}] {r.summary} — {r.duration_min} min, {r.walk_m} m a pé — {r.label}")
    for b in r.breakdown:
        print(f"      {b.points:+d}  {b.detail}")
    if r.explanation:
        e = r.explanation
        print(f"      >> ({e.source}) {e.resumo}")
        if e.dica:
            print(f"      >> dica: {e.dica}")
    print()
