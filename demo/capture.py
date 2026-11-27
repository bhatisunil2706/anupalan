"""Record every GET /api response the real app makes while browsing it, for the static demo site."""
import json, re, sys
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright

BASE = "http://localhost:3000"
OUT = sys.argv[1]
store = {}
visited, queue = set(), []
PATTERNS = [r"^/[a-z-]+/?$", r"^/(controls|policies|incidents|vendors|access-reviews)/[0-9a-f-]{36}$",
            r"^/frameworks/[a-z0-9_]+$", r"^/docs/[a-z0-9-]+$", r"^/training/[a-z0-9-]+$",
            r"^/training/[a-z0-9-]+/certificate$", r"^/training/manage/[a-z0-9-]+$",
            r"^/vendors/questionnaires(/[a-z0-9-]+)?$", r"^/dpdp/[a-z]+$", r"^/evidence/review$",
            r"^/account/security$", r"^/training/manage$"]
SKIP = {"/login", "/signup", "/forgot-password", "/reset-password", "/verify-email", "/onboarding", "/policies/new"}

def on_response(r):
    u = urlsplit(r.url)
    if not u.path.startswith("/api/") or r.request.method != "GET" or r.status != 200:
        return
    if "json" not in (r.headers.get("content-type") or ""):
        return
    try:
        store[u.path[4:] + (("?" + u.query) if u.query else "")] = r.json()
    except Exception:
        pass

def enqueue(path):
    path = path.split("#")[0].split("?")[0].rstrip("/") or "/"
    if path in visited or path in SKIP or path in queue:
        return
    if any(re.match(p, path) for p in PATTERNS):
        queue.append(path)

def collect_links(pg):
    for a in pg.locator("a[href^='/']").all():
        try:
            enqueue(a.get_attribute("href"))
        except Exception:
            pass


# Optional: python capture.py OUT [EXISTING] adds to an earlier recording, visiting only pages it doesn't have.
if len(sys.argv) > 2:
    prev = json.load(open(sys.argv[2]))
    store.update(prev["responses"]); visited.update(prev["pages"])
    for p in prev["pages"]:
        visited.discard(p) if p in ("/vendors", "/training", "/training/manage", "/vendors/questionnaires") else None

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1400, "height": 900})
    pg.on("response", on_response)
    pg.goto(BASE + "/login"); pg.fill("input[type=email]", "priya@paisasetu.example")
    pg.fill("input[type=password]", "Demo-Anupalan-2026!"); pg.keyboard.press("Enter")
    pg.wait_for_url("**/dashboard"); pg.wait_for_timeout(1500)
    for start in ["/dashboard", "/tasks", "/frameworks", "/controls", "/evidence/review", "/policies", "/audit",
                  "/training", "/training/manage", "/assistant", "/integrations", "/people", "/access-reviews",
                  "/dpdp/inventory", "/dpdp/consent", "/dpdp/discovery", "/dpdp/requests", "/incidents", "/risks",
                  "/vendors", "/vendors/questionnaires", "/docs", "/account/security", "/settings"]:
        enqueue(start)
    n = 0
    while queue and n < 700:
        path = queue.pop(0); visited.add(path); n += 1
        try:
            pg.goto(BASE + path, wait_until="networkidle", timeout=20000)
        except Exception:
            pass
        pg.wait_for_timeout(300)
        collect_links(pg)
        # Open tabs so their data (and links) are recorded too.
        for t in pg.get_by_role("tab").all()[:8]:
            try:
                t.click(timeout=2000); pg.wait_for_load_state("networkidle", timeout=5000)
                collect_links(pg)
            except Exception:
                pass
        if n % 50 == 0:
            print(n, "pages,", len(store), "responses, queue", len(queue), flush=True)
    # Drawers and dialogs that load data when opened.
    for path, label in [("/incidents", "Report incident"), ("/policies", "New policy"), ("/vendors", "Add vendor")]:
        try:
            pg.goto(BASE + path, wait_until="networkidle"); pg.get_by_role("button", name=label).first.click(timeout=3000)
            pg.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
    json.dump({"responses": store, "pages": sorted(visited)}, open(OUT, "w"))
    print("done", len(visited), "pages,", len(store), "responses")
