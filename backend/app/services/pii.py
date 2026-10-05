"""Personal data detectors tuned for India. Values are classified in memory and only masked examples are kept."""
import re
from dataclasses import dataclass

# ---------------------------------------------------------------- validators


_VERHOEFF_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5], [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7], [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3], [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]
_VERHOEFF_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4], [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7], [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]


def verhoeff_valid(number: str) -> bool:
    c = 0
    for i, ch in enumerate(reversed(number)):
        c = _VERHOEFF_D[c][_VERHOEFF_P[i % 8][int(ch)]]
    return c == 0


def luhn_valid(number: str) -> bool:
    total, alt = 0, False
    for ch in reversed(number):
        d = int(ch)
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


# ---------------------------------------------------------------- detectors

UPI_HANDLES = (
    "okaxis|oksbi|okhdfcbank|okicici|ybl|ibl|axl|paytm|apl|upi|axisbank|icici|hdfcbank|sbi|kotak|yesbank|"
    "airtel|jio|freecharge|mobikwik|idfcbank|federal|indus|rbl|pnb|boi|barodampay|aubank|fbl|ikwik|waicici|"
    "wahdfcbank|waaxis|wasbi|ptyes|ptaxis|pthdfc|ptsbi|superyes|naviaxis|yapl"
)

PATTERNS = {
    "aadhaar": re.compile(r"(?<!\d)[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}(?!\d)"),
    "pan": re.compile(r"(?<![A-Z0-9])[A-Z]{3}[ABCFGHLJPTK][A-Z]\d{4}[A-Z](?![A-Z0-9])"),
    "gstin": re.compile(r"(?<![A-Z0-9])\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z](?![A-Z0-9])"),
    "card": re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)"),
    "email": re.compile(r"(?<![\w.+-])[\w.+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}(?![\w-])"),
    "upi": re.compile(rf"(?<![\w.-])[\w.-]{{2,64}}@(?:{UPI_HANDLES})(?![\w.-])", re.I),
    "phone": re.compile(r"(?<![\d+])(?:\+91[ -]?|91[ -]|0)?[6-9]\d{4}[ -]?\d{5}(?!\d)"),
    "ifsc": re.compile(r"(?<![A-Z0-9])[A-Z]{4}0[A-Z0-9]{6}(?![A-Z0-9])"),
}

# Categories that are too ambiguous to detect from values alone; found only via column / key names.
NAME_HINTS = {
    "aadhaar": ["aadhaar", "aadhar", "uidai", "uid_no"],
    "pan": ["pan_no", "pan_number", "pancard", "pan_card", "pan"],
    "passport": ["passport"],
    "voter_id": ["voter", "epic_no"],
    "dob": ["dob", "date_of_birth", "birth_date", "birthdate", "birthday"],
    "phone": ["phone", "mobile", "msisdn", "contact_no", "whatsapp"],
    "email": ["email", "e_mail"],
    "address": ["address", "addr_line", "street", "pincode", "pin_code", "postal_code", "zipcode"],
    "name": ["first_name", "last_name", "full_name", "customer_name", "fname", "lname", "father_name"],
    "bank_account": ["account_no", "account_number", "acct_no", "bank_account"],
    "health": ["diagnosis", "medical", "blood_group", "prescription", "health"],
    "biometric": ["fingerprint", "biometric", "face_template"],
    "gender": ["gender", "sex"],
}

LABELS = {
    "aadhaar": "Aadhaar number",
    "pan": "PAN",
    "gstin": "GSTIN",
    "card": "Payment card number",
    "email": "Email address",
    "upi": "UPI ID",
    "phone": "Phone number",
    "ifsc": "Bank IFSC",
    "passport": "Passport number",
    "voter_id": "Voter ID",
    "dob": "Date of birth",
    "address": "Address",
    "name": "Name",
    "bank_account": "Bank account number",
    "health": "Health data",
    "biometric": "Biometric data",
    "gender": "Gender",
}

SENSITIVE = {"aadhaar", "pan", "card", "bank_account", "health", "biometric", "passport"}


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def mask(category: str, value: str) -> str:
    v = value.strip()
    if category == "email" or category == "upi":
        user, _, domain = v.partition("@")
        return f"{user[:1]}{'*' * max(len(user) - 1, 2)}@{domain}"
    keep = 4 if len(v) > 6 else 1
    return "".join("X" if ch.isalnum() else ch for ch in v[:-keep]) + v[-keep:]


def classify(value: str) -> dict[str, str]:
    """Return {category: matched text} for the personal data types found in one value."""
    found: dict[str, str] = {}
    if not value or len(value) > 5000:
        value = (value or "")[:5000]
    for m in PATTERNS["aadhaar"].finditer(value):
        if verhoeff_valid(_digits(m.group())):
            found["aadhaar"] = m.group()
            break
    for cat in ("pan", "gstin", "ifsc"):
        m = PATTERNS[cat].search(value)
        if m:
            found[cat] = m.group()
    if "gstin" in found and "pan" in found and found["pan"] in found["gstin"]:
        del found["pan"]  # a GSTIN embeds the PAN
    for m in PATTERNS["card"].finditer(value):
        d = _digits(m.group())
        if 13 <= len(d) <= 19 and luhn_valid(d) and d[0] in "234568" and not (
                "aadhaar" in found and _digits(found["aadhaar"]) in d):
            found["card"] = m.group()
            break
    m = PATTERNS["upi"].search(value)
    if m:
        found["upi"] = m.group()
    m = PATTERNS["email"].search(value)
    if m and ("upi" not in found or m.group() != found["upi"]):
        found["email"] = m.group()
    if "card" not in found and "aadhaar" not in found:
        m = PATTERNS["phone"].search(value)
        if m:
            found["phone"] = m.group()
    return found


def hint_categories(name: str) -> list[str]:
    n = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    parts = set(n.split("_"))
    out = []
    for cat, hints in NAME_HINTS.items():
        for h in hints:
            if (h == n) or (("_" in h) and h in n) or (("_" not in h) and h in parts) or (len(h) > 5 and h in n):
                out.append(cat)
                break
    return out


@dataclass
class FieldStats:
    sampled: int = 0
    matches: dict[str, int] = None
    examples: dict[str, list[str]] = None

    def __post_init__(self):
        self.matches = {}
        self.examples = {}

    def add(self, value) -> None:
        if value is None:
            return
        text = str(value)
        if not text.strip():
            return
        self.sampled += 1
        for cat, hit in classify(text).items():
            self.matches[cat] = self.matches.get(cat, 0) + 1
            ex = self.examples.setdefault(cat, [])
            if len(ex) < 3:
                ex.append(mask(cat, hit))


def findings_for_field(field_name: str, stats: FieldStats, min_ratio: float = 0.05) -> list[dict]:
    """Turn field statistics into findings. Value matches need to cover a minimum share of the sample."""
    out = []
    for cat, n in stats.matches.items():
        if n >= 1 and (stats.sampled == 0 or n / stats.sampled >= min_ratio or n >= 5):
            out.append({"category": cat, "matches": n, "sampled": stats.sampled, "by_name_only": False,
                        "examples": stats.examples.get(cat, [])})
    found = {f["category"] for f in out}
    for cat in hint_categories(field_name):
        if cat not in found:
            out.append({"category": cat, "matches": 0, "sampled": stats.sampled, "by_name_only": True,
                        "examples": []})
    return out
