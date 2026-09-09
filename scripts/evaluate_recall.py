"""Compare saved reports with a human-reviewed DOI benchmark; no model calls.

uv run python scripts/evaluate_recall.py benchmark.json report1.json report2.json
Benchmark format: {"expected_dois": ["10.1257/app.3.3.188", ...]}.
Cited-DOI recall is a retrieval proxy, not evidence of correct inclusion or claims.
"""
import argparse
import json
import re
from itertools import combinations
from pathlib import Path


def normalize(doi):
    return doi.lower().removeprefix("https://doi.org/").rstrip(".,;)")


def evaluate(expected, reports):
    expected = {normalize(doi) for doi in expected}
    if not expected:
        raise ValueError("Benchmark must contain at least one expected DOI")
    sets = {}
    results = []
    for name, text in reports.items():
        found = {normalize(doi) for doi in re.findall(r"10\.\d{4,9}/[^\s<>\]\\\"]+", text, re.I)}
        sets[name] = found
        results.append({"report": name, "cited_dois": sorted(found),
                        "benchmark_recall": len(expected & found) / len(expected),
                        "missing_dois": sorted(expected - found)})
    overlap = [{"reports": [a, b], "jaccard": len(sets[a] & sets[b]) / len(sets[a] | sets[b])
                if sets[a] | sets[b] else None} for a, b in combinations(sets, 2)]
    return {"metric_scope": "Cited DOI overlap only; manual screening and claim validation required",
            "runs": results, "overlap": overlap}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("benchmark", type=Path)
    parser.add_argument("reports", nargs="+", type=Path)
    args = parser.parse_args()
    benchmark = json.loads(args.benchmark.read_text())
    reports = {}
    for path in args.reports:
        data = json.loads(path.read_text())
        reports[str(path)] = data.get("result", "")
    print(json.dumps(evaluate(benchmark["expected_dois"], reports), indent=2))
