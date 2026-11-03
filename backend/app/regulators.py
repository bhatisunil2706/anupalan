"""Financial-sector regulators' cyber incident reporting deadlines, shown as clocks on incidents.

CERT-In and the DPDP Board have their own fields on the incident; these are the sector regulators. An incident is
marked as reportable to one or more regulators (`Incident.regulators`); each regulator has one or more clocks that run
from the time the incident was detected. A regulator is suggested when the organisation uses one of its frameworks.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Regulator:
    key: str
    name: str
    hint: str
    frameworks: frozenset[str]


@dataclass(frozen=True)
class Clock:
    key: str
    regulator: str
    title: str
    rule: str
    hours: int


REGULATORS: dict[str, Regulator] = {r.key: r for r in (
    Regulator("rbi", "Reportable to RBI",
              "RBI-regulated entities (banks, NBFCs, payment system operators, payment aggregators) report cyber "
              "incidents within 6 hours of detection.",
              frozenset({"rbi_cyber", "rbi_dpsc", "rbi_pso", "rbi_pa"})),
    Regulator("sebi", "Reportable to SEBI",
              "SEBI-regulated entities report cyber incidents to SEBI within 6 hours under CSCRF.",
              frozenset({"sebi_cscrf"})),
    Regulator("irdai", "Reportable to IRDAI",
              "Insurers and intermediaries copy their CERT-In report to IRDAI within 6 hours.",
              frozenset({"irdai_cyber"})),
    Regulator("ifsca", "Reportable to IFSCA",
              "IFSCA-regulated entities in GIFT City report within 6 hours, then an interim report in 3 days and a "
              "root cause analysis in 30 days.",
              frozenset({"ifsca_cyber"})),
)}

CLOCKS: list[Clock] = [
    Clock("rbi", "rbi", "Report to RBI",
          "Within 6 hours of detection on the DAKSH portal (non-bank PSOs: Annex 1 format; housing finance companies "
          "report to NHB)", 6),
    Clock("sebi", "sebi", "Report to SEBI", "Within 6 hours of detection, through SEBI's incident reporting portal "
          "(CSCRF)", 6),
    Clock("irdai", "irdai", "Copy the CERT-In report to IRDAI", "Within 6 hours of detection (IRDAI Cyber Security "
          "Guidelines 2026)", 6),
    Clock("ifsca", "ifsca", "Initial report to IFSCA", "Within 6 hours of detection, to cyber-incidents@ifsca.gov.in "
          "copying IFSCA's CISO", 6),
    Clock("ifsca_interim", "ifsca", "Interim report to IFSCA", "Within 3 days of detection", 72),
    Clock("ifsca_rca", "ifsca", "Root cause analysis to IFSCA", "Within 30 days of detection", 720),
]
CLOCK_KEYS = {c.key for c in CLOCKS}


def clocks_for(regulators: list[str] | None) -> list[Clock]:
    selected = set(regulators or [])
    return [c for c in CLOCKS if c.regulator in selected]


def reminder_lead_hours(clock: Clock) -> int:
    """When to send the 'due soon' reminder: 2 hours before short clocks, a day before longer ones."""
    return 2 if clock.hours <= 6 else 24
