#!/usr/bin/env python3
"""만든 내레이션 음성이 원고를 그대로 읽었는지 받아쓰기로 대조한다.

TTS 는 가끔 문장을 통째로 빼먹거나 비슷한 말로 바꿔 읽는다(샘플에서 실제로 봤다).
자막은 원고 그대로라, 그러면 소리와 자막이 다른 말을 한다. 그래서 만든 뒤 한 번 듣는다.

받아쓰기도 틀릴 수 있으므로 기준 아래인 문단은 '다시 들어볼 것'이지 곧 '틀림'은 아니다.

판정은 한글만 본다. 원고의 영어 이름(Slack, root, fail2ban)은 받아쓰기가 '슬랙', '루트'
처럼 한글로 적기도 해서, 그대로 비교하면 멀쩡한 문단이 무더기로 걸린다. 그래서
  · 원고 한글이 받아쓴 글에 얼마나 남아 있는가 (coverage)
  · 원고 문장마다 따로 봤을 때 가장 많이 사라진 문장은 얼마나 남았나 (worst sentence)
둘 중 하나라도 기준 아래면 걸린다. 문장 하나를 통째로 빼먹는 실수는 뒤쪽이 잡는다.
정말 틀렸으면 narrate.py --only <장면> --force 로 그 장면만 다시 만든다.

usage:
  python3 verify_narration.py [--engine openai|whisper] [--coverage 0.93] [--sentence 0.75] [--device cuda|cpu]

openai 는 gpt-4o-transcribe 로 받아쓴다(빠르다. 음성이 외부로 나간다 — 원고와 같은 내용이다).
whisper 는 로컬 faster-whisper large-v3 (느리다. 이 PC 에는 cuDNN 8 이 없어 CPU 로만 돈다).
"""
import argparse
import difflib
import json
import pathlib
import re
import sys
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).parent
NARRATION = ROOT / "assets" / "narration"


def hangul(s: str) -> str:
    return re.sub(r"[^가-힣]", "", s)


def kept(part: str, heard: str) -> float:
    """part 의 글자가 heard 에 순서대로 얼마나 남아 있나 (0~1)."""
    if not part:
        return 1.0
    sm = difflib.SequenceMatcher(None, part, heard, autojunk=False)
    return sum(b.size for b in sm.get_matching_blocks()) / len(part)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", choices=["openai", "whisper"], default="openai")
    ap.add_argument("--coverage", type=float, default=0.93)
    ap.add_argument("--sentence", type=float, default=0.75)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--model", default="large-v3")
    args = ap.parse_args()

    manifest = json.loads((NARRATION / "manifest.json").read_text(encoding="utf-8"))
    if args.engine == "openai":
        import importlib.util
        spec = importlib.util.spec_from_file_location("narrate", ROOT / "narrate.py")
        narrate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(narrate)
        from openai import OpenAI
        client = OpenAI(api_key=narrate.openai_key())

        def hear(path):
            with open(path, "rb") as f:
                return client.audio.transcriptions.create(
                    model="gpt-4o-transcribe", file=f, language="ko").text.strip()
    else:
        from faster_whisper import WhisperModel
        compute = "float16" if args.device == "cuda" else "int8"
        model = WhisperModel(args.model, device=args.device, compute_type=compute)

        def hear(path):
            segs, _ = model.transcribe(str(path), language="ko", beam_size=5, vad_filter=False)
            return "".join(s.text for s in segs).strip()

    lines = manifest["lines"]
    with ThreadPoolExecutor(6 if args.engine == "openai" else 1) as ex:
        heards = list(ex.map(lambda x: hear(NARRATION / x["file"]), lines))

    report, flagged = [], []
    for x, heard in zip(lines, heards):
        h = hangul(heard)
        coverage = kept(hangul(x["text"]), h)
        sents = [t for t in re.split(r"(?<=[.?!])\s+", x["text"]) if hangul(t)]
        worst_score, worst = min((kept(hangul(t), h), t) for t in sents)
        ok = coverage >= args.coverage and worst_score >= args.sentence
        report.append({"id": x["id"], "coverage": round(coverage, 3),
                       "worst_sentence": round(worst_score, 3), "ok": ok,
                       "text": x["text"], "heard": heard, "weakest": worst})
        print(f"  {'ok   ' if ok else 'CHECK'} {coverage:.3f} {worst_score:.2f}  {x['id']}")
        if not ok:
            flagged.append(report[-1])

    (NARRATION / "verify.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                           encoding="utf-8")
    print(f"\n문단 {len(report)}개 중 다시 들어볼 것 {len(flagged)}개 "
          f"(coverage ≥ {args.coverage}, 문장 ≥ {args.sentence})")
    for f in flagged:
        print(f"\n  {f['id']}  (coverage {f['coverage']}, 가장 약한 문장 {f['worst_sentence']})"
              f"\n    약한 문장: {f['weakest']}\n    원고: {f['text']}\n    들림: {f['heard']}")
    sys.exit(1 if flagged else 0)


if __name__ == "__main__":
    main()
