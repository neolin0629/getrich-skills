"""Print one complete anonymous benchmark input, with an auditable end marker."""
import argparse
import hashlib
import json
from pathlib import Path


def emit_question(packet: Path, index: int) -> str:
    questions = json.loads(packet.read_text(encoding="utf-8"))["questions"]
    if index < 0 or index >= len(questions):
        raise ValueError("question index out of range")
    q = questions[index]
    evidence = q["evidence"]
    digest = hashlib.sha256(evidence.encode("utf-8")).hexdigest()
    metadata = {key: q[key] for key in ("id", "trial", "question", "retrieved_at") if key in q}
    receipt = f"END_INPUT id={q['id']} chars={len(evidence)} sha256={digest}"
    return json.dumps(metadata, ensure_ascii=False) + "\n\n" + evidence + "\n\n" + receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path)
    parser.add_argument("index", type=int, help="zero-based question index")
    args = parser.parse_args()
    print(emit_question(args.packet, args.index))


if __name__ == "__main__":
    main()
