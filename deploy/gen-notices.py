#!/usr/bin/env python3
"""
THIRD_PARTY_NOTICES.md 생성: 릴리스 압축본이 재배포하는 프론트엔드 번들의 의존성(런타임 트리)과
백엔드 파이썬 의존성의 라이선스와 저작권 고지를 모은다. MIT/ISC/BSD 는 재배포 시 고지 포함이 의무다.
  deploy/gen-notices.py            # 저장소 루트에 THIRD_PARTY_NOTICES.md 를 쓴다
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONT = ROOT / "frontend"
OUT = ROOT / "THIRD_PARTY_NOTICES.md"


def js_runtime_tree() -> dict[str, dict]:
    pkg = json.loads((FRONT / "package.json").read_text())
    seen: dict[str, dict] = {}

    def walk(name: str):
        if name in seen:
            return
        d = FRONT / "node_modules" / name
        try:
            meta = json.loads((d / "package.json").read_text())
        except OSError:
            return
        lic_text = ""
        for cand in ("LICENSE", "LICENSE.md", "LICENSE.txt", "LICENCE", "LICENCE.md", "license", "License.md", "LICENSE-MIT", "LICENSE-MIT.txt"):
            p = d / cand
            if p.is_file():
                lic_text = p.read_text(encoding="utf-8", errors="replace").strip()
                break
        lic = meta.get("license")
        if isinstance(lic, dict):
            lic = lic.get("type")
        seen[name] = {"version": meta.get("version", "?"), "license": lic or "?", "author": (meta.get("author") if isinstance(meta.get("author"), str) else (meta.get("author") or {}).get("name", "")), "text": lic_text, "url": meta.get("homepage") or ""}
        for dep in (meta.get("dependencies") or {}):
            walk(dep)

    for dep in pkg.get("dependencies", {}):
        walk(dep)
    return dict(sorted(seen.items()))


def py_deps() -> dict[str, dict]:
    sys.path.insert(0, str(ROOT / "backend"))
    from importlib import metadata
    req = (ROOT / "backend" / "requirements.txt").read_text().splitlines()
    names = [r.split(">=")[0].split("==")[0].split("<")[0].strip() for r in req if r.strip() and not r.startswith("#")]
    out: dict[str, dict] = {}
    for n in names:
        try:
            d = metadata.distribution(n)
        except metadata.PackageNotFoundError:
            out[n] = {"version": "?", "license": "(not installed in venv)", "text": ""}
            continue
        expr = d.metadata.get("License-Expression") or ""
        cls = [c.split("::")[-1].strip() for c in d.metadata.get_all("Classifier", []) if c.startswith("License ::")]
        lic = expr or (cls[0] if cls else (d.metadata.get("License") or "?").splitlines()[0])
        text = ""
        for f in (d.files or []):
            if f.name.upper().startswith(("LICENSE", "LICENCE", "COPYING")) and "licenses" in str(f) or f.name.upper() in ("LICENSE", "LICENSE.TXT", "LICENSE.MD"):
                try:
                    text = f.read_text().strip()
                    break
                except Exception:
                    pass
        out[n] = {"version": d.version, "license": lic, "text": text}
    return out


def main():
    js = js_runtime_tree()
    py = py_deps()
    lines = ["# Third-party notices", "",
             "Sentinel Overwatch 는 Apache License 2.0 으로 배포된다. 아래는 릴리스에 포함되거나 설치 시 내려받는 제3자 구성요소와 그 라이선스다.",
             "호스트 도구(fail2ban, auditd, Lynis, dpkg/apt 등)는 별도 프로세스로 호출할 뿐 이 소프트웨어에 포함되지 않는다.", "",
             "## Frontend (번들되어 재배포됨)", "", "| package | version | license |", "|---|---|---|"]
    for n, m in js.items():
        lines.append(f"| {n} | {m['version']} | {m['license']} |")
    lines += ["", "## Backend (pip 로 설치, --wheels 릴리스에는 휠 포함)", "", "| package | version | license |", "|---|---|---|"]
    for n, m in py.items():
        lines.append(f"| {n} | {m['version']} | {m['license']} |")
    lines += ["", "## Fonts", "", "docs/ 의 문서는 Google Fonts 에서 IBM Plex Sans KR / IBM Plex Mono (SIL Open Font License 1.1) 를 불러온다. 폰트 파일은 재배포하지 않는다.", "",
              "## License texts (frontend bundle)", ""]
    for n, m in js.items():
        if m["text"]:
            lines += [f"### {n} {m['version']} ({m['license']})", "", "```", m["text"], "```", ""]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    missing = [n for n, m in js.items() if not m["text"]]
    print(f"wrote {OUT} ({len(js)} js packages, {len(py)} python packages)")
    if missing:
        print("license text not found for:", ", ".join(missing))


if __name__ == "__main__":
    main()
