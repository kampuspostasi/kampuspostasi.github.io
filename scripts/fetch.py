#!/usr/bin/env python3
"""Kampüs Postası - haber toplayıcı, tam metin çözücü ve editoryal yeniden yazım motoru.

RSS ve Google Haberler kaynaklarını tarar, Google yönlendirme linklerini çözer,
kaynak sayfadan tam metni çeker, SEO/clickbait kalabalığını temizler, cümle yapısını ve
ifade biçimini Kampüs Postası editoryal diline dönüştürerek çok paragraflı özgün haber
metni (body) üretir.
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "news.json"
MAX_ITEMS = 1500
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

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
    "ders saati", "cumhuriyet bayramı", "lise öğrencileri", "liselilere", "meslek lisesi",
    "veli", "öğretmen ataması", "bursluluk sınavı", "iokbs", "ilköğretim", "okul çevreleri",
    "kantin", "servis ücreti",
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

JUNK_PHRASES = [
    "tüm hakları saklıdır", "gizlilik politikası", "çerez politikası", "abone ol",
    "bizi takip edin", "haberin devamı", "google haberler", "whatsapp", "telegram",
    "instagram", "facebook", "twitter", "yorum yap", "okuma süresi", "editör:",
    "reklam", "sponsorlu", "ilgili haberler", "bunlar da ilginizi çekebilir",
    "kopyalanamaz", "izinsiz kullanılamaz", "aa / ", "iha / ", "dha / ",
    "paylaş yorumlar", "google algoritmasına", "tercih edilen kaynak", "aşağıdaki e-posta",
    "sonraki haber", "önceki haber", "yazı boyutu", "haberi paylaş",
]

# Editoryal yeniden yazım dönüşüm sözlüğü (kaynak cümle kalıplarını özgünleştirir)
REWRITE_MAP = [
    (r"\bgerçekleştirilecek\b", "yapılacak"),
    (r"\bgerçekleştirildi\b", "tamamlandı"),
    (r"\bgerçekleştirilen\b", "düzenlenen"),
    (r"\berişime açıldı\b", "yayımlandı"),
    (r"\berişime sunuldu\b", "açıklandı"),
    (r"\bbaşvuruda bulunmak isteyen adayların\b", "başvuracak öğrencilerin"),
    (r"\bbaşvuruda bulunacak adayların\b", "başvuru yapacak adayların"),
    (r"\bbaşvuruda bulunabilir\b", "başvurabilir"),
    (r"\bbaşvuru yapmayı düşünen adayların\b", "başvurmayı planlayan öğrencilerin"),
    (r"\böğrenim gören\b", "okuyan"),
    (r"\bönem taşıyor\b", "gerekiyor"),
    (r"\bönem taşımaktadır\b", "kritik görülüyor"),
    (r"\bdikkat çekiyor\b", "öne çıkıyor"),
    (r"\besas alınmalıdır\b", "dikkate alınmalı"),
    (r"\besas alınacak\b", "geçerli olacak"),
    (r"\bbelirtildi\b", "bildirildi"),
    (r"\bifade edildi\b", "aktarıldı"),
    (r"\bkaydedildi\b", "vurgulandı"),
    (r"\baçıklamalarda bulundu\b", "bilgi verdi"),
    (r"\bhayata geçirilen\b", "başlatılan"),
    (r"\bhayata geçirildi\b", "uygulamaya alındı"),
    (r"\binternet sitesi üzerinden\b", "web sayfasından"),
    (r"\bresmî internet sitesinde\b", "resmî sayfasında"),
    (r"\bresmi internet sitesinde\b", "resmî sayfasında"),
    (r"\bmerakla beklenen\b", "beklenen"),
    (r"\byoğun ilgi gören\b", "ilgi gören"),
    (r"\bgözler [a-zçğıöşü\s]+ çevrildi\.?", ""),
    (r"\bgeri sayım başladı!?\.?", ""),
]


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
    t = re.sub(r"^(son dakika\.{0,3}|flaş\.{0,3})\s*[:\-!]?\s*", "", t, flags=re.I)
    if " | " in t:
        parts = [p.strip() for p in t.split(" | ") if len(p.strip()) > 15]
        if parts:
            parts.sort(key=lambda p: sum(1 for c in p if c.isupper()) / max(1, len(p)))
            t = parts[0]
    if ":" in t:
        left, right = t.split(":", 1)
        upper_ratio = sum(1 for c in left if c.isupper()) / max(1, sum(1 for c in left if c.isalpha()))
        if len(right.strip()) >= 20 and (upper_ratio > 0.6 or "sorgulama ekranı" in tr_lower(left)):
            t = right.strip()
    alpha = [c for c in t if c.isalpha()]
    if alpha and sum(1 for c in alpha if c.isupper()) / len(alpha) > 0.75:
        t = tr_capitalize(tr_lower(t))
        for acr in ["KYK", "YKS", "ÖSYM", "YÖK", "KPSS", "ALES", "YDS", "DGS", "VGM", "TEV", "GSB", "TÜBİTAK", "İBB", "AÖF", "DHBT", "TDK"]:
            t = re.sub(rf"\b{tr_lower(acr)}\b", acr, t)
    if t.count("?") >= 2:
        first_q = t.split("?", 1)[0].strip() + "?"
        if len(first_q) >= 25:
            t = first_q
    t = re.sub(r"\s+", " ", t).strip(" -–|")
    if len(t) > 95:
        t = t[:92].rsplit(" ", 1)[0] + "…"
    return tr_capitalize(t)


def strip_page_chrome(s: str, title: str) -> str:
    """Kaynak sayfadan sızan 'Ana Sayfa > Kategori > Başlık etiket' kalıntılarını keser."""
    out = re.sub(r"^(Ana Sayfa|Kaynak Ekle|Anasayfa)\s+", "", s.strip(), flags=re.I)
    tl, ol = tr_lower(title.rstrip("…. ")), tr_lower(out)
    for key in (tl, tl[-35:], tl[:35]):
        if len(key) >= 18:
            pos = ol.find(key)
            if 0 <= pos < 260 and len(out) - (pos + len(key)) > 40:
                out = out[pos + len(key):].lstrip(" :!?.-–")
                break
    # Başta kalan "Başvurular Başladı burs " veya tek kelimelik etiketleri temizle
    out = re.sub(r"^(başvuruları?\s+başladı!?\.?\s+)?(burs|haber|eğitim|üniversite)\s+(?=[A-ZÇĞİÖŞÜ0-9])", "", out, flags=re.I)
    out = re.sub(r"^Binlerce Öğrencinin Beklediği [^\n.]{5,50} İçin\s+", "", out)
    return tr_capitalize(out.strip())


def paraphrase_sentence(s: str) -> str:
    out = s.strip()
    # Başlangıçtaki breadcrumb/kategori veya satır içi reklam kalıntılarını temizle
    out = re.sub(r"^Ana Sayfa\s+[^\n.]{5,90}\b(burs|haber|eğitim)\s+", "", out, flags=re.I)
    out = re.sub(r"^[A-ZÇĞİÖŞÜ][a-zçğıöşü]+\s+burs\s+başvuruları\s+(?=[A-ZÇĞİÖŞÜ])", "", out)
    # Tamamı büyük harf olan ara başlık cümlelerini ele
    alpha = [c for c in out if c.isalpha()]
    if alpha and sum(1 for c in alpha if c.isupper()) / len(alpha) > 0.7:
        return ""
    for pat, repl in REWRITE_MAP:
        out = re.sub(pat, repl, out, flags=re.I)
    out = re.sub(r"\s+", " ", out).strip()
    return tr_capitalize(out) if out else ""


def is_seo_spam_sentence(s: str) -> bool:
    sl = tr_lower(s)
    if len(s) < 35:
        return True
    if any(j in sl for j in JUNK_PHRASES):
        return True
    if s.count("?") >= 2:
        return True
    if s.count(",") >= 3 and any(w in sl for w in ["ne zaman", "sorgulama", "açıklandı mı", "kaç tl"]):
        return True
    if any(p in sl for p in [
        "haberimizde", "işte detaylar", "merak konusu oldu", "yoğun şekilde araştırılıyor",
        "aramaları hız kazandı", "gündemdeki yerini koruyor", "sorularının yanıtı",
        "detaylar haberimizde", "haberin detayları", "merak edilen tarih",
    ]):
        return True
    return False


def resolve_google_url(url: str) -> str:
    if "news.google.com" not in url or "/articles/" not in url:
        return url
    try:
        aid = url.split("/articles/")[1].split("?")[0]
        req = urllib.request.Request(f"https://news.google.com/articles/{aid}", headers={"User-Agent": UA})
        page = urllib.request.urlopen(req, timeout=8).read().decode("utf-8", errors="ignore")
        sg = re.search(r'data-n-a-sg="([^"]+)"', page)
        ts = re.search(r'data-n-a-ts="([^"]+)"', page)
        if not (sg and ts):
            return url
        payload = (
            f'[[["Fbv4je","[\\"garturlreq\\",[[\\"tr\\",\\"TR\\",[\\"FINANCE_TOP_INDICES\\",\\"WEB_TEST_1_0_0\\"],'
            f'null,null,1,1,\\"TR:tr\\",null,180,null,null,null,null,null,0,1],\\"tr\\",\\"TR\\",1,[2,4,8],1,1,'
            f'\\"655000234\\",0,0,null,0],\\"{aid}\\",{ts.group(1)},\\"{sg.group(1)}\\"]",null,"generic"]]]'
        )
        r2 = urllib.request.Request(
            "https://news.google.com/_/DotsSplashUi/data/batchexecute",
            data=urllib.parse.urlencode({"f.req": payload}).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8", "User-Agent": UA},
        )
        res = urllib.request.urlopen(r2, timeout=8).read().decode("utf-8", errors="ignore")
        m = re.search(r'\\"(https?://[^\\"]+)\\"', res)
        if m and "news.google.com" not in m.group(1):
            return m.group(1)
    except Exception:
        pass
    return url


def fetch_raw_article(url: str) -> tuple[str, list[str]]:
    """Haberin gerçek URL'sini çözer ve ham paragraf listesini döndürür."""
    real_url = resolve_google_url(url)
    paragraphs: list[str] = []
    try:
        req = urllib.request.Request(real_url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=10) as resp:
            real_url = resp.geturl() or real_url
            raw = resp.read().decode("utf-8", errors="ignore")
    except Exception:
        return real_url, paragraphs

    # 1. JSON-LD articleBody varsa en temiz tam metin oradadır
    for m in re.findall(r'"articleBody"\s*:\s*"((?:[^"\\]|\\.)*)"', raw):
        try:
            body_txt = html.unescape(json.loads('"' + m + '"'))
            body_txt = re.sub(r"<[^>]+>", " ", body_txt)
            for chunk in re.split(r"(?:\r?\n)+|(?<=[.!?])\s+(?=[A-ZÇĞİÖŞÜ0-9])", body_txt):
                c = re.sub(r"\s+", " ", chunk).strip()
                if len(c) >= 45:
                    paragraphs.append(c)
            if len(paragraphs) >= 3:
                return real_url, paragraphs
        except Exception:
            pass

    # 2. HTML <p> etiketlerinden çek
    cleaned_html = re.sub(r"<(script|style|nav|footer|header|aside|form|noscript)[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
    for p in re.findall(r"<p[^>]*>(.*?)</p>", cleaned_html, flags=re.S | re.I):
        txt = strip_html(p)
        if len(txt) >= 50:
            paragraphs.append(txt)

    return real_url, paragraphs


def build_editorial_article(title: str, raw_desc: str, raw_paragraphs: list[str], category: str, source: str) -> tuple[str, list[str]]:
    """Ham paragrafları ve açıklamayı temizler, yeniden yazar ve (summary, body_list) döndürür."""
    candidates: list[str] = []
    if raw_desc:
        for s in re.split(SENT_SPLIT, raw_desc):
            if len(s.strip()) >= 40:
                candidates.append(s.strip())
    for p in raw_paragraphs:
        for s in re.split(SENT_SPLIT, p):
            if len(s.strip()) >= 40:
                candidates.append(s.strip())

    # SEO spam, tekrar ve başlık kopyalarını ele
    seen_norms: list[str] = [norm_title(title)]
    clean_sentences: list[str] = []
    for s in candidates:
        if is_seo_spam_sentence(s):
            continue
        rw = paraphrase_sentence(strip_page_chrome(s, title))
        if len(rw) < 40:
            continue
        nt = norm_title(rw)
        if any(nt[:45] == sn[:45] or is_similar(rw, sn) for sn in seen_norms):
            continue
        seen_norms.append(nt)
        clean_sentences.append(rw)
        if len(clean_sentences) >= 14:
            break

    # Önce başlıktaki sorunun net cevabını seç, kalan cümleler "Ayrıntılar" olsun
    answer, clean_sentences = pick_answer(title, clean_sentences)

    # Cümleleri 2'şerli akıcı paragraflar halinde grupla
    body: list[str] = []
    for i in range(0, len(clean_sentences), 2):
        para = " ".join(clean_sentences[i:i + 2]).strip()
        if para:
            body.append(para)
        if len(body) >= 6:
            break

    # Eğer kaynak sayfa koruma/JS arkasındaysa ve hiç paragraf çıkmadıysa bağlamsal editoryal metin üret
    if not body:
        t_clean = title.rstrip(".?!")
        if category == "Burslar":
            body = [
                f"{t_clean} başlığıyla duyurulan burs programına ilişkin başvuru takvimi ve değerlendirme süreci öğrencilerin gündeminde yer alıyor.",
                "Adayların başvuru ekranı açıldığında öğrenim belgesi, transkript ve gelir durumunu gösteren belgeleri eksiksiz hazırlaması gerekiyor. Başvurular ilgili kurumun resmî başvuru sistemi üzerinden alınıyor.",
                f"Kontenjan, aylık ödeme tutarı ve kesin sonuç tarihleri için duyuruyu yayımlayan kurumun resmî açıklamaları takip edilmeli.",
            ]
        elif category == "KYK & Yurtlar":
            body = [
                f"{t_clean} konusuyla ilgili Gençlik ve Spor Bakanlığı (GSB) ile Kredi ve Yurtlar Genel Müdürlüğü süreci yürütülüyor.",
                "KYK burs, öğrenim kredisi ve yurt işlemlerinin tamamı e-Devlet kapısı üzerinden T.C. kimlik numarası ile sorgulanabiliyor. Taahhütname onayı ve kayıt takvimine dikkat edilmesi gerekiyor.",
                "Resmî duyurular yayımlandıkça başvuru ekranları ve sonuç belgeleri e-Devlet sisteminde güncelleniyor.",
            ]
        elif category == "Sınavlar":
            body = [
                f"{t_clean} gelişmesi, sınava hazırlanan adaylar ve tercih sürecindeki öğrenciler tarafından yakından izleniyor.",
                "Sınav giriş belgeleri, başvuru kılavuzları ve sonuç açıklamaları ÖSYM'nin Aday İşlemleri Sistemi (AİS) üzerinden erişime açılıyor.",
                "Adayların başvuru ve geç başvuru günlerini kaçırmamak için resmî sınav takvimini kontrol etmesi öneriliyor.",
            ]
        else:
            body = [
                f"{t_clean} başlıklı gelişme, yükseköğretim gündeminde öne çıkan konular arasında yer aldı.",
                "Üniversite öğrencilerini ve akademik birimleri ilgilendiren düzenlemenin uygulama detayları ilgili kurumların duyuru sayfalarında paylaşılıyor.",
            ]

    if not answer:
        answer = body[0] if body else title
        body = body[1:]
    return answer, body


SENT_SPLIT = r"(?<=[a-zçğıöşüA-ZÇĞİÖŞÜ)\"”'’][.!?])\s+"

MONTHS_RE = r"(ocak|şubat|mart|nisan|mayıs|haziran|temmuz|ağustos|eylül|ekim|kasım|aralık)"

# Soru tipi -> (başlıkta tetikleyici kelimeler, cevap cümlesinde aranan işaretler)
QUESTION_TYPES = [
    ("para", ["kaç tl", "ne kadar", "ücret", "miktar", "tutar", "kaç lira"],
     [r"\d[\d.]*\s*(tl|lira)\b", r"\btl\b", r"\blira\b"]),
    ("nasıl", ["nasıl", "nereden", "nerede", "sorgula", "hangi site", "ekranı"],
     [r"e-devlet", r"turkiye\.gov\.tr", r"\.gov\.tr", r"üzerinden", r"adresinden", r"sistem", r"ekranından", r"giriş yap"]),
    ("şart", ["şart", "kimler", "kimlere", "koşul", "gerekli belge", "hangi belge"],
     [r"şart", r"koşul", r"başvurabil", r"gerek", r"belge", r"öğrenciler"]),
    ("zaman", ["ne zaman", "tarih", "hangi gün", "saat kaç", "kaç gün", "takvim"],
     [MONTHS_RE, r"\d{1,2}[./]\d{1,2}", r"tarihleri arasında", r"henüz", r"bekleniyor", r"açıklanacak",
      r"hafta", r"gün içinde", r"\bsaat\b"]),
    ("durum", ["açıklandı mı", "başladı mı", "belli oldu mu", "yatırıldı mı", "çıktı mı", "uzatıldı mı"],
     [r"henüz", r"açıklanmadı", r"açıklandı", r"başladı", r"bekleniyor", r"paylaşmadı", r"duyurul", MONTHS_RE]),
]


def pick_answer(title: str, sentences: list[str]) -> tuple[str, list[str]]:
    """Başlıktaki soruya en doğrudan cevap veren 1-2 cümleyi seçer."""
    if not sentences:
        return "", sentences
    tl = tr_lower(title)
    qtypes = [q for q in QUESTION_TYPES if any(k in tl for k in q[1])]
    ttoks = title_tokens(title)

    def score(i: int, s: str) -> float:
        sl = tr_lower(s)
        sc = 0.0
        for _, _, markers in qtypes:
            sc += 3 * sum(1 for m in markers if re.search(m, sl))
        if re.search(r"\d", s):
            sc += 1
        sc += 0.6 * len(ttoks & title_tokens(s))
        sc -= 0.25 * i                      # erken cümleler genelde daha özdür
        if "?" in s:
            sc -= 4                         # soru cümlesi cevap değildir
        if len(s) > 280:
            sc -= 1.5
        return sc

    ranked = sorted(((score(i, s), i) for i, s in enumerate(sentences)), reverse=True)
    best_i = ranked[0][1]
    chosen = [best_i]
    # Cevap tek cümleyse ve kısaysa, tamamlayıcı en iyi ikinci cümleyi yanına ekle
    if len(sentences[best_i]) < 165 and len(ranked) > 1:
        if best_i + 1 < len(sentences) and "?" not in sentences[best_i + 1] and len(sentences[best_i + 1]) < 210:
            chosen.append(best_i + 1)
        elif ranked[1][0] > 0 and "?" not in sentences[ranked[1][1]] and len(sentences[ranked[1][1]]) < 210:
            chosen.append(ranked[1][1])
            chosen.sort()
    answer = " ".join(sentences[i] for i in chosen)
    rest = [s for i, s in enumerate(sentences) if i not in chosen]
    return answer, rest


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
            desc = ""
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


def enrich_item(e: dict) -> dict:
    """Tek bir haberi kaynak sayfasından çekip yeniden yazar."""
    real_url, raw_paras = fetch_raw_article(e["source_url"])
    if real_url and "news.google.com" not in real_url:
        e["source_url"] = real_url
    summary, body = build_editorial_article(
        e["title"],
        e.get("raw_desc", "") or e.get("summary", ""),
        raw_paras,
        e["category"],
        e["source"],
    )
    e["summary"] = summary
    e["body"] = body
    e["tags"] = e.get("tags") or extract_tags(e["title"], " ".join(body))
    e.pop("raw_desc", None)
    e.pop("clean_title", None)
    return e


def main() -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    raw_existing: list[dict] = json.loads(DATA_FILE.read_text("utf-8")) if DATA_FILE.exists() else []

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

    new_items: list[dict] = []
    now = datetime.now(timezone.utc).isoformat()
    for it in fetched:
        if it["source_url"] in seen_links or not is_candidate(it):
            continue
        ct = clean_title(it["raw_title"])
        if any(is_similar(ct, st) for st in seen_titles):
            continue
        seen_links.add(it["source_url"])
        seen_titles.append(ct)
        base = slugify(ct)
        slug = base if base not in used_slugs else f"{base}-{hashlib.md5(it['source_url'].encode()).hexdigest()[:6]}"
        used_slugs.add(slug)
        cat = rule_category(ct, it["raw_desc"])
        new_items.append({
            "slug": slug,
            "title": ct,
            "summary": "",
            "body": [],
            "category": cat,
            "tags": [],
            "source": it["source"],
            "source_url": it["source_url"],
            "raw_title": it["raw_title"],
            "raw_desc": it["raw_desc"],
            "published": it["published"],
            "added": now,
            "ai": False,
        })
    print(f"→ {len(new_items)} yeni tekil aday haber")

    # Tam metni olmayan mevcut haberleri + yeni haberleri paralel olarak çekip yeniden yaz
    to_enrich = new_items + [e for e in existing if not e.get("summary")]
    if to_enrich:
        print(f"→ {len(to_enrich)} haberin tam metni çekiliyor ve yeniden yazılıyor...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
            list(pool.map(enrich_item, to_enrich))

    all_items = existing + new_items
    all_items.sort(key=lambda e: e["published"], reverse=True)
    all_items = all_items[:MAX_ITEMS]
    DATA_FILE.write_text(json.dumps(all_items, ensure_ascii=False, indent=1), "utf-8")
    print(f"✔ {len(new_items)} yeni haber eklendi, tüm metinler hazır. Toplam: {len(all_items)}")


if __name__ == "__main__":
    main()
