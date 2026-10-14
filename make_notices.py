"""exe에 실제로 들어간 라이브러리의 라이선스 문구를 모아 THIRD_PARTY_LICENSES.md를 만든다.

사용: python make_notices.py [dist\\PDFEditor\\_internal] [출력파일]
"""
from __future__ import annotations

import sys
from importlib import metadata
from pathlib import Path

internal = Path(sys.argv[1] if len(sys.argv) > 1 else r"dist\PDFEditor\_internal")
out_path = Path(sys.argv[2] if len(sys.argv) > 2 else "THIRD_PARTY_LICENSES.md")

# 번들된 최상위 모듈 이름 → 배포 패키지
bundled_tops = {p.name.split(".")[0] for p in internal.iterdir()}
tops_to_dists = metadata.packages_distributions()
dist_names: set[str] = set()
for top in bundled_tops:
    for d in tops_to_dists.get(top, []):
        dist_names.add(d)
# 빌드 도구는 결과물에 포함되지 않으므로 제외
dist_names -= {"pyinstaller", "pyinstaller-hooks-contrib", "altgraph", "pefile", "pip", "setuptools"}
# PySide6 계열은 최상위 이름(PySide6)을 공유하므로, 실제 DLL이 들어간 것만 남긴다
_qt_dir = internal / "PySide6"
for _name, _marker in (("PySide6_WebEngine", "Qt6WebEngine"), ("PySide6_Pdf", "Qt6Pdf")):
    if not any(_qt_dir.glob(f"{_marker}*")):
        dist_names.discard(_name)


def license_files(dist: metadata.Distribution) -> list[tuple[str, str]]:
    found = []
    for f in dist.files or []:
        name = f.name.upper()
        if any(k in name for k in ("LICENSE", "LICENCE", "COPYING", "NOTICE")) and f.suffix.lower() in ("", ".txt", ".md", ".rst"):
            if "dist-info" in str(f) or "egg-info" in str(f):
                try:
                    text = dist.locate_file(f).read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                if text.strip():
                    found.append((f.name, text))
    return found


lines = [
    "# 제3자 라이선스 고지 (Third-Party Licenses)",
    "",
    "PDF 에디터 배포본(exe)에는 아래 오픈소스 구성 요소가 포함되어 있습니다.",
    "각 구성 요소의 저작권은 해당 제작자에게 있으며, 아래 라이선스 조건에 따라 배포됩니다.",
    "",
    "## 목록",
    "",
]
entries = []
for name in sorted(dist_names, key=str.lower):
    try:
        dist = metadata.distribution(name)
    except metadata.PackageNotFoundError:
        continue
    meta = dist.metadata
    lic = meta.get("License-Expression") or meta.get("License") or "(파일 참조)"
    lic = " ".join(lic.split())[:120]
    home = meta.get("Home-page") or next(
        (u.split(",", 1)[1].strip() for u in meta.get_all("Project-URL") or [] if "," in u), "")
    entries.append((meta["Name"], meta["Version"], lic, home, license_files(dist)))
    lines.append(f"- **{meta['Name']}** {meta['Version']} — {lic}" + (f" — {home}" if home else ""))

lines += [
    "- **Python** — PSF License — https://www.python.org/",
    "- **Qt** (PySide6가 포함) — LGPL-3.0 — https://www.qt.io/",
    "",
    "## Qt / PySide6 (LGPL-3.0) 안내",
    "",
    "이 프로그램은 Qt for Python(PySide6)을 LGPL-3.0 조건으로 사용합니다.",
    "Qt 라이브러리는 exe 폴더 안의 `_internal\\PySide6` 에 별도 파일(DLL)로 들어 있으며,",
    "사용자는 LGPL-3.0이 허용하는 범위에서 이를 같은 버전 계열의 Qt 라이브러리로 교체할 수 있습니다.",
    "Qt for Python의 소스코드는 https://code.qt.io/cgit/pyside/pyside-setup.git/ 에서 받을 수 있습니다.",
    "",
    "## OpenCV 안의 FFmpeg 안내",
    "",
    "`opencv-python-headless`에는 FFmpeg 라이브러리(LGPL 계열)가 함께 들어 있습니다.",
    "이 프로그램은 동영상 기능을 사용하지 않으며, 해당 파일은 라이브러리 구성상 포함되어 있습니다.",
    "",
    "## 라이선스 전문",
    "",
]

seen: dict[str, str] = {}
for name, version, lic, home, files in entries:
    for fname, text in files:
        key = " ".join(text.split())
        if key in seen:
            lines += [f"### {name} {version} — {fname}", f"(위 {seen[key]}의 문구와 동일)", ""]
            continue
        seen[key] = f"{name} {version} / {fname}"
        lines += [f"### {name} {version} — {fname}", "", "```text", text.rstrip(), "```", ""]

py_license = Path(sys.base_prefix) / "LICENSE.txt"
if py_license.exists():
    lines += ["### Python — LICENSE.txt", "", "```text", py_license.read_text(encoding="utf-8", errors="replace").rstrip(), "```", ""]

out_path.write_text("\n".join(lines), encoding="utf-8")
print(f"{out_path}: {len(entries)}개 패키지, {len(seen)}개 고유 라이선스 문구, {out_path.stat().st_size // 1024} KB")
for name, version, lic, _, files in entries:
    print(f"  {name} {version}: {lic} ({len(files)}개 파일)")
