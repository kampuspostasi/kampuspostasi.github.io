#!/usr/bin/env python3
"""Burs Radarı - günlük haber toplayıcı ve akıllı Türkçe editör.

Eğitim ve burs RSS kaynaklarını tarar, üniversite/burs ile ilgili haberleri seçer,
clickbait/SEO kalabalığını temizler, benzer haberleri tekilleştirir, etiket üretir
ve data/news.json'a yazar. GEMINI_API_KEY varsa ek olarak LLM özeti kullanır;
yoksa yerleşik Türkçe metin motoruyla tamamen anahtarsız çalışır.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "news.json"
MAX_ITEMS = 1500
UA = "Mozilla/5.0 (compatible; BursRadariBot/1.0; +https://github.com)"

FEEDS = [
    ("Hürriyet", "https://www.hurriyet.com.tr/rss/egitim"),
    ("Sabah", "https://www.sabah.com.tr/rss/egitim.xml"),
    ("CNN Türk", "https://www.cnnturk.com/feed/rss/egitim/news"),
    ("TRT Haber", "https://www.trthaber.com/egitim_articles.rss"),
    ("Sözcü", "https://www.sozcu.com.tr/feeds-rss-category-egitim"),
    ("Google Haberler", "https://news.google.com/rss/search?q=%22%C3%BCniversite%22+burs+ba%C5%9Fvuru+when:7d&hl=tr&gl=TR&ceid=TR:tr"),
    ("Google Haberler", "https://news.google.com/rss/search?q=VGM+burs+OR+TEV+burs+OR+T%C3%9CB%C4%B0TAK+burs+OR+%22burs+ba%C5%9Fvurular%C4%B1%22+%C3%BCniversite+when:14d&hl=tr&gl=TR&ceid=TR:tr"),
    ("Google Haberler", "https://news.google.com/rss/search?q=KYK+burs+OR+%22KYK+yurt%22+OR+%22%C3%B6%C4%9Frenim+kredisi%22+when:7d&hl=tr&gl=TR&ceid=TR:tr"),
    ("Google Haberler", "https://news.google.com/rss/search?q=erasmus+%C3%BCniversite+OR+%22yurt+d%C4%B1%C5%9F%C4%B1+burs%22+OR+fulbright+when:14d&hl=tr&gl=TR&ceid=TR:tr"),
    ("Google Haberler", "https://news.google.com/rss/search?q=%22%C3%BCniversite+%C3%B6%C4%9Frencilerine%22+staj+OR+%22Ulusal+Staj+Program%C4%B1%22+when:14d&hl=tr&gl=TR&ceid=TR:tr"),
]

CATEGORIES = ["Burslar", "KYK & Yurtlar", "Sınavlar", "Üniversiteler", "Yurt Dışı", "Kariyer & Staj"]

KEYWORDS = [
    "burs", "üniversite", "universite", "yks", "kyk", "yök", "ösym",
    "öğrenci yurdu", "yurt başvuru", "kpss", "ales", "yds", "yökdil", "dgs",
    "lisansüstü", "yüksek lisans", "doktora", "erasmus", "staj", "tercih",
    "akademisyen", "rektör", "kampüs", "harç", "tübitak", "vgm", "tev",
    "mezun", "fakülte", "lisans", "önlisans", "ön lisans", "üniversiteli",
    "yatay geçiş", "dikey geçiş", "akademik", "enstitü", "hazırlık", "öğrenim kredisi",
]

EXCLUDE = [
    "ara tatil", "karne", "ilkokul", "anaokulu", "okul öncesi", "lgs", "ortaokul",
    "ders saati", "cumhuriyet bayramı", "lise öğrencileri", "veli", "öğretmen ataması",
    "bursluluk sınavı", "iokbs", "ilköğretim", "okul çevreleri", "kantin", "servis ücreti",
]

CATEGORY_RULES = [
    ("KYK & Yurtlar", ["kyk", "yurt başvuru", "yurt sonuç", "öğrenim kredisi", "öğrenci yurdu", "gsb burs"]),
    ("Burslar", ["burs", "vgm", "tev ", "tübitak"]),
    ("Yurt Dışı", ["yurt dışı", "yurtdışı", "erasmus", "fulbright", "chevening", "daad", "uluslararası öğrenci"]),
    ("Kariyer & Staj", ["staj", "kariyer", "iş ilanı", "istihdam", "mezun"]),
    ("Sınavlar", ["yks", "ösym", "ales", "yds", "dgs", "yökdil", "sınav", "tercih", "kpss", "dhbt", "aöf"]),
    ("Üniversiteler", ["üniversite", "yök", "rektör", "fakülte", "akademisyen", "kampüs", "enstitü"]),
]

TAG_RULES = [
    ("kyk", ["kyk", "kredi ve yurtlar"]),
    ("burs", ["burs"]),
    ("vgm", ["vgm", "vakıflar genel müdürlüğü"]),
    ("yurt", ["kyk yurt", "öğrenci yurdu", "yurt başvuru", "yurt sonuç"]),
    ("yks", ["yks", "yükseköğretim kurumları sınavı"]),
    ("ösym", ["ösym"]),
    ("yök", ["yök", "yükseköğretim kurulu"]),
    ("kpss", ["kpss"]),
    ("dgs", ["dgs", "dikey geçiş"]),
    ("ales", ["ales"]),
    ("erasmus", ["erasmus"]),
    ("yurt-dışı", ["yurt dışı", "yurtdışı", "uluslararası"]),
    ("staj", ["staj"]),
    ("mezun", ["mezun"]),
    ("yatay-geçiş", ["yatay geçiş"]),
    ("yüksek-lisans", ["yüksek lisans", "lisansüstü", "doktora", "enstitü"]),
    ("tübitak", ["tübitak"]),
    ("aöf", ["aöf", "açıköğretim"]),
]

STOPWORDS = {
    "ve", "ile", "için", "bir", "bu", "da", "de", "mi", "mı", "mu", "mü",
    "ne", "zaman", "nasıl", "kaç", "gibi", "olan", "olarak", "son", "yeni",
    "sorgulama", "ekranı", "tarihi", "açıklandı", "açıklanacak", "belli", "oldu",
    "2026", "2027", "haber", "haberleri", "sonuçları", "sonucu", "başvuru", "başvuruları",
}


def tr_lower(s: str) -> str:
    return s.replace("İ", "i").replace("I", "ı").lower()


def tr_capitalize(s: str) -> str:
    if not s:
        return s
    first = s[0]
    first_up = "İ" if first == "i" else ("I" if first == "ı" else first.upper())
    return first_up + s[1:]


def strip_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def slugify(text: str) -> str:
    table = str.maketrans("çğıöşüâîû", "cgiosuaiu")
    s = tr_lower(text).translate(table)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:70].rstrip("-") or "haber"


def norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9çğıöşü]", "", tr_lower(t))[:80]


def title_tokens(t: str) -> set[str]:
    words = re.findall(r"[a-z0-9çğıöşü]{3,}", tr_lower(t))
    return {w[:5] for w in words if w not in STOPWORDS}


def is_similar(t1: str, t2: str) -> bool:
    s1, s2 = title_tokens(t1), title_tokens(t2)
    if not s1 or not s2:
        return False
    inter = len(s1 & s2)
    union = len(s1 | s2)
    if inter / union >= 0.5 or (inter >= 2 and len(s1) <= 3 and len(s2) <= 3):
        return True
    return inter >= 3 and inter / min(len(s1), len(s2)) >= 0.65


def clean_title(raw: str) -> str:
    t = raw.strip()
    # "Son dakika..." gibi girişleri kaldır
    t = re.sub(r"^(son dakika\.{0,3}|flaş\.{0,3})\s*[:\-!]?\s*", "", t, flags=re.I)
    # "|" ile ayrılmış çoklu SEO başlıklarında en anlamlı parçayı seç
    if " | " in t:
        parts = [p.strip() for p in t.split(" | ") if len(p.strip()) > 15]
        if parts:
            # Büyük harf oranı daha düşük olan parçayı tercih et
            parts.sort(key=lambda p: sum(1 for c in p if c.isupper()) / max(1, len(p)))
            t = parts[0]
    # "BÜYÜK HARF SEO BAŞLIĞI: Normal başlık" kalıbını temizle
    if ":" in t:
        left, right = t.split(":", 1)
        upper_ratio = sum(1 for c in left if c.isupper()) / max(1, sum(1 for c in left if c.isalpha()))
        if len(right.strip()) >= 20 and (upper_ratio > 0.6 or "sorgulama ekranı" in tr_lower(left)):
            t = right.strip()
    # Tamamı BÜYÜK HARF ise tümce düzenine çevir
    alpha = [c for c in t if c.isalpha()]
    if alpha and sum(1 for c in alpha if c.isupper()) / len(alpha) > 0.75:
        t = tr_capitalize(tr_lower(t))
        for acr in ["KYK", "YKS", "ÖSYM", "YÖK", "KPSS", "ALES", "YDS", "DGS", "VGM", "TEV", "GSB", "TÜBİTAK", "İBB", "AÖF", "DHBT"]:
            t = re.sub(rf"\b{tr_lower(acr)}\b", acr, t)
    # Birden fazla soru cümlesi arka arkaya dizilmişse ilkini tut
    if t.count("?") >= 2:
        first_q = t.split("?", 1)[0].strip() + "?"
        if len(first_q) >= 25:
            t = first_q
    t = re.sub(r"\s+", " ", t).strip(" -–|")
    if len(t) > 95:
        t = t[:92].rsplit(" ", 1)[0] + "…"
    return tr_capitalize(t)


def clean_summary(title: str, raw_desc: str, source: str, category: str) -> str:
    d = raw_desc.strip()
    # Google News açıklaması genelde başlığın tekrarı + kaynak adıdır; temizle
    if not d or norm_title(d)[:40] == norm_title(title)[:40] or len(d) < 45:
        return ""
    # SEO dolgu cümlelerini ayıkla
    sentences = re.split(r"(?<=[.!?])\s+", d)
    kept = []
    for s in sentences:
        sl = tr_lower(s)
        if s.count(",") >= 3 and ("ne zaman" in sl or "sorgulama" in sl):
            continue
        if any(p in sl for p in ["haberimizde", "işte detaylar", "merak konusu oldu", "yoğun şekilde araştırılıyor"]):
            continue
        kept.append(s.strip())
    out = " ".join(kept).strip() or d
    if len(out) > 360:
        out = out[:350].rsplit(" ", 1)[0] + "…"
    return out


def extract_tags(title: str, desc: str) -> list[str]:
    text = tr_lower(title + " " + desc)
    tags = []
    for tag, kws in TAG_RULES:
        if any(k in text for k in kws):
            tags.append(tag)
        if len(tags) == 4:
            break
    return tags or ["üniversite"]


def http_get(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def parse_date(s: str | None) -> datetime:
    if s:
        try:
            d = parsedate_to_datetime(s.strip())
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            return d.astimezone(timezone.utc)
        except Exception:
            pass
    return datetime.now(timezone.utc)


def parse_feed(source: str, raw: bytes) -> list[dict]:
    items = []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        print(f"  ! {source}: XML hatası {e}", file=sys.stderr)
        return items
    for it in root.iter("item"):
        title = strip_html(it.findtext("title") or "")
        link = (it.findtext("link") or it.findtext("guid") or "").strip()
        if not title or not link.startswith("http"):
            continue
        real_source = source
        src_el = it.find("source")
        if src_el is not None and (src_el.text or "").strip():
            real_source = src_el.text.strip()
        if " - " in title and source == "Google Haberler":
            t_main, t_src = title.rsplit(" - ", 1)
            if 2 <= len(t_src) <= 30:
                title = t_main.strip()
                real_source = t_src.strip()
        desc = strip_html(it.findtext("description") or "")
        if source == "Google Haberler":
            desc = ""  # Google RSS açıklaması sadece başlık tekrarı içerir
        items.append({
            "source": real_source,
            "source_url": link,
            "raw_title": title,
            "raw_desc": desc[:1200],
            "published": parse_date(it.findtext("pubDate")).isoformat(),
        })
    return items


def is_candidate(item: dict) -> bool:
    title = tr_lower(item["raw_title"])
    text = tr_lower(item["raw_title"] + " " + item["raw_desc"])
    if any(x in text for x in EXCLUDE) and "üniversite" not in title:
        return False
    return any(k in title for k in KEYWORDS) or sum(k in text for k in KEYWORDS) >= 2


def rule_category(title: str, desc: str = "") -> str:
    for text in (title, title + " " + desc):
        t = tr_lower(text)
        for cat, kws in CATEGORY_RULES:
            if any(k in t for k in kws):
                return cat
    return "Üniversiteler"


def gemini_process(batch: list[dict], api_key: str) -> dict[int, dict]:
    model = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    listing = "\n\n".join(
        f"[{i}] KAYNAK: {b['source']}\nBAŞLIK: {b['raw_title']}\nAÇIKLAMA: {b['raw_desc'][:700]}"
        for i, b in enumerate(batch)
    )
    prompt = f"""Sen "Burs Radarı" adlı, üniversite öğrencileri ve adayları için burs ve üniversite
