#!/usr/bin/env python3
"""내레이션 음성을 만든다. build_frames.py 보다 먼저 돌린다.

원고는 STORYBOARD.md 한 곳에만 있다. 여기서 문단 단위로 읽어 한 문단에 파일
하나씩 음성을 만들고, 앞뒤 무음을 걷어내고 음량을 맞춰 assets/narration/ 에 둔다.
build_frames.py 는 그 길이를 시계로 삼아 자막·요소·장면 길이를 정한다.

엔진은 둘이다.
  openai — OpenAI TTS (gpt-4o-mini-tts). 키는 저장소 루트 .env 의 OPENAI_API.
           원고가 외부 서비스로 나간다.
  qwen   — 로컬 Qwen3-TTS (/data/Source/Qwen3-TTS 의 tts_batch.py). 외부로 나가지 않는다.

음성 파일(assets/narration/, .narration-raw/)은 저장소에 넣지 않는다. 새로 받은
저장소에서는 이 스크립트를 먼저 돌려야 렌더에 소리가 난다. 돌리지 않고
build_frames.py 를 돌리면 음성 없는 판(자막만)으로 돌아간다.

원고를 고친 문단만 다시 만든다. 무엇이 바뀌었는지는 문단 원문의 해시로 안다 —
파일 이름(장면-문단번호)만으로는 원고가 바뀐 것을 알 수 없기 때문이다.

usage:
  python3 narrate.py --engine openai --voice marin [--force] [--only 02-why,03-map]
  python3 narrate.py --engine qwen --gpus 0,3 -- <tts_batch.py 에 넘길 인자...>
  (지금 쓰는 목소리를 다시 만드는 정확한 명령은 voice/README.md)
"""
import argparse
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).parent
REPO = ROOT.parents[2]
RAW = ROOT / ".narration-raw"          # TTS 원본. 저장소에 넣지 않는다.
OUT = ROOT / "assets" / "narration"    # 다듬은 최종본. 컴포지션이 읽는다.

QWEN_DIR = pathlib.Path(os.environ.get("QWEN3_TTS_DIR", "/data/Source/Qwen3-TTS"))

OPENAI_MODEL = "gpt-4o-mini-tts"
OPENAI_INSTRUCTIONS = (
    "Speak natural, fluent Korean as the narrator of a calm, honest product tutorial video. "
    "Warm and reassuring but never salesy or dramatic, never alarming. Moderate, even pace; "
    "clear articulation; natural short pauses at commas and sentence ends. "
    "Each input is one paragraph in the middle of a continuous narration: carry on "
    "smoothly as if continuing from the previous paragraph, do not sound like starting a new announcement.")

# 앞뒤 무음을 걷어낸다(문단 사이 쉼은 build_frames.py 가 정한다) → 말소리 기준 음량.
# 무음 제거는 파이썬에서 한다. ffmpeg 의 silenceremove+areverse 조합은 일부 파일에서
# abort 했다(ffmpeg_filter.c 의 assertion). 음량 맞추기만 ffmpeg 에 맡긴다.
TRIM_DB = -50.0      # 이보다 조용한 앞뒤는 무음으로 본다 (dBFS, 10ms 창의 최대값 기준)
TRIM_PAD = 0.05      # 말 앞뒤로 남겨두는 여유 (초)
LOUDNORM = "loudnorm=I=-16:TP=-1.5:LRA=11"
RATE = 48000


def text_sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def storyboard_lines() -> list[dict]:
    spec = importlib.util.spec_from_file_location("build_frames", ROOT / "build_frames.py")
    bf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bf)
    board = bf.read_storyboard()
    lines = []
    for name, *_ in bf.FRAMES:
        _, paras = board[name]
        for i, text in enumerate(paras):
            lines.append({"id": f"{name}-{i}", "text": text, "text_sha": text_sha(text)})
    return lines


def trim_silence(src: pathlib.Path, dst: pathlib.Path):
    """앞뒤 무음을 걷어내 dst 에 쓴다. 가운데 쉼은 건드리지 않는다."""
    import numpy as np
    import soundfile as sf
    audio, rate = sf.read(str(src), always_2d=True, dtype="float32")
    level = np.abs(audio).max(axis=1)
    win = max(1, int(rate * 0.01))
    frames = len(level) // win
    if frames == 0:
        sys.exit(f"{src.name}: 소리가 없다")
    peaks = level[:frames * win].reshape(frames, win).max(axis=1)
    loud = np.nonzero(peaks > 10 ** (TRIM_DB / 20))[0]
    if len(loud) == 0:
        sys.exit(f"{src.name}: 기준보다 큰 소리가 한 번도 없다 — TTS 가 빈 음성을 준 것 같다")
    pad = int(rate * TRIM_PAD)
    start = max(0, loud[0] * win - pad)
    end = min(len(audio), (loud[-1] + 1) * win + pad)
    sf.write(str(dst), audio[start:end], rate, subtype="PCM_16")


def probe_duration(path: pathlib.Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(path)],
                       check=True, capture_output=True, text=True)
    return float(r.stdout.strip())


