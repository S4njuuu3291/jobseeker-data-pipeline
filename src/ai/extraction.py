"""Conservative evidence checks for AI proposals; unknown values stay null."""

import re
from datetime import date

FIELDS = (
    "role",
    "location",
    "salary_min",
    "salary_max",
    "salary_currency",
    "salary_period",
    "job_type",
    "seniority",
    "work_mode",
    "experience_min",
    "experience_max",
    "education",
    "company_industry",
    "skills",
    "benefits",
    "posting_date",
)
INTEGER_FIELDS = {"salary_min", "salary_max", "experience_min", "experience_max"}
ARRAY_FIELDS = {"skills", "benefits"}
ALIASES = {
    "salary_currency": {
        "IDR": [r"\bRp\b", r"\bIDR\b", r"\brupiah\b"],
        "USD": [r"\bUSD\b", r"US\s*\$"],
        "SGD": [r"\bSGD\b", r"S\s*\$"],
    },
    "salary_period": {
        "monthly": [
            r"per month",
            r"/month",
            r"per bulan",
            r"/bulan",
            r"bulanan",
            r"monthly",
        ],
        "yearly": [r"per year", r"/year", r"per tahun", r"yearly", r"annual"],
        "hourly": [r"per hour", r"/hour", r"per jam", r"hourly"],
        "daily": [r"per day", r"/day", r"per hari", r"daily"],
    },
    "job_type": {
        "full_time": [r"full[\s_-]?time", r"penuh waktu"],
        "part_time": [r"part[\s_-]?time", r"paruh waktu"],
        "contract": [r"contract", r"kontrak"],
        "internship": [r"intern(?:ship)?", r"magang"],
        "freelance": [r"freelance", r"pekerja lepas"],
    },
    "work_mode": {
        "remote": [r"remote", r"work from home", r"\bWFH\b"],
        "hybrid": [r"hybrid", r"hibrida"],
        "on_site": [
            r"on[\s_-]?site",
            r"kerja di lokasi",
            r"work from office",
            r"\bWFO\b",
        ],
    },
    "seniority": {
        "intern": [r"\bintern(?:ship)?\b", r"\bmagang\b"],
        "junior": [r"\bjunior\b", r"\bjr\.?\b"],
        "mid": [r"\bmid(?:dle)?\b"],
        "senior": [r"\bsenior\b", r"\bsr\.?\b"],
        "lead": [r"\blead\b"],
        "manager": [r"\bmanager\b", r"\bmanajer\b"],
        "executive": [r"\bexecutive\b"],
    },
    "education": {
        "high_school": [r"high school", r"\bSMA\b", r"\bSMK\b"],
        "diploma": [r"diploma", r"\bD[1-4]\b"],
        "bachelor": [r"bachelor", r"sarjana", r"\bS1\b"],
        "master": [r"master", r"magister", r"\bS2\b"],
        "phd": [r"\bPh\.?D\b", r"doctorate", r"\bS3\b"],
    },
}


def normalized(value):
    return re.sub(r"\s+", " ", str(value)).strip().casefold()


def contains(source, value):
    return bool(normalized(value)) and normalized(value) in normalized(source)


def alias_supported(field, value, quote):
    patterns = ALIASES[field].get(value, [])
    return any(re.search(pattern, quote, re.I) for pattern in patterns)


def explicit_years(quote):
    if not re.search(r"experience|pengalaman", quote, re.I):
        return None, None
    match = re.search(r"(\d+)\s*[-–]\s*(\d+)\s*(?:years?|tahun)", quote, re.I)
    if match:
        return int(match[1]), int(match[2])
    lower = re.search(
        r"(?:minimum|minimal|min\.?|at least|setidaknya)\s*(\d+)\s*(?:years?|tahun)",
        quote,
        re.I,
    )
    upper = re.search(
        r"(?:maximum|maximal|maksimal|max\.?|at most)\s*(\d+)\s*(?:years?|tahun)",
        quote,
        re.I,
    )
    plus = re.search(r"(\d+)\s*\+\s*(?:years?|tahun)", quote, re.I)
    return int(lower[1]) if lower else int(plus[1]) if plus else None, int(
        upper[1]
    ) if upper else None


def amount(raw, unit):
    pieces = re.split(r"[.,]", raw)
    if len(pieces) > 1 and all(len(p) == 3 for p in pieces[1:]):
        number = float("".join(pieces))
    elif len(pieces) == 2:
        number = float(raw.replace(",", "."))
    elif len(pieces) == 1:
        number = float(raw)
    else:
        return None
    factor = {
        "juta": 1000000,
        "jt": 1000000,
        "million": 1000000,
        "ribu": 1000,
        "thousand": 1000,
        "k": 1000,
    }.get((unit or "").lower(), 1)
    value = number * factor
    return int(value) if value.is_integer() else None


