"""RAG básico: recuperação sobre a base de conhecimento de acessibilidade.

Escolha técnica: TF-IDF de n-gramas de caracteres + similaridade de cosseno (scikit-learn).
- A base é pequena e curada (dezenas de trechos): um índice vetorial externo seria custo sem ganho.
- N-gramas de caracteres toleram flexões e erros de digitação em português ("elevador/elevadores").
- É determinístico e roda offline => avaliação reprodutível (hit@k / MRR em eval/).
A interface `Retriever.search` isola a escolha: trocar por embeddings + Azure AI Search/pgvector
não muda o resto do serviço.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .models import Profile

PROFILE_BOOST = 0.08


@dataclass(frozen=True)
class Chunk:
    id: str
    titulo: str
    texto: str
    perfis: tuple[str, ...]
    fonte: str
    palavras_chave: str = ""


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float


class Retriever:
    def __init__(self, chunks: list[Chunk], min_score: float = 0.15):
        if not chunks:
            raise ValueError("Base de conhecimento vazia")
        self.chunks = chunks
        self.min_score = min_score
        self._vec = TfidfVectorizer(
            analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, strip_accents="unicode", lowercase=True
        )
        corpus = [f"{c.titulo}. {c.palavras_chave}. {c.texto}" for c in chunks]
        self._matrix = self._vec.fit_transform(corpus)

    @classmethod
    def from_file(cls, path: Path, min_score: float = 0.15) -> "Retriever":
        raw = json.loads(path.read_text(encoding="utf-8"))
        chunks = [
            Chunk(
                id=c["id"],
                titulo=c["titulo"],
                texto=c["texto"],
                perfis=tuple(c.get("perfis", ["todos"])),
                fonte=c.get("fonte", ""),
                palavras_chave=c.get("palavras_chave", ""),
            )
            for c in raw["trechos"]
        ]
        return cls(chunks, min_score=min_score)

    def search(self, query: str, profile: Profile | None = None, k: int = 2) -> list[Hit]:
        """Retorna até k trechos acima do limiar. Lista vazia = 'não sei' (melhor que dica irrelevante)."""
        if not query.strip():
            return []
        sims = cosine_similarity(self._vec.transform([query]), self._matrix)[0]
        hits = []
        for chunk, sim in zip(self.chunks, sims):
            if sim < self.min_score:
                continue  # o boost de perfil só reordena; não "salva" trecho irrelevante
            boost = PROFILE_BOOST if profile and profile.value in chunk.perfis else 0.0
            hits.append(Hit(chunk=chunk, score=float(sim) + boost))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:k]


ISSUE_QUERY = {
    "bloqueio": "rota sem opção acessível, alternativa de transporte porta a porta",
    "escadas": "escadas sem elevador, evitar degraus",
    "elevador_incerto": "elevador quebrado fora de operação na estação, o que fazer",
    "escada_rolante": "escada rolante parada",
    "caminhada_longa": "caminhada longa, pausas e descanso",
    "ladeira": "ladeira, rampa e inclinação do trajeto",
    "calcada_ruim": "calçada com buracos e obstáculos, risco de queda",
    "sem_cobertura": "ponto de ônibus sem cobertura, espera no sol e chuva",
    "sem_assento": "espera em pé, assento preferencial",
    "baldeacao": "baldeação e troca de linha",
    "sem_dados": "sem informação de acessibilidade, confirmar nos canais oficiais",
}


def build_query(profile_label: str, codes: list[str]) -> str:
    parts = [ISSUE_QUERY[c] for c in codes if c in ISSUE_QUERY]
    if not parts:
        parts = ["direitos e prioridade no transporte público"]
    return f"{profile_label}: " + "; ".join(parts)