def openai_key() -> str:
    if os.environ.get("OPENAI_API"):
        return os.environ["OPENAI_API"]
    env = REPO / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^\s*(?:export\s+)?OPENAI_API\s*=\s*(.*)$", line)
            if m:
                return m.group(1).strip().strip("'\"")
    sys.exit(f"OpenAI 키를 찾지 못했다: 환경변수 OPENAI_API 또는 {env} 의 OPENAI_API")


def clean_wav(data: bytes) -> bytes:
    """OpenAI 가 주는 wav 를 길이가 제대로 적힌 wav 로 다시 쓴다.

    스트리밍용이라 RIFF·data 길이 칸이 0xFFFFFFFF 로 비어 있어, ffmpeg 가 끝을
    '깨진 패킷'으로 읽고 길이를 어림한다. 헤더의 fmt 값은 그대로 믿고, 샘플 경계에
    맞춰 자른 뒤 wave 모듈로 다시 쓴다.
    """
    import io
    import struct
    import wave
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("wav 가 아니다")
    pos, fmt, pcm = 12, None, None
    while pos + 8 <= len(data):
        cid, size = data[pos:pos + 4], struct.unpack("<I", data[pos + 4:pos + 8])[0]
        body = pos + 8
        if cid == b"fmt ":
            fmt = struct.unpack("<HHIIHH", data[body:body + 16])
            pos = body + size + (size & 1)
        elif cid == b"data":
            end = len(data) if size == 0xFFFFFFFF else min(len(data), body + size)
            pcm = data[body:end]
            break
        else:
            pos = body + size + (size & 1)
    if fmt is None or pcm is None:
        raise ValueError("wav 에 fmt/data 가 없다")
    tag, channels, rate, _, align, bits = fmt
    if tag != 1:
        raise ValueError(f"PCM 이 아니다 (format tag {tag})")
    pcm = pcm[:len(pcm) - len(pcm) % align]
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(bits // 8)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def run_openai(todo: list[dict], voice: str, workers: int = 6):
    from openai import OpenAI
    client = OpenAI(api_key=openai_key())

    def one(l):
        dst = RAW / f"{l['id']}.wav"
        for attempt in range(5):
            try:
                r = client.audio.speech.create(model=OPENAI_MODEL, voice=voice, input=l["text"],
                                               instructions=OPENAI_INSTRUCTIONS,
                                               response_format="wav")
                tmp = dst.with_suffix(".part")
                tmp.write_bytes(clean_wav(r.content))
                tmp.rename(dst)
                return l["id"], None
            except Exception as e:   # 속도 제한·일시 오류는 물러났다가 다시
                err = e
                time.sleep(2 ** attempt)
        return l["id"], err

    failed = []
    with ThreadPoolExecutor(workers) as ex:
        for n, (lid, err) in enumerate(ex.map(one, todo), 1):
            print(f"  [{n}/{len(todo)}] {lid}" + (f"  실패: {err}" if err else ""))
            if err:
                failed.append(lid)
    if failed:
        sys.exit(f"음성을 만들지 못한 문단: {', '.join(failed)}")


def run_qwen(todo: list[dict], tts_args: list[str], gpus: list[str]):
    """문단을 GPU 수만큼 나눠 동시에 만든다.

    이번에 만들 문단 목록의 순서대로 번갈아 나눈다(i % GPU 수). tts_batch.py 는 문단마다
    시드를 다시 거므로 결과가 함께 만든 문단에 따라 달라지지 않는다. 다만 같은 시드라도
    물리 카드가 다르면 바이트까지 같지는 않다 — 한 문단이 어느 카드에 가는지는 이번
    목록에 달렸으므로, --only 로 일부만 다시 만들면 그 문단이 예전과 다른 카드에서 만들어질 수 있다.
    """
    py, batch = QWEN_DIR / ".venv" / "bin" / "python", QWEN_DIR / "tts_batch.py"
    for p in (py, batch):
        if not p.exists():
            sys.exit(f"Qwen3-TTS 를 찾지 못했다: {p}  (QWEN3_TTS_DIR 로 위치를 알려줄 수 있다)")
    procs = []
    for k, gpu in enumerate(gpus):
        part = [l for i, l in enumerate(todo) if i % len(gpus) == k]
        if not part:
            continue
        shard = RAW / f"qwen-gpu{gpu}"
        shard.mkdir(exist_ok=True)
        req = shard / "lines.json"
        req.write_text(json.dumps([{"id": l["id"], "text": l["text"]} for l in part],
                                  ensure_ascii=False, indent=2), encoding="utf-8")
        # GPU 번호는 nvidia-smi 번호다. PCI_BUS_ID 가 없으면 CUDA 가 다른 순서로 센다.
        env = dict(os.environ, CUDA_DEVICE_ORDER="PCI_BUS_ID", CUDA_VISIBLE_DEVICES=gpu)
        log = open(shard / "tts_batch.log", "w", encoding="utf-8")
        procs.append((gpu, part, shard, log, subprocess.Popen(
            [str(py), str(batch), "--in", str(req), "--out-dir", str(shard), "--force", *tts_args],
            env=env, stdout=log, stderr=subprocess.STDOUT)))
        print(f"  GPU {gpu}: 문단 {len(part)}개")
    failed = []
    for gpu, part, shard, log, proc in procs:
        code = proc.wait()
        log.close()
        if code != 0:
            failed.append(f"GPU {gpu} (종료 코드 {code}, 로그 {shard / 'tts_batch.log'})")
            continue
        for l in part:
            (shard / f"{l['id']}.wav").replace(RAW / f"{l['id']}.wav")
    if failed:
        sys.exit("Qwen3-TTS 가 실패했다: " + ", ".join(failed))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", choices=["openai", "qwen"], required=True)
    ap.add_argument("--voice", help="openai 목소리 (예: marin)")
    ap.add_argument("--gpus", default="0", help="qwen: 나눠 쓸 GPU 번호(nvidia-smi 기준), 쉼표로")
    ap.add_argument("--force", action="store_true", help="바뀌지 않은 문단도 다시 만든다")
    ap.add_argument("--only", default="",
                    help="장면 이름이나 문단 id 를 쉼표로 (예: 02-why,18-arch-path-4)")
    ap.add_argument("tts_args", nargs=argparse.REMAINDER,
                    help="qwen: -- 뒤의 인자는 tts_batch.py 에 그대로 넘긴다")
    args = ap.parse_args()
    tts_args = [a for a in args.tts_args if a != "--"]
    if args.engine == "openai":
        if not args.voice:
            sys.exit("--engine openai 에는 --voice 가 필요하다")
        settings = {"engine": "openai", "model": OPENAI_MODEL, "voice": args.voice,
                    "instructions": OPENAI_INSTRUCTIONS}
    else:
        settings = {"engine": "qwen", "tts_args": tts_args}

    lines = storyboard_lines()
    scenes = {l["id"].rsplit("-", 1)[0] for l in lines}
    ids = {l["id"] for l in lines}
    only = {s for s in args.only.split(",") if s}
    if only - scenes - ids:
        sys.exit(f"없는 장면·문단: {', '.join(sorted(only - scenes - ids))}")

    RAW.mkdir(exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT / "manifest.json"
    old = {}
    if manifest_path.exists():
        prev = json.loads(manifest_path.read_text(encoding="utf-8"))
        old = {x["id"]: x for x in prev["lines"]}
        # 목소리 설정이 바뀌면 예전 음성과 섞이면 안 된다.
        if prev.get("settings") != settings and not args.force:
            sys.exit("목소리 설정이 지난번과 다르다. 전체를 다시 만들려면 --force 를 붙여라.\n"
                     f"  지난번: {prev.get('settings')}\n  이번:   {settings}")

    def wanted(l):
        if only and l["id"] not in only and l["id"].rsplit("-", 1)[0] not in only:
            return False
        prev = old.get(l["id"])
        return (args.force or prev is None or prev["text_sha"] != l["text_sha"]
                or not (OUT / prev["file"]).exists())

    todo = [l for l in lines if wanted(l)]
    print(f"문단 {len(lines)}개 중 {len(todo)}개를 만든다 ({settings['engine']})")

    if todo:
        for l in todo:   # 엔진이 있는 파일을 건너뛸 수 있으므로, 다시 만들 것은 먼저 지운다
            (RAW / f"{l['id']}.wav").unlink(missing_ok=True)
        if args.engine == "openai":
            run_openai(todo, args.voice)
        else:
            run_qwen(todo, tts_args, [g for g in args.gpus.split(",") if g])
        for l in todo:
            src = RAW / f"{l['id']}.wav"
            if not src.exists():
                sys.exit(f"TTS 가 {src.name} 을 만들지 않았다")
            trimmed = RAW / f"{l['id']}.trim.wav"
            trim_silence(src, trimmed)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(trimmed),
                            "-af", LOUDNORM, "-ar", str(RATE), "-ac", "1",
                            str(OUT / f"{l['id']}.wav")], check=True)
            trimmed.unlink()

    done = {l["id"] for l in todo}
    entries = []
    for l in lines:
        dst = OUT / f"{l['id']}.wav"
        if l["id"] in done:
            entries.append({"id": l["id"], "file": dst.name, "text_sha": l["text_sha"],
                            "duration_s": round(probe_duration(dst), 3), "text": l["text"]})
        elif l["id"] in old:
            entries.append(old[l["id"]])
    manifest_path.write_text(json.dumps({"settings": settings, "trim": {"db": TRIM_DB, "pad_s": TRIM_PAD}, "loudnorm": LOUDNORM,
                                         "sample_rate": RATE, "lines": entries},
                                        ensure_ascii=False, indent=2), encoding="utf-8")
    total = sum(e["duration_s"] for e in entries)
    print(f"manifest.json — 문단 {len(entries)}/{len(lines)} · 음성 합계 {total/60:.1f}분")


if __name__ == "__main__":
    main()
