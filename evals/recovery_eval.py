"""Offline retrieval ablation for version-specific synthetic recovery policies.

The reader extracts structured policies from retrieved text, never expected
answers. This measures retrieval availability and policy lookup, not LLM quality.
"""
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from copilot.retrieval import RUNBOOK_DIR, VectorIndex, load_chunks

HERE = Path(__file__).resolve().parent


def policies(chunks):
    for chunk in chunks:
        for raw in re.findall(r"```json\s*(.*?)\s*```", chunk.text, re.DOTALL):
            policy = json.loads(raw)
            yield policy, chunk.runbook


def read_policy(service, version, chunks):
    matches = [(p, source) for p, source in policies(chunks) if p["service"] == service and p["version"] == version]
    if len(matches) != 1:
        return {"status": "insufficient_evidence", "policy": None, "source": None}
    policy, source = matches[0]
    return {"status": "policy_found", "policy": policy, "source": source}


def run():
    cases = json.loads((HERE/"recovery_cases.json").read_text())
    chunks = load_chunks(RUNBOOK_DIR/"recovery")
    index = VectorIndex(chunks, "tfidf")
    runs = []
    for mode in ("no-retrieval", "tfidf"):
        records = []
        for case in cases:
            hits = index.search(case["q"], 3) if mode == "tfidf" else []
            answer = read_policy(case["service"], case["version"], [c for c, _ in hits])
            expected = case["expect"]
            correct = answer["policy"] == expected
            top = list(policies([hits[0][0]])) if hits else []
            records.append({"case_id": case["case_id"], "supported": expected is not None,
                            "correct": correct, "top1_exact_version": any(p == expected for p, _ in top) if expected else None,
                            "answer": answer, "retrieved": [{"runbook": c.runbook, "section": c.section, "score": s} for c,s in hits]})
        supported = [r for r in records if r["supported"]]
        unknown = [r for r in records if not r["supported"]]
        runs.append({"mode": mode, "summary": {"n": len(records),
            "supported_cases": len(supported), "exact_policy_correct": sum(r["correct"] for r in supported),
            "unknown_version_cases": len(unknown), "correct_abstentions": sum(r["correct"] for r in unknown),
            "top1_exact_version": sum(bool(r["top1_exact_version"]) for r in supported)}, "records": records})
    out = {"dataset_version": "recovery-v1", "corpus": "runbooks/recovery", "measured_at": datetime.now(timezone.utc).isoformat(),
           "reader": "structured policy extraction with exact service/version matching",
           "limitations": "Author-written synthetic fixtures; no model calls, no recovery execution, no dense-retrieval comparison.",
           "dataset_sha256": hashlib.sha256((HERE/"recovery_cases.json").read_bytes()).hexdigest(),
           "corpus_sha256": hashlib.sha256(''.join(c.text for c in chunks).encode()).hexdigest(), "runs": runs}
    path = HERE.parent/"results"/"recovery.json"
    path.write_text(json.dumps(out, indent=2)+'\n')
    return out


if __name__ == "__main__":
    result = run()
    for item in result["runs"]:
        print(item["mode"], item["summary"])
