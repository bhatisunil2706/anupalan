"""Load framework, control and policy content from app/content into the database (idempotent upsert)."""
import re
from pathlib import Path

import yaml
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import ControlTemplate, Framework, Mapping, PolicyTemplate, Requirement

CONTENT_DIR = Path(__file__).resolve().parent.parent / "content"
_FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.S)


class ContentError(ValueError):
    pass


def read_frameworks() -> list[dict]:
    return [yaml.safe_load(p.read_text()) for p in sorted((CONTENT_DIR / "frameworks").glob("*.yaml"))]


def read_controls() -> list[dict]:
    return yaml.safe_load((CONTENT_DIR / "controls.yaml").read_text())["controls"]


def read_policy_templates() -> list[dict]:
    out = []
    for p in sorted((CONTENT_DIR / "policies").glob("*.md")):
        m = _FRONTMATTER.match(p.read_text())
        if not m:
            raise ContentError(f"{p.name}: missing front matter")
        meta = yaml.safe_load(m.group(1))
        out.append({**meta, "body_md": m.group(2).strip() + "\n"})
    return out


def validate_content(frameworks: list[dict], controls: list[dict]) -> None:
    """Every requirement must map to at least one control, and every mapping must point at a real requirement."""
    codes = [c["code"] for c in controls]
    if len(codes) != len(set(codes)):
        raise ContentError("Duplicate control codes")
    for fw in frameworks:
        refs = [r["ref"] for r in fw["requirements"]]
        if len(refs) != len(set(refs)):
            raise ContentError(f"{fw['code']}: duplicate requirement refs")
        mapped = {ref for c in controls for ref in c.get("maps", {}).get(fw["code"], [])}
        unmapped = [r for r in refs if r not in mapped]
        unknown = sorted(mapped - set(refs))
        if unmapped:
            raise ContentError(f"{fw['code']}: requirements without a control: {unmapped}")
        if unknown:
            raise ContentError(f"{fw['code']}: controls map to unknown refs: {unknown}")


def load_content(db: Session) -> dict:
    frameworks = read_frameworks()
    controls = read_controls()
    validate_content(frameworks, controls)

    req_index: dict[tuple[str, str], Requirement] = {}
    for fw_data in frameworks:
        fw = db.scalar(select(Framework).where(Framework.code == fw_data["code"])) or Framework(code=fw_data["code"])
        for field in ("name", "short_name", "version", "region", "publisher", "source_url", "content_version",
                      "review_status"):
            setattr(fw, field, str(fw_data.get(field, "")))
        fw.description = (fw_data.get("description") or "").strip()
        db.add(fw)
        db.flush()
        existing = {r.ref: r for r in db.scalars(select(Requirement).where(Requirement.framework_id == fw.id))}
        seen = set()
        for order, r in enumerate(fw_data["requirements"]):
            req = existing.get(r["ref"]) or Requirement(framework_id=fw.id, ref=r["ref"])
            req.section = r.get("section", "")
            req.title = r["title"]
            req.guidance = r.get("guidance", "")
            req.condition = r.get("condition")
            req.order = order
            db.add(req)
            seen.add(r["ref"])
            req_index[(fw.code, r["ref"])] = req
        for ref, req in existing.items():
            if ref not in seen:
                db.delete(req)
    db.flush()

    for c in controls:
        tpl = db.scalar(select(ControlTemplate).where(ControlTemplate.code == c["code"])) or ControlTemplate(
            code=c["code"]
        )
        tpl.title = c["title"]
        tpl.description = c["description"].strip()
        tpl.category = c["category"]
        tpl.frequency = c["frequency"]
        tpl.evidence_hint = c.get("evidence_hint", "")
        tpl.automatable = bool(c.get("automated", False))
        db.add(tpl)
        db.flush()
        db.execute(delete(Mapping).where(Mapping.control_template_id == tpl.id))
        for fw_code, refs in c.get("maps", {}).items():
            for ref in refs:
                db.add(Mapping(requirement_id=req_index[(fw_code, ref)].id, control_template_id=tpl.id))

    for p in read_policy_templates():
        pt = db.scalar(select(PolicyTemplate).where(PolicyTemplate.slug == p["slug"])) or PolicyTemplate(
            slug=p["slug"]
        )
        pt.title = p["title"]
        pt.body_md = p["body_md"]
        pt.control_codes = list(p.get("controls", []))
        pt.review_months = int(p.get("review_months", 12))
        db.add(pt)

    db.commit()
    return {
        "frameworks": len(frameworks),
        "requirements": len(req_index),
        "controls": len(controls),
    }
