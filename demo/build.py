"""Build the static demo site from a recording made with capture.py.

    python demo/build.py demo/capture.json OUT_DIR [--base-path /anupalan]

Copies the frontend to a temporary folder, swaps in the demo pieces from demo/files (an /api shim that answers from
recorded data, a static-export config, no server-only code), writes the recorded responses as JSON files and builds
plain HTML/JS into OUT_DIR, ready for GitHub Pages. The real frontend is not changed.
"""
import argparse, hashlib, json, os, re, shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = ROOT / "demo" / "files"
DYNAMIC = {  # route folder -> regex over recorded page paths giving the param
    "(app)/access-reviews/[id]": r"^/access-reviews/([0-9a-f-]{36})$",
    "(app)/controls/[id]": r"^/controls/([0-9a-f-]{36})$",
    "(app)/docs/[slug]": r"^/docs/([a-z0-9-]+)$",
    "(app)/frameworks/[code]": r"^/frameworks/([a-z0-9_]+)$",
    "(app)/incidents/[id]": r"^/incidents/([0-9a-f-]{36})$",
    "(app)/policies/[id]": r"^/policies/([0-9a-f-]{36})$",
    "(app)/training/[slug]": r"^/training/(?!manage$)([a-z0-9-]+)(?:/certificate)?$",
    "(app)/training/manage/[slug]": r"^/training/manage/([a-z0-9-]+)$",
    "(app)/vendors/[id]": r"^/vendors/([0-9a-f-]{36})$",
    "(app)/vendors/questionnaires/[slug]": r"^/vendors/questionnaires/([a-z0-9-]+)$",
}
REMOVE = ["src/proxy.ts", "src/app/(auth)/signup", "src/app/(auth)/forgot-password", "src/app/(auth)/reset-password",
          "src/app/(auth)/verify-email", "src/app/(auth)/onboarding", "src/app/(auth)/invite", "src/app/l", "src/app/p",
          "src/app/q"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("capture"); ap.add_argument("out"); ap.add_argument("--base-path", default="/anupalan")
    a = ap.parse_args()
    cap = json.load(open(a.capture))
    (ROOT / "demo" / ".build").mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="site-", dir=ROOT / "demo" / ".build"))
    src = work / "frontend"
    shutil.copytree(ROOT / "frontend", src, ignore=shutil.ignore_patterns("node_modules", ".next", "out"))
    # Hard-linked copy of the dependencies (fast, no extra space); bundlers refuse links that leave the project.
    if subprocess.run(["cp", "-al", str(ROOT / "frontend" / "node_modules"), str(src / "node_modules")]).returncode:
        shutil.copytree(ROOT / "frontend" / "node_modules", src / "node_modules", symlinks=True)
    for r in REMOVE:
        p = src / r
        shutil.rmtree(p) if p.is_dir() else p.unlink(missing_ok=True)
    shutil.copy(FILES / "next.config.ts", src / "next.config.ts")
    (src / "src" / "demo").mkdir()
    shutil.copy(FILES / "shim.tsx", src / "src" / "demo" / "shim.tsx")
    shutil.copy(FILES / "layout.tsx", src / "src" / "app" / "layout.tsx")
    shutil.copy(FILES / "redirect-page.tsx", src / "src" / "app" / "page.tsx")
    shutil.copy(FILES / "redirect-page.tsx", src / "src" / "app" / "(auth)" / "login" / "page.tsx")

    for folder, pattern in DYNAMIC.items():
        params = sorted({m.group(1) for p in cap["pages"] if (m := re.match(pattern, p))})
        key = folder.rsplit("[", 1)[1].rstrip("]")
        if not params:
            shutil.rmtree(src / "src" / "app" / folder)
            print(f"no recorded pages for {folder}; left out of the demo")
            continue
        (src / "src" / "app" / folder / "layout.tsx").write_text(
            f"export const dynamicParams = false;\n\n"
            f"export function generateStaticParams() {{\n  return {json.dumps([{key: v} for v in params])};\n}}\n\n"
            "export default function Layout({ children }: { children: React.ReactNode }) {\n  return children;\n}\n")

    data = src / "public" / "demo-data"
    data.mkdir(parents=True)
    index = {}
    for key, body in cap["responses"].items():
        if not key.startswith("/help"):  # tidy what the recording run leaves in sample data
            text = json.dumps(body).replace("http://localhost:3000", "https://compliance.paisasetu.example")
            body = json.loads(text.replace("HeadlessChrome", "Chrome"))
        name = hashlib.sha256(key.encode()).hexdigest()[:20] + ".json"
        (data / name).write_text(json.dumps(body, separators=(",", ":")))
        index[key] = name
    (data / "index.json").write_text(json.dumps(index, separators=(",", ":")))

    env = {**os.environ, "NEXT_PUBLIC_BASE_PATH": a.base_path, "NEXT_PUBLIC_DEMO": "1", "NEXT_TELEMETRY_DISABLED": "1"}
    r = subprocess.run(["npx", "next", "build"], cwd=src, env=env)
    if r.returncode:
        sys.exit(f"build failed; sources left in {src}")
    out = Path(a.out)
    shutil.rmtree(out, ignore_errors=True)
    shutil.copytree(src / "out", out)
    (out / ".nojekyll").write_text("")
    print(f"Demo site written to {out} ({len(index)} recorded responses)")
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
