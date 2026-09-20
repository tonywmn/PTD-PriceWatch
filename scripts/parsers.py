import json
import re
from dataclasses import dataclass
from html import unescape


@dataclass
class Result:
    price: float | None
    availability: str
    validated: bool
    status: str


PRODUCT_PATTERNS = (
    r"playstation\s*[®™]?\s*5\s*pro",
    r"playstation\s*[®™]?\s*5\s*[-–]?\s*pro",
    r"ps5\s*pro",
    r"playstation\s*pro",
)

CAPACITY_PATTERNS = (
    r"\b2\s*tb\b",
    r"\b2\.000\s*gb\b",
    r"\b2000\s*gb\b",
)

SOLD_OUT_PATTERNS = (
    "dieser artikel ist dauerhaft ausverkauft",
    "artikel ist dauerhaft ausverkauft",
    "unser aktionsangebot ist leider ausverkauft",
    "derzeit nicht vorrätig",
    "zurzeit nicht verfügbar",
    "artikel kann derzeit nicht gekauft werden",
    "aktuell ausverkauft",
    "nicht auf lager",
    "leider keine lieferung möglich",
    "keine angebote",
)

BUY_SIGNALS = (
    "in den warenkorb",
    "in den einkaufswagen",
    "jetzt kaufen",
    "sofort lieferbar",
    "auf lager",
)


def normalize(text: str) -> str:
    value = unescape(text or "")
    value = value.replace("\u00ad", "").replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def money(value) -> float | None:
    if value is None:
        return None

    raw = normalize(str(value))
    match = re.search(r"\d[\d.\s]*(?:,\d{2})?|\d+(?:\.\d{2})?", raw)
    if not match:
        return None

    number = match.group(0).replace(" ", "")

    try:
        if "," in number:
            parsed = float(number.replace(".", "").replace(",", "."))
        elif number.count(".") > 1:
            parsed = float(number.replace(".", ""))
        else:
            parsed = float(number)
    except ValueError:
        return None

    return parsed if 300 <= parsed <= 3000 else None


def product_identity_ok(text: str, require_capacity: bool = True) -> bool:
    value = normalize(text).lower()
    product_match = any(re.search(pattern, value) for pattern in PRODUCT_PATTERNS)
    capacity_match = any(re.search(pattern, value) for pattern in CAPACITY_PATTERNS)
    return product_match and (capacity_match or not require_capacity)


def first_sold_out_signal(text: str) -> str | None:
    value = normalize(text).lower()
    return next((signal for signal in SOLD_OUT_PATTERNS if signal in value), None)


def prices_near_product(text: str) -> list[float]:
    value = normalize(text)
    prices = []

    patterns = (
        r"(?:PlayStation\s*[®™]?\s*5\s*Pro|PS5\s*Pro)[\s\S]{0,900}?"
        r"(?<!\d)(\d{3,4}(?:\.\d{3})*,\d{2})\s*€",
        r"(?<!\d)(\d{3,4}(?:\.\d{3})*,\d{2})\s*€[\s\S]{0,500}?"
        r"(?:PlayStation\s*[®™]?\s*5\s*Pro|PS5\s*Pro)",
    )

    for pattern in patterns:
        for match in re.findall(pattern, value, re.I):
            parsed = money(match)
            if parsed is not None:
                prices.append(parsed)

    return prices


