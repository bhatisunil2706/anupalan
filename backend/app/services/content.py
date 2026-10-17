"""Load framework, control and policy content from app/content into the database (idempotent upsert)."""
import re
from pathlib import Path

import yaml
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (
    ControlTemplate,
    Framework,
    Mapping,
    PolicyTemplate,
    QuestionnaireTemplate,
    Requirement,
    TrainingCourse,
)

CONTENT_DIR = Path(__file__).resolve().parent.parent / "content"
_FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.S)


class ContentError(ValueError):
    pass


def read_frameworks() -> list[dict]:
    return [yaml.safe_load(p.read_text()) for p in sorted((CONTENT_DIR / "frameworks").glob("*.yaml"))]


def read_controls() -> list[dict]:
    controls = yaml.safe_load((CONTENT_DIR / "controls.yaml").read_text())["controls"]
    acceptance = yaml.safe_load((CONTENT_DIR / "acceptance.yaml").read_text())["acceptance"]
    for c in controls:
        c["acceptance"] = acceptance.get(c["code"], [])
    unknown = set(acceptance) - {c["code"] for c in controls}
    if unknown:
        raise ContentError(f"acceptance.yaml lists unknown controls: {sorted(unknown)}")
    return controls


def read_policy_templates() -> list[dict]:
    out = []
    for p in sorted((CONTENT_DIR / "policies").glob("*.md")):
        m = _FRONTMATTER.match(p.read_text())
        if not m:
            raise ContentError(f"{p.name}: missing front matter")
        meta = yaml.safe_load(m.group(1))
        out.append({**meta, "body_md": m.group(2).strip() + "\n"})
    return out


def read_yaml_dir(name: str) -> list[dict]:
    items = [yaml.safe_load(p.read_text()) for p in sorted((CONTENT_DIR / name).glob("*.yaml"))]
    for item in items:
        for i, q in enumerate(item.get("quiz", [])):
            if not 0 <= q["answer"] < len(q["options"]):
                raise ContentError(f"{item['slug']}: quiz question {i + 1} has an invalid answer index")
        ids = [q["id"] for q in item.get("questions", [])]
        if len(ids) != len(set(ids)):
            raise ContentError(f"{item['slug']}: duplicate question ids")
    return items


def merge_requirement_mappings(frameworks: list[dict], controls: list[dict]) -> None:
    """Frameworks may list their covering controls per requirement (`controls: [ACC-03, ...]`) instead of the control
    library listing the framework. Fold those into each control's `maps` so the rest of the loader sees one shape."""
    by_code = {c["code"]: c for c in controls}
    for fw in frameworks:
        for r in fw["requirements"]:
            for code in r.get("controls", []) or []:
                if code not in by_code:
                    raise ContentError(f"{fw['code']} {r['ref']}: unknown control {code}")
                refs = by_code[code].setdefault("maps", {}).setdefault(fw["code"], [])
                if r["ref"] not in refs:
                    refs.append(r["ref"])


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


QUESTION_TYPES = ("yes_no", "text", "choice")


def validate_questions(questions: list[dict], where: str) -> None:
    """Shared by built-in content and companies' own questionnaires."""
    ids = [q.get("id") for q in questions]
    if len(ids) != len(set(ids)) or not all(ids):
        raise ContentError(f"{where}: every question needs a unique id")
    for q in questions:
        if q.get("type") not in QUESTION_TYPES:
            raise ContentError(f"{where} {q['id']}: type must be one of {QUESTION_TYPES}")
        if not str(q.get("text", "")).strip():
            raise ContentError(f"{where} {q['id']}: question text is empty")
        if q["type"] == "yes_no" and int(q.get("weight") or 0) > 0 and q.get("good") not in ("yes", "no"):
            raise ContentError(f"{where} {q['id']}: scored yes/no questions need an expected answer")
        if q["type"] == "choice" and len(q.get("options") or []) < 2:
            raise ContentError(f"{where} {q['id']}: choice questions need at least two options")


def check_content() -> dict:
    """Read and validate all framework content without touching the database."""
    frameworks, controls = read_frameworks(), read_controls()
    thin = [c["code"] for c in controls if len(c.get("acceptance", [])) < 2]
    if thin:
        raise ContentError(f"Controls need at least two acceptance criteria: {thin}")
    merge_requirement_mappings(frameworks, controls)
    validate_content(frameworks, controls)
    for q in read_yaml_dir("questionnaires"):
        validate_questions(q["questions"], q["slug"])
    return {"frameworks": len(frameworks), "requirements": sum(len(f["requirements"]) for f in frameworks),
            "controls": len(controls)}


def load_content(db: Session) -> dict:
    frameworks = read_frameworks()
    controls = read_controls()
    merge_requirement_mappings(frameworks, controls)
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
        tpl.acceptance_criteria = list(c.get("acceptance", []))
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

    for c in read_yaml_dir("training"):
        row = db.scalar(select(TrainingCourse).where(TrainingCourse.slug == c["slug"])) or TrainingCourse(
            slug=c["slug"])
        row.title, row.summary, row.minutes = c["title"], c.get("summary", ""), int(c.get("minutes", 10))
        row.body_md, row.quiz, row.pass_mark = c["body_md"], c["quiz"], int(c.get("pass_mark", 80))
        row.control_codes = c.get("control_codes", [])
        row.scenarios = c.get("scenarios", [])
        row.audience, row.category = c.get("audience", "Everyone"), c.get("category", "Security")
        row.order = int(c.get("order", 100))
        db.add(row)

    for q in read_yaml_dir("questionnaires"):
        validate_questions(q["questions"], q["slug"])
        row = db.scalar(select(QuestionnaireTemplate).where(QuestionnaireTemplate.slug == q["slug"])) or \
            QuestionnaireTemplate(slug=q["slug"])
        row.title, row.description, row.questions = q["title"], (q.get("description") or "").strip(), q["questions"]
        row.kind, row.order = q.get("kind", "core"), int(q.get("order", 100))
        row.recommended_for = list(q.get("recommended_for", []))
        db.add(row)

    db.commit()
    return {
        "frameworks": len(frameworks),
        "requirements": len(req_index),
        "controls": len(controls),
    }
