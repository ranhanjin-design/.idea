"""Resolve existing pet places to government, provider, then directory pages."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from pypdf import PdfReader

from pawplan.database.db import ROOT, get_connection, init_database
from pawplan.ingestion.fetch_fehd import fetch_fehd_directory
from pawplan.ingestion.fetch_petcircle_groomers import parse_page
from pawplan.normalize import normalize_district
from pawplan.sources import AFCD_VETS, compact, restaurant_source_url, source_identity

CACHE = ROOT / "data/raw/venue_source_pages"
MANIFEST = ROOT / "data/knowledge/venue_sources.json"


def _read(url: str, *, skip_fetch: bool, timeout: int = 20) -> tuple[bytes, str]:
    """Cache by full URL; never put credentials or untrusted URL text in a filename."""
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        raise ValueError("Expected a public HTTP(S) source URL")
    if parts.hostname in {"localhost", "127.0.0.1", "::1"} or parts.hostname.endswith(".local"):
        raise ValueError("Local addresses are not public venue sources")
    CACHE.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(url.encode()).hexdigest()
    body, meta = CACHE / (key + ".bin"), CACHE / (key + ".json")
    if skip_fetch:
        info = json.loads(meta.read_text(encoding="utf-8"))
        return body.read_bytes(), info["fetched_at_utc"]
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 (PawPlanHK academic project)", "Accept-Encoding": "identity"})
    with urlopen(request, timeout=timeout) as response:
        data = response.read(4_000_001)
    if len(data) > 4_000_000:
        raise ValueError("Source response is unexpectedly large")
    fetched = datetime.now(timezone.utc).isoformat()
    body.write_bytes(data)
    meta.write_text(json.dumps({"url": url, "fetched_at_utc": fetched}), encoding="utf-8")
    return data, fetched


def _phone(value: str | None) -> str:
    digits = re.sub(r"\D", "", value or "")
    return digits[-8:] if len(digits) in {8, 11} else ""


def _same_name(place: dict, name: str) -> bool:
    target = compact(name)
    generic = {"動物醫院", "獸醫診所", "寵物醫院", "寵物診所", "動物診所"}
    for field in ("name_zh", "name_en"):
        value = place.get(field) or ""
        if len(compact(value)) >= 8 and compact(value) in target:
            return True
        for part in re.findall(r"[\u4e00-\u9fff]{4,}", value):
            if part not in generic and compact(part) in target:
                return True
    return False


def parse_vet_pdf(path: Path) -> list[dict]:
    """Read the rendered table columns, keeping bilingual names and wrapped rows together."""
    records = []
    for page_no, page in enumerate(PdfReader(path).pages, 1):
        lines = page.extract_text(extraction_mode="layout").splitlines()
        header = next((line for line in lines if "Business Address" in line and "Business Phone" in line), None)
        if not header:
            raise ValueError(f"AFCD table layout changed on page {page_no}")
        address_col, phone_col = header.index("Business Address"), header.index("Business Phone")
        districts = None
        current = None

        def finish():
            nonlocal current
            if current and current["name"] and current["address"] and current["phones"]:
                current["phone"] = current["phones"][0]
                current.pop("has_english", None)
                records.append(current)
            current = None

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("*"):
                break
            region = re.fullmatch(r"([A-Za-z ,&]+) District(?:\s*\(.*\))?", stripped)
            if region:
                finish()
                label = region[1].replace("Hong Kong ", "").replace("New Territories ", "").strip()
                districts = (["Central/Western", "Southern"] if label == "Central, Western and Southern"
                             else [normalize_district(label)])
                continue
            if districts is None or not stripped:
                continue
            name = line[:address_col].strip()
            address = line[address_col:phone_col].strip()
            right = line[phone_col:].strip()
            numbers = [_phone(n) for n in re.findall(r"\d{4}\s*\d{4}", right)]
            # A few source rows place the Chinese address after the phone column.
            tail = re.sub(r"\d{4}\s*\d{4}", "", right).strip(" /")
            if re.search(r"[\u4e00-\u9fff]", tail):
                address = " ".join(x for x in [address, tail] if x)
            if re.fullmatch(r"[\u4e00-\u9fff]{1,8}區", name) and not address:
                continue
            new_row = bool(name) and (current is None
                or bool(re.search(r"[\u4e00-\u9fff]", address))
                or (bool(re.search(r"[A-Za-z]", name)) and current["has_english"]))
            if new_row:
                finish()
                current = {"districts": districts, "name": "", "address": "", "phones": [],
                           "page": page_no, "has_english": False}
            if current:
                if name:
                    current["name"] = " ".join(x for x in [current["name"], name] if x)
                    current["has_english"] |= bool(re.search(r"[A-Za-z]", name))
                if address:
                    current["address"] = " ".join(x for x in [current["address"], address] if x)
                current["phones"].extend(numbers)
        finish()
    if not records:
        raise ValueError("AFCD clinic table contains no usable rows")
    return records


def _addresses_agree(left: str, right: str) -> bool:
    a, b = compact(left), compact(right)
    if a and b and (a in b or b in a):
        return True
    na, nb = set(re.findall(r"\d+", left)), set(re.findall(r"\d+", right))
    if na and nb and not na.intersection(nb):
        return False
    stop = {"hong", "kong", "kowloon", "territories", "new", "shop", "ground", "floor",
            "street", "road", "avenue", "block", "flat", "sha", "tin", "wan", "chai", "tai",
            "building", "centre", "center", "court", "unit", "basement", "village", "district",
            "tsuen", "yuen", "long", "tuen", "mun", "north", "point", "central", "western",
            "southern", "sham", "shui", "sai", "kung", "happy", "valley", "sheung", "ying", "pun"}
    words = lambda text: {w for w in re.findall(r"[a-z]{3,}", text.lower()) if w not in stop}
    if words(left).intersection(words(right)):
        return True
    chinese = re.findall(r"[\u4e00-\u9fff]+", left)
    generic = {"香港新界", "香港九龍", "香港香港", "新界沙田", "香港灣仔", "新界元朗"}
    return any(part[i:i+4] in b and part[i:i+4] not in generic
               for part in chinese for i in range(max(0, len(part)-3)))


def match_vet(place: dict, clinics: list[dict]) -> dict | None:
    district = "Yau Tsim Mong" if place["district"] == "Mong Kok" else place["district"]
    phone = _phone(place.get("phone"))
    matches = [c for c in clinics if phone and phone in c["phones"]
               and district in c["districts"] and _same_name(place, c["name"])
               and _addresses_agree(place.get("address") or "", c["address"])]
    return matches[0] if len(matches) == 1 else None


def _gopaw_links(xml: bytes) -> dict[str, str]:
    result = {}
    for node in ElementTree.fromstring(xml).iter():
        if node.tag.endswith("}loc") or node.tag == "loc":
            url = node.text or ""
            match = re.match(r"https://gopaw\.io/venues/(\d+)-", url)
            if match:
                result[match[1]] = url
    if not result:
        raise ValueError("GoPaw sitemap has no published venue detail URLs")
    return result


def _petcircle_links(skip_fetch: bool) -> dict[str, dict]:
    result = {}
    for page in range(1, 21):
        url = "https://petcircle-hk.vercel.app/grooming" + (f"?page={page}" if page > 1 else "")
        data, fetched = _read(url, skip_fetch=skip_fetch)
        html = data.decode("utf-8")
        published = set(re.findall(r'href="(/businesses/grm-\d+)"', html))
        rows = parse_page(html)
        if not rows:
            break
        added = 0
        for row in rows:
            gid = row["petcircle_id"]
            if gid in result:
                continue
            href = f"/businesses/{gid}"
            if href not in published:
                raise ValueError(f"PetCircle card has no published detail page: {gid}")
            # Extract a provider URL from this card only, never a neighbouring card.
            start = html.find(f'href="{href}"')
            end = html.find('href="/businesses/', start + 10)
            card = html[start:end if end >= 0 else html.find('</main>', start)]
            links = [unescape(x) for x in re.findall(r'href="(https?://[^"]+)"', card)]
            provider = next((x for x in links if "google.com" not in urlsplit(x).netloc), None)
            result[gid] = {**row, "source_url": urljoin(url, href), "website": provider, "fetched_at_utc": fetched}
            added += 1
        if not added:
            break
        # The published pagination gives a bounded final page (currently 14).
        page_numbers = [int(x) for x in re.findall(r'href="/grooming\?page=(\d+)"', html)]
        if page_numbers and page >= max(page_numbers):
            break
    return result


def _provider_match(row: dict, html: str, shared_domain: bool) -> bool:
    visible = unescape(re.sub(r"<script\b.*?</script>|<style\b.*?</style>", " ", html, flags=re.S | re.I))
    visible = re.sub(r"<[^>]+>", " ", visible)
    phone = _phone(row.get("phone"))
    if phone and phone in re.sub(r"[\s()+-]", "", visible):
        return True
    return not shared_domain and _same_name(row, visible)


def refresh_sources(skip_fetch: bool = False) -> dict:
    init_database(apply_second_source=False)
    if not skip_fetch:
        fehd_path = fetch_fehd_directory()
    else:
        fehd_path = ROOT / "data/raw/fehd_dog_restaurants_current.json"
    fehd = json.loads(fehd_path.read_text(encoding="utf-8"))
    if not isinstance(fehd, dict):
        raise ValueError("FEHD snapshot has no fetch metadata; fetch it again")
    vet_html, vet_fetched = _read(AFCD_VETS, skip_fetch=skip_fetch)
    pdf_links = re.findall(r'href="([^"#]*Vet_Clinics_List_\d+\.pdf)"', vet_html.decode("utf-8"))
    if not pdf_links:
        raise ValueError("AFCD vet directory no longer links its clinic list")
    vet_pdf_url = urljoin(AFCD_VETS, pdf_links[-1])
    pdf, _ = _read(vet_pdf_url, skip_fetch=skip_fetch)
    vet_path = CACHE / "afcd_current_vet_clinics.pdf"
    vet_path.write_bytes(pdf)
    clinics = parse_vet_pdf(vet_path)
    xml, sitemap_fetched = _read("https://gopaw.io/sitemap-venues.xml", skip_fetch=skip_fetch)
    gopaw = _gopaw_links(xml)
    dogdog_html, dogdog_fetched = _read("https://dogdoghk.com/malls/", skip_fetch=skip_fetch)
    dogdog_links = {urljoin("https://dogdoghk.com", unescape(x)) for x in re.findall(
        r'href=["\']([^"\']+)["\']', dogdog_html.decode("utf-8"))
        if re.fullmatch(r"/malls/[^/]+/?", urlsplit(urljoin("https://dogdoghk.com", unescape(x))).path)}
    if not dogdog_links:
        raise ValueError("DogDogHK directory no longer publishes its mall detail links")
    petcircle = _petcircle_links(skip_fetch)

    conn = get_connection()
    try:
        places = [dict(r) for r in conn.execute("SELECT * FROM places")]
        before = {r["licence_no"]: dict(r) for r in conn.execute("SELECT * FROM restaurants")}
        old_sources = {}
        for r in conn.execute("SELECT entity_type,entity_id,metadata_json FROM venue_sources"):
            old_sources[(r[0], r[1])] = json.loads(r[2])
    finally:
        conn.close()

    for row in places:
        if row["source_name"] == "petcircle":
            card = petcircle.get(row["place_id"].removeprefix("petcircle_"))
            if card and _phone(row.get("phone")) and _phone(row.get("phone")) == _phone(card.get("phone")):
                row["name_en"] = card.get("name_en")
                row["name_zh"] = card.get("name_zh") or card["name"]
    places_by_id = {row["place_id"]: row for row in places}

    providers = {}
    for row in places:
        if row["source_name"] == "mall_official":
            url = row["source_url"]
        elif row["source_name"] == "petcircle":
            url = petcircle.get(row["place_id"].removeprefix("petcircle_"), {}).get("website")
        else:
            url = row.get("website")
        host = urlsplit(url or "").hostname or ""
        if url and not any(x in host for x in ("gopaw.io", "petcircle-hk", "dogdoghk.com", "google.", "facebook.", "instagram.")):
            providers[row["place_id"]] = url
    unique_urls = sorted(set(providers.values()))

    def check(url):
        try:
            data, fetched = _read(url, skip_fetch=skip_fetch, timeout=12)
            return url, {"html": data.decode("utf-8", "replace"), "fetched_at_utc": fetched}
        except Exception as error:
            return url, {"error": type(error).__name__}

    print(f"Checking {len(unique_urls)} provider/policy pages; AFCD rows={len(clinics)}, PetCircle cards={len(petcircle)}", flush=True)
    with ThreadPoolExecutor(max_workers=5) as pool:
        checked = dict(pool.map(check, unique_urls))
    domain_phones = {}
    for row in places:
        url = providers.get(row["place_id"])
        if url:
            domain_phones.setdefault(urlsplit(url).netloc.lower(), set()).add(_phone(row.get("phone")))

    entries = []
    vet_matches, provider_matches, unresolved = [], [], []
    for row in places:
        pid = row["place_id"]
        previous = old_sources.get(("place", pid), {})
        original = previous.get("original_source_url") or row["source_url"]
        fallback, fetched = original, None
        if row["source_name"] == "GoPaw":
            vid = pid.rsplit("_", 1)[-1]
            fallback = gopaw.get(vid) or ""
            fetched = sitemap_fetched
        elif row["source_name"] == "petcircle":
            card = petcircle.get(pid.removeprefix("petcircle_"))
            if card and (_phone(card.get("phone")) == _phone(row.get("phone")) or _same_name(row, card["name"])):
                fallback, fetched = card["source_url"], card["fetched_at_utc"]
            else:
                fallback = ""
        elif row["source_name"] == "dogdoghk":
            fallback = original if original in dogdog_links else ""
            fetched = dogdog_fetched
        metadata = {
            "source_url": fallback or original,
            "source_name": row["source_name"], "origin_source_name": row["source_name"],
            "original_source_url": original, "evidence_tier": 3,
            "source_scope": "directory_listing", "source_detail_url": fallback or None,
            "source_note": "第三方地点目录；到访前请向场地确认地址及服务。",
            "source_last_verified_at": fetched,
        }
        if not fallback:
            unresolved.append({"place_id": pid, "reason": "not_found_in_current_published_directory"})
            metadata["source_note"] = "旧目录记录，当前详情页未能核实；请直接向场地确认。"
        provider_url = providers.get(pid)
        provider = checked.get(provider_url, {})
        shared = len(domain_phones.get(urlsplit(provider_url or "").netloc.lower(), set())) > 1
        verified_provider = bool(provider.get("html") and _provider_match(row, provider["html"], shared))
        if row["source_name"] == "mall_official":
            # A published policy remains Tier 2 even if temporarily unreachable.
            metadata.update(source_url=row["source_url"], source_name="mall_official", evidence_tier=2,
                            source_scope="mall_pet_policy", source_note="商场官网宠物政策；不代表场内所有店铺均允许宠物。",
                            source_detail_url=row["source_url"], source_last_verified_at=(provider.get("fetched_at_utc") if verified_provider else row["last_verified_at"]))
            if not provider.get("html"):
                metadata["source_note"] += " 本次未能读取，保留此前核实的官网链接。"
        elif verified_provider:
            metadata.update(source_url=provider_url, source_name="venue_official", evidence_tier=2,
                            source_scope="provider_contact", source_note="场地自有网页；请向该分店确认具体服务及开放时间。",
                            source_detail_url=provider_url, source_last_verified_at=provider["fetched_at_utc"])
            provider_matches.append(pid)
            metadata["service_source_url"] = fallback or None
        if row["place_type"] in {"vet", "dental", "emergency"}:
            clinic = match_vet(row, clinics)
            metadata["service_source_url"] = fallback or None
            if clinic:
                metadata.update(source_url=AFCD_VETS, source_name="AFCD", evidence_tier=1,
                                source_scope="clinic_identity_and_address",
                                source_note="渔护署公布的兽医诊所名单（非完整名册）；仅核对诊所身份及地址，未确认急诊、牙科或24小时服务。",
                                source_record_url=f"{vet_pdf_url}#page={clinic['page']}",
                                source_last_verified_at=vet_fetched)
                vet_matches.append({"place_id": pid, "clinic": clinic})
        metadata["source_status"] = "verified" if (
            fallback or verified_provider or metadata["source_name"] in {"AFCD", "mall_official"}
        ) else "unverified"
        entries.append({"entity_type": "place", "entity_id": pid, "identity_key": source_identity(row), "metadata": metadata})

    restaurants = []
    for raw in fehd["restaurants"]:
        licence = str(raw["licence"])
        district = normalize_district(raw["district_en"])
        row = {
            "restaurant_id": "fehd_" + licence, "licence_no": licence,
            "name_en": raw["shop_sign_en"] or None, "name_zh": raw["shop_sign_tc"] or raw["shop_sign_en"],
            "district": district, "address": raw["address_tc"] or raw["address_en"],
            "source_url": restaurant_source_url(district), "last_verified_at": datetime.fromisoformat(fehd["fetched_at_utc"]).astimezone(timezone(timedelta(hours=8))).date().isoformat(),
        }
        restaurants.append(row)
        entries.append({"entity_type": "restaurant", "entity_id": row["restaurant_id"], "identity_key": source_identity(row), "metadata": {
            "source_url": row["source_url"], "source_name": "FEHD", "evidence_tier": 1,
            "source_scope": "dog_entry_permission", "source_note": "食环署获准许狗只进入的食肆名单；请按该店守则到访。",
            "source_detail_url": raw.get("house_rule_tc") or raw.get("house_rule_en") or None,
            "source_last_verified_at": fehd["fetched_at_utc"],
        }})
    current = {r["licence_no"] for r in restaurants}
    unlisted = [r for licence, r in before.items() if licence not in current]
    report = {
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "restaurant_count": len(restaurants), "restaurant_district_count": len({r["district"] for r in restaurants}),
        "restaurants_added": len(current - set(before)), "restaurants_unlisted": len(unlisted),
        "place_count": len(places), "afcd_matched_place_rows": len(vet_matches),
        "afcd_matched_clinics": len({(m["clinic"]["page"], m["clinic"]["phone"], m["clinic"]["name"]) for m in vet_matches}),
        "provider_matched_place_rows": len(provider_matches),
        "place_sources": dict(Counter(e["metadata"]["source_name"] for e in entries if e["entity_type"] == "place")),
        "provider_pages_checked": len(checked), "provider_pages_unavailable": sum("error" in v for v in checked.values()),
        "afcd_clinics": clinics, "afcd_matches": vet_matches,
        "unlisted_restaurants": unlisted, "missing_directory_details": unresolved,
        "unresolved_places": [{"place_id": e["entity_id"], "reason": "no_verified_current_source"}
                              for e in entries if e["metadata"].get("source_status") == "unverified"],
        "entries": entries,
    }
    # A complete report is assembled before mutating the live data.
    conn = get_connection()
    try:
        with conn:
            conn.execute("UPDATE restaurants SET dog_permission = 0 WHERE restaurant_id LIKE 'fehd_%'")
            for row in restaurants:
                conn.execute("""INSERT INTO restaurants (restaurant_id,licence_no,name_en,name_zh,district,address,dog_permission,source_url,last_verified_at)
                    VALUES (:restaurant_id,:licence_no,:name_en,:name_zh,:district,:address,1,:source_url,:last_verified_at)
                    ON CONFLICT(restaurant_id) DO UPDATE SET name_en=excluded.name_en,name_zh=excluded.name_zh,
                    district=excluded.district,address=excluded.address,dog_permission=1,source_url=excluded.source_url,last_verified_at=excluded.last_verified_at""", row)
            for entry in entries:
                conn.execute("INSERT OR REPLACE INTO venue_sources VALUES (?,?,?,?)", (
                    entry["entity_type"], entry["entity_id"], entry["identity_key"], json.dumps(entry["metadata"], ensure_ascii=False)))
                if entry["entity_type"] == "place":
                    original_row = places_by_id[entry["entity_id"]]
                    conn.execute("UPDATE places SET source_url=?,name_en=?,name_zh=? WHERE place_id=?", (
                        entry["metadata"]["source_url"], original_row["name_en"], original_row["name_zh"], entry["entity_id"]))
    finally:
        conn.close()
    MANIFEST.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh government-first sources for all existing pet places")
    parser.add_argument("--skip-fetch", action="store_true")
    args = parser.parse_args()
    report = refresh_sources(skip_fetch=args.skip_fetch)
    print(json.dumps({k: v for k, v in report.items() if not isinstance(v, list)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