def walk_json(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk_json(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk_json(value)


def jsonld_offers(html: str) -> list[tuple[float | None, str, str]]:
    offers_found = []

    scripts = re.findall(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html or "",
        re.I | re.S,
    )

    for raw in scripts:
        try:
            root = json.loads(unescape(raw).strip())
        except (json.JSONDecodeError, TypeError):
            continue

        for item in walk_json(root):
            name = normalize(str(item.get("name", "")))
            if not product_identity_ok(name, require_capacity=False):
                continue

            offers = item.get("offers", {})
            if not isinstance(offers, list):
                offers = [offers]

            for offer in offers:
                if not isinstance(offer, dict):
                    continue
                price = money(offer.get("price") or offer.get("lowPrice"))
                availability = normalize(str(offer.get("availability", ""))).lower()
                offers_found.append((price, availability, name))

    return offers_found


def visible_price(text: str, provider: str) -> float | None:
    value = normalize(text)

    provider_patterns = {
        "PlayStation Direct DE": (
            r"PlayStation\s*[®™]?\s*5\s*Pro(?:\s*Konsole)?\s*[-–]?\s*2\s*TB"
            r"[\s\S]{0,400}?(\d{3,4},\d{2})\s*€",
            r"(\d{3,4},\d{2})\s*€[\s\S]{0,300}?(?:Lagerung|Speicher)\s*:\s*2\s*TB",
        ),
        "MediaMarkt DE": (
            r"SONY\s+PlayStation[®™]?5\s+Pro[\s\S]{0,800}?(\d{3,4},\d{2})\s*€",
        ),
        "Saturn DE": (
            r"SONY\s+PlayStation[®™]?5\s+Pro[\s\S]{0,800}?(\d{3,4},\d{2})\s*€",
        ),
        "Alternate DE": (
            r"PlayStation\s*5\s*Pro\s*2\s*TB[\s\S]{0,600}?€\s*(\d{3,4},\d{2})",
            r"€\s*(\d{3,4},\d{2})[\s\S]{0,500}?PlayStation\s*5\s*Pro",
        ),
        "Expert DE": (
            r"PlayStation[®™]?5\s*Pro[\s\S]{0,900}?(\d{3,4},\d{2})\s*€",
        ),
        "Amazon.de": (
            r"Playstation\s*5\s*Pro\s*2\s*TB[\s\S]{0,700}?(\d{3,4},\d{2})\s*€",
            r"(\d{3,4},\d{2})\s*€[\s\S]{0,500}?Playstation\s*5\s*Pro\s*2\s*TB",
        ),
        "Geizhals DE": (
            r"Sony\s+PlayStation\s+5\s+Pro\s*[-–]?\s*2TB[\s\S]{0,1200}?\bab\s*€?\s*(\d{1,4}(?:\.\d{3})*,\d{2})",
            r"\bab\s*€\s*(\d{1,4}(?:\.\d{3})*,\d{2})",
        ),
        "Idealo DE": (
            r"Sony\s+PlayStation\s+5\s+Pro[\s\S]{0,1200}?Neu\s+ab\s+(\d{1,4}(?:\.\d{3})*,\d{2})\s*€",
            r"Neu\s+ab\s+(\d{1,4}(?:\.\d{3})*,\d{2})\s*€",
        ),
    }

    for pattern in provider_patterns.get(provider, ()):
        match = re.search(pattern, value, re.I)
        if match:
            parsed = money(match.group(1))
            if parsed is not None:
                return parsed

    nearby = prices_near_product(value)
    return nearby[0] if nearby else None


def determine_availability(provider: str, text: str, html: str) -> tuple[str, str | None]:
    value = normalize(text).lower()
    sold_out = first_sold_out_signal(value)

    if sold_out:
        return "unavailable", sold_out

    json_offers = jsonld_offers(html)
    if any("instock" in availability or "limitedavailability" in availability for _, availability, _ in json_offers):
        return "available", None

    if provider in ("MediaMarkt DE", "Saturn DE"):
        delivery_ok = "lieferung nach hause" in value and "in den warenkorb" in value
        return ("available", None) if delivery_ok else ("unknown", None)

    if provider == "Amazon.de":
        return ("available", None) if "in den einkaufswagen" in value else ("unknown", None)

    if provider == "Alternate DE":
        return ("available", None) if "in den warenkorb" in value else ("unknown", None)

    if provider == "PlayStation Direct DE":
        buyable = "in den warenkorb" in value or "jetzt kaufen" in value
        return ("available", None) if buyable else ("unknown", None)

    if provider == "Geizhals DE":
        available = bool(re.search(r"\b[1-9]\d*\s+Angebote?\b", value, re.I))
        return ("available", None) if available else ("unknown", None)

    if provider == "Idealo DE":
        available = "neu ab" in value and "angebote" in value
        return ("available", None) if available else ("unknown", None)

    return ("available", None) if any(signal in value for signal in BUY_SIGNALS) else ("unknown", None)


def parse_text(provider: str, text: str, html: str = "") -> Result:
    combined = normalize(f"{text} {re.sub(r'<[^>]+>', ' ', html or '')}")

    # Comparison pages may abbreviate capacity differently, but must still identify PS5 Pro.
    require_capacity = provider not in ("Geizhals DE", "Idealo DE")
    identity = product_identity_ok(combined, require_capacity=require_capacity)

    if not identity:
        return Result(None, "unknown", False, "Produktidentität nicht bestätigt")

    availability, sold_out_signal = determine_availability(provider, text, html)

    price = visible_price(text, provider)
    if price is None:
        offers = jsonld_offers(html)
        price = next((offer_price for offer_price, _, _ in offers if offer_price is not None), None)

    if availability == "unavailable":
        status = f"Nicht verfügbar: {sold_out_signal}"
        return Result(price, availability, False, status)

    if availability == "available" and price is not None:
        return Result(price, availability, True, "Preis & Verfügbarkeit bestätigt")

    if price is not None:
        return Result(price, "unknown", False, "Preis erkannt, Verfügbarkeit unbestätigt")

    if availability == "available":
        return Result(None, availability, False, "Verfügbarkeit erkannt, Preis unbestätigt")

    return Result(None, "unknown", False, "Nicht eindeutig bestätigt")
