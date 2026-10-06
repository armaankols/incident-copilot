"""Retrieval eval: does the vector index return the right runbook? (recall@1 / recall@3)
Small hand-written query set -- extend it with real incident phrasings for stronger numbers."""
import json
from pathlib import Path

from copilot.retrieval import EMBEDDERS, VectorIndex, load_chunks

HERE = Path(__file__).resolve().parent


def run(embedder: str) -> dict:
    queries = json.loads((HERE / "retrieval_queries.json").read_text())
    index = VectorIndex(load_chunks(), embedder)
    r1 = r3 = 0
    for item in queries:
        seen = []
        for chunk, _ in index.search(item["q"], 12):
            if chunk.runbook not in seen:
                seen.append(chunk.runbook)
        r1 += item["expect"] in seen[:1]
        r3 += item["expect"] in seen[:3]
    n = len(queries)
    return {"embedder": embedder, "n_queries": n, "recall@1": round(100 * r1 / n, 1), "recall@3": round(100 * r3 / n, 1)}


if __name__ == "__main__":
    out = [run("tfidf")]
    for name in EMBEDDERS:
        if name == "tfidf":
            continue
        try:
            out.append(run(name))
        except Exception as e:  # noqa: BLE001  (fastembed is optional)
            print(f"skipping {name}: {type(e).__name__}")
    for o in out:
        print(o)
    (HERE.parent / "results" / "retrieval.json").write_text(json.dumps(out, indent=2))