haberleri yayınlayan bir Türkçe sitenin editörüsün. Aşağıdaki haberleri değerlendir.

Her haber için:
- relevant: Üniversite öğrencisi/adayı/mezunu için faydalıysa true. İlkokul/lise/MEB idari haberleri false.
- category: Şunlardan biri: {", ".join(CATEGORIES)}
- title: En fazla 90 karakter, clickbait olmayan, net ve bilgilendirici yeni bir başlık.
- summary: 2-4 cümlelik, tamamen KENDİ CÜMLELERİNLE yazılmış özgün özet.
- tags: 2-4 kısa etiket (küçük harf).

Sadece JSON dizi döndür: [{{"id":0,"relevant":true,"category":"...","title":"...","summary":"...","tags":["..."]}}]

HABERLER:
{listing}"""
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.4, "responseMimeType": "application/json"},
    }).encode()
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, data=body, headers={
                "Content-Type": "application/json", "x-goog-api-key": api_key})
            with urllib.request.urlopen(req, timeout=120) as r:
                resp = json.load(r)
            text = resp["candidates"][0]["content"]["parts"][0]["text"]
            arr = json.loads(text)
            return {int(o["id"]): o for o in arr if "id" in o}
        except Exception as e:
            print(f"  ! Gemini denemesi {attempt + 1} başarısız: {e}", file=sys.stderr)
            time.sleep(5 * (attempt + 1))
    return {}


def main() -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    raw_existing: list[dict] = json.loads(DATA_FILE.read_text("utf-8")) if DATA_FILE.exists() else []

    # Mevcut haberleri de yeni filtre ve başlık temizleyiciden geçir
    existing: list[dict] = []
    seen_links: set[str] = set()
    seen_titles: list[str] = []
    used_slugs: set[str] = set()

    for e in raw_existing:
        rt = e.get("raw_title", e["title"])
        if not is_candidate({"raw_title": rt, "raw_desc": e.get("summary", "")}):
            continue
        ct = clean_title(rt)
        if any(is_similar(ct, st) for st in seen_titles):
            continue
        e["title"] = ct
        e["category"] = rule_category(ct, e.get("summary", ""))
        e["summary"] = clean_summary(ct, e.get("summary", ""), e["source"], e["category"])
        e["tags"] = e.get("tags") or extract_tags(ct, e["summary"])
        seen_links.add(e["source_url"])
        seen_titles.append(ct)
        used_slugs.add(e["slug"])
        existing.append(e)

    fetched: list[dict] = []
    for source, url in FEEDS:
        try:
            items = parse_feed(source, http_get(url))
            print(f"✓ {source}: {len(items)} öğe")
            fetched.extend(items)
        except Exception as e:
            print(f"! {source} alınamadı: {e}", file=sys.stderr)

    new: list[dict] = []
    for it in fetched:
        if it["source_url"] in seen_links or not is_candidate(it):
            continue
        ct = clean_title(it["raw_title"])
        if any(is_similar(ct, st) for st in seen_titles):
            continue
        seen_links.add(it["source_url"])
        seen_titles.append(ct)
        it["clean_title"] = ct
        new.append(it)
    print(f"→ {len(new)} yeni tekil aday haber")

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    results: dict[int, dict] = {}
    if api_key and new:
        for start in range(0, len(new), 25):
            chunk = new[start:start + 25]
            res = gemini_process(chunk, api_key)
            for k, v in res.items():
                results[start + k] = v
            time.sleep(2)
        print(f"→ Gemini {len(results)}/{len(new)} haberi işledi")
    elif not api_key:
        print("✓ Yerleşik Türkçe metin motoru aktif (API anahtarı gerekmiyor)")

    now = datetime.now(timezone.utc).isoformat()
    added = []
    for idx, it in enumerate(new):
        r = results.get(idx)
        if r is not None and not r.get("relevant", True):
            continue
        if r is not None:
            title = clean_title(r.get("title") or it["clean_title"])
            category = r.get("category") if r.get("category") in CATEGORIES else rule_category(title, it["raw_desc"])
            summary = (r.get("summary") or "").strip() or clean_summary(title, it["raw_desc"], it["source"], category)
            tags = [str(t)[:30] for t in (r.get("tags") or [])][:4] or extract_tags(title, summary)
            ai = True
        else:
            title = it["clean_title"]
            category = rule_category(title, it["raw_desc"])
            summary = clean_summary(title, it["raw_desc"], it["source"], category)
            tags = extract_tags(title, summary)
            ai = False

        base = slugify(title)
        slug = base if base not in used_slugs else f"{base}-{hashlib.md5(it['source_url'].encode()).hexdigest()[:6]}"
        used_slugs.add(slug)
        added.append({
            "slug": slug, "title": title, "summary": summary, "category": category, "tags": tags,
            "source": it["source"], "source_url": it["source_url"], "raw_title": it["raw_title"],
            "published": it["published"], "added": now, "ai": ai,
        })

    all_items = existing + added
    all_items.sort(key=lambda e: e["published"], reverse=True)
    all_items = all_items[:MAX_ITEMS]
    DATA_FILE.write_text(json.dumps(all_items, ensure_ascii=False, indent=1), "utf-8")
    print(f"✔ {len(added)} yeni haber eklendi. Toplam: {len(all_items)}")


if __name__ == "__main__":
    main()