def salary_bounds(quote):
    if not re.search(r"\b(?:salary|gaji|Rp|IDR|USD|SGD|rupiah)\b|\$", quote, re.I):
        return None, None
    units = r"(juta|jt|million|ribu|thousand|k)?"
    match = re.search(
        r"([\d.,]+)\s*"
        + units
        + r"\s*[-–]\s*(?:Rp|IDR|USD|SGD|\$)?\s*([\d.,]+)\s*"
        + units,
        quote,
        re.I,
    )
    if match:
        return amount(match[1], match[2] or match[4]), amount(
            match[3], match[4] or match[2]
        )
    return None, None


def supported(field, value, quote, job_title):
    if re.search(r"\bnot\b|\bno\b|tidak|bukan", quote, re.I):
        return False
    if field in INTEGER_FIELDS:
        if type(value) is not int or value < 0:
            return False
        bounds = (
            explicit_years(quote)
            if field.startswith("experience")
            else salary_bounds(quote)
        )
        return value == bounds[0 if field.endswith("_min") else 1]
    if field in ARRAY_FIELDS:
        return (
            isinstance(value, list)
            and 0 < len(value) <= 15
            and all(isinstance(v, str) and contains(quote, v) for v in value)
        )
    if (
        not isinstance(value, str)
        or not value.strip()
        or normalized(value) in {"unknown", "none", "null", "n/a"}
    ):
        return False
    if field == "posting_date":
        try:
            date.fromisoformat(value)
        except ValueError:
            return False
        return value in quote
    if field in ALIASES:
        if re.search(r"\bnot\b|\bno\b|tidak|bukan", quote, re.I):
            return False
        if field == "seniority" and not contains(job_title, quote):
            # Collaborating with senior people does not make this role senior.
            if not re.search(
                r"seniority|(?:job|position|posisi|jabatan)\s*(?:level|title)?\s*[:=]|level\s*[:=]",
                quote,
                re.I,
            ):
                return False
        if field == "education" and re.search(
            r"preferred|diutamakan|nice.to.have", quote, re.I
        ):
            return False
        return alias_supported(field, value, quote)
    if field == "company_industry" and not re.search(
        r"industry|industri|sector|sektor|bidang", quote, re.I
    ):
        return False
    return contains(quote, value)


def evidence_context(source, quote):
    # Check the surrounding sentence as well: quoting only "remote" must not
    # bypass "This role is not remote" in the original source.
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", source):
        if contains(sentence, quote):
            return sentence
    return source


def context_supports(field, value, quote, source, title):
    title_evidence = field in {"role", "seniority"} and contains(title, quote)
    context = evidence_context(title if title_evidence else source, quote)
    if re.search(r"\bnot\b|\bno\b|tidak|bukan", context, re.I):
        return False
    if field == "posting_date" and not re.search(
        r"posted|published|posting|tayang|dipublikasikan|listing date", context, re.I
    ):
        return False
    if field == "role" and not contains(title, value):
        if not re.search(r"(?:role|posisi|position|jabatan)\s*[:=]", context, re.I):
            return False
    if field == "company_industry" and re.search(
        r"experience|pengalaman|client|customer|klien|pelanggan", context, re.I
    ):
        return False
    if field == "seniority":
        levels = [
            level for level in ALIASES[field] if alias_supported(field, level, context)
        ]
        if len(levels) != 1:
            return False
    if field == "work_mode":
        modes = [
            mode for mode in ALIASES[field] if alias_supported(field, mode, context)
        ]
        if "hybrid" in modes:
            return value == "hybrid"
        if len(modes) > 1:
            return False
    if field == "education" and re.search(
        r"preferred|diutamakan|nice.to.have", context, re.I
    ):
        return False
    return True


def validate_proposals(parsed, fields, title, description):
    """Reject unsupported proposals rather than asking the model to invent proof."""
    if not isinstance(parsed, dict) or any(key not in parsed for key in fields):
        raise ValueError("AI response missing requested fields")
    accepted, evidence, rejected = {}, {}, []
    job_description = description.split("ABOUT COMPANY", 1)[0]
    for field in fields:
        proposal = parsed[field]
        if proposal is None:
            accepted[field] = None
            continue
        if not isinstance(proposal, dict) or set(proposal) != {"value", "evidence"}:
            raise ValueError("AI field must contain value and evidence")
        value, quote = proposal["value"], proposal["evidence"]
        if value is None:
            accepted[field] = None
            continue
        source = description if field == "company_industry" else job_description
        grounded = (
            isinstance(quote, str)
            and len(quote) <= 500
            and (
                contains(source, quote)
                or (field in {"role", "seniority"} and contains(title, quote))
            )
        )
        if (
            grounded
            and supported(field, value, quote, title)
            and context_supports(field, value, quote, source, title)
        ):
            accepted[field] = value
            evidence[field] = quote
        else:
            accepted[field] = None
            rejected.append(field)
    return accepted, evidence, rejected
