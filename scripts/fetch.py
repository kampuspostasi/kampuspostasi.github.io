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
import ssl
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

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

FEEDS = [
    ("Anadolu Ajansı", "https://www.aa.com.tr/tr/rss/default?cat=egitim"),
    ("Hürriyet", "https://www.hurriyet.com.tr/rss/egitim"),
    ("Sabah", "https://www.sabah.com.tr/rss/egitim.xml"),
    ("CNN Türk", "https://www.cnnturk.com/feed/rss/egitim/news"),
    ("TRT Haber", "https://www.trthaber.com/egitim_articles.rss"),
    ("Sözcü", "https://www.sozcu.com.tr/feeds-rss-category-egitim"),
    ("Google Haberler", "https://news.google.com/rss/search?q=%22%C3%BCniversite%22+burs+ba%C5%9Fvuru+when:7d&hl=tr&gl=TR&ceid=TR:tr"),
    ("Google Haberler", "https://news.google.com/rss/search?q=VGM+burs+OR+TEV+burs+OR+T%C3%9CB%C4%B0TAK+burs+OR+%22burs+ba%C5%9Fvurular%C4%B1%22+%C3%BCniversite+when:14d&hl=tr&gl=TR&ceid=TR:tr"),
    ("Google Haberler", "https://news.google.com/rss/search?q=KYK+burs+OR+%22KYK+yurt%22+OR+%22%C3%B6%C4%9Frenim+kredisi%22+when:7d&hl=tr&gl=TR&ceid=TR:tr"),
    ("Google Haberler", "https://news.google.com/rss/search?q=erasmus+%C3%BCniversite+OR+%22yurt+d%C4%B1%C5%9F%C4%B1+burs%22+OR+fulbright+when:14d&hl=tr&gl=TR&ceid=TR:tr"),
    ("Google Haberler", "https://news.google.com/rss/search?q=%22%C3%BCniversite+%C3%B6%C4%9Frencilerine%22+staj+OR+%22Ulusal+Staj+Program%C4%B1%22+OR+%22%C4%B0%C5%9EKUR+Gen%C3%A7lik%22+when:14d&hl=tr&gl=TR&ceid=TR:tr"),
    ("Google Haberler", "https://news.google.com/rss/search?q=site:osym.gov.tr+OR+site:yok.gov.tr+OR+site:gsb.gov.tr+OR+site:tubitak.gov.tr+when:14d&hl=tr&gl=TR&ceid=TR:tr"),
]

# Doğrudan taranan birincil resmî kurum ve vakıf kaynakları (Ana Kaynaklar)
OFFICIAL_SOURCES = {
    "ÖSYM", "YÖK", "TÜBİTAK", "VGM", "TEV", "Türkiye Ulusal Ajansı", "Resmî Gazete", "GSB / KYK",
}

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
    "kantin", "servis ücreti", "ortaöğretim bursu", "şüpheli ölüm", "ölü bulundu",
    "hayatını kaybetti", "intihar", "cinayet", "tutuklandı", "gözaltına alındı",
    "bilişim personeli alım", "sözleşmeli personel", "anıldı", "hayvan kurtarma",
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
    "mevlana bulvarı", "çankaya / ankara", "merkezi başkanlığı", "aşağıdaki linkten",
    "aşağıdaki bağlantı", "aşağıda sunulan", "detaylı bilgi için:", "hakkında bilgi:",
    "detaylar için tıklayın", "tıklayınız", "kategorimizden inceleyebilirsiniz",
    "kategorisinden inceleyebilirsiniz", "kategorimizi takip edebilirsiniz",
    "okur temsilcimize ulaşabilirsiniz", "web sitemizde burslar sayfasından",
    "obigenç", "app store", "google play", "tev.org.tr/", "(% 10)",
    "sözlerini şöyle sürdürdü", "şunları kaydetti", "şöyle konuştu",
    "konusuyla ilgili gençlik ve spor bakanlığı",
    "duyurusu resmî olarak yayımlandı", "süreç adayların erişimine açıldı",
    "yükseköğretim gündeminde yürürlüğe girdi", "şer'iyye vekâleti",
    "vakıflarla ilgili konulara gelince", "vakfedenin şartı", "iyilik ve takvada",
    "medeniyetimizdeki vakıf anlayışı", "sosyal medya hesaplarını takip edebilirsiniz",
]

# Editoryal yeniden yazım dönüşüm sözlüğü (doğal ve akıcı, ne çok resmi ne lakayt ton)
REWRITE_MAP = [
    (r"\bgerçekleştirilmesi gerekmektedir\b", "yapılması gerekiyor"),
    (r"\bgerçekleştirilecek\b", "yapılacak"),
    (r"\bgerçekleştirildi\b", "tamamlandı"),
    (r"\bgerçekleştirilen\b", "düzenlenen"),
    (r"\berişime açılmıştır\b", "yayımlandı"),
    (r"\berişime açıldı\b", "yayımlandı"),
    (r"\berişime sunuldu\b", "açıklandı"),
    (r"\btamamlanmıştır\b", "tamamlandı"),
    (r"\bbaşlatılmıştır\b", "başladı"),
    (r"\byayımlanmıştır\b", "yayımlandı"),
    (r"\bduyurulmuştur\b", "duyuruldu"),
    (r"\bbelirtilmiştir\b", "belirtildi"),
    (r"\bbildirilmiştir\b", "bildirildi"),
    (r"\bsunulmaktadır\b", "sunuluyor"),
    (r"\bulaşılmaktadır\b", "ulaşılabiliyor"),
    (r"\bdüzenlenecektir\b", "düzenlenecek"),
    (r"\bbaşvuruda bulunmak isteyen adayların\b", "başvuracak öğrencilerin"),
    (r"\bbaşvuruda bulunacak adayların\b", "başvuru yapacak adayların"),
    (r"\bbaşvuruda bulunabilir\b", "başvurabilir"),
    (r"\bbaşvuru yapmayı düşünen adayların\b", "başvurmayı planlayan öğrencilerin"),
    (r"\böğrenim gören\b", "okuyan"),
    (r"\bönem taşıyor\b", "gerekiyor"),
    (r"\bönem taşımaktadır\b", "önemli görülüyor"),
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
    (r"\bardından gözler [a-zçğıöşüA-ZÇĞİÖŞÜ\s]+? çevrildi\b", "ardından sonuçların açıklanması bekleniyor"),
    (r"\bgözler [a-zçğıöşüA-ZÇĞİÖŞÜ\s]+? çevrildi\b", "süreç yakından takip ediliyor"),
    (r"\biçin geri sayım başladı!?\.?", "için bekleyiş sürüyor"),
    (r"\bgeri sayım başladı!?\.?", "bekleyiş sürüyor"),
]

ACRONYMS = ["KYK", "YKS", "ÖSYM", "YÖK", "KPSS", "ALES", "YDS", "YÖKDİL", "DGS", "VGM", "TEV", "GSB", "TÜBİTAK", "İBB", "AÖF", "DHBT", "TDK", "MEV", "İŞKUR", "DUS", "STS", "TUS", "EUS", "ÖZYES", "DAAD", "ARIS", "STAR", "KA131", "KA120", "KA210", "KA220", "KA240", "UNESCO", "KBÜ", "BŞEÜ", "GAÜN", "BANÜ", "BUÜ", "OMÜ", "GRÜ", "ODTÜ", "TENMAK", "SAYZEK", "ŞEKAV", "TADER", "NİVAK", "YUVA", "YKDS"]

SPECIFIC_ENTITIES = (
    "kyk", "vgm", "vakıflar", "yks", "ösym", "yök", "kpss", "ales", "yds", "yökdil",
    "dgs", "tus", "dus", "dhbt", "tübitak", "tev", "ibb", "işkur", "erasmus", "aöf",
    "tdk", "mev", "tenmak", "sayzek", "şekav", "tader", "nivak", "odtü", "istanbul",
)

DANGLING_ENDINGS = (
    "için", "ardından", "sonra", "önce", "göre", "ile", "olarak", "üzere", "birlikte",
    "beraber", "rağmen", "karşı", "doğru", "kadar", "eden", "olan", "yapan", "gelen",
    "alan", "veren", "belirten", "ifade eden", "işaret eden", "dikkat çeken", "vurgulayan",
    "söyleyen", "kaydeden", "aktaran", "arasında", "kapsamında", "tarafından", "üzerinden",
    "nedeniyle", "dolayı", "hakkında", "ilişkin", "yönelik", "ait", "dair", "ve", "veya",
    "ya da", "ancak", "fakat", "ama", "çünkü", "ki", "de", "da", "ise", "şöyle", "şunları",
    "dr", "prof", "doç", "sayın", "av", "öğr", "gör", "arş", "uzm", "no", "tc", "c",
    "başvur", "devam", "başta", "özellikle", "örneğin", "hazırlık",
)


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


def fix_acronyms(s: str) -> str:
    out = s
    for acr in ACRONYMS:
        out = re.sub(rf"(?<![.\w/]){tr_lower(acr)}(?![.\w])", acr, out, flags=re.I)
    out = re.sub(r"\be-devlet\b", "e-Devlet", out, flags=re.I)
    out = re.sub(r"(?<![.\w])(?:e-yds|eyds)(?![.\w])", "e-YDS", out, flags=re.I)
    out = re.sub(r"\berasmus\+", "Erasmus+", out, flags=re.I)
    return out


def clean_title(raw: str) -> str:
    t = html.unescape(raw.strip())
    # Yazım hataları ve bitişik yazımları düzelt
    t = re.sub(r"\bsonucları\b", "sonuçları", t, flags=re.I)
    t = re.sub(r"\bacıklandı\b", "açıklandı", t, flags=re.I)
    t = re.sub(r"\bacıklanacak\b|\baçıklancak\b", "açıklanacak", t, flags=re.I)
    t = re.sub(r"\b2026(YKS|KPSS|ALES|DGS|TUS|DUS)\b", r"2026 \1", t, flags=re.I)
    t = re.sub(r"\bYÖK['’]den\b", "YÖK'ten", t, flags=re.I)
    t = re.sub(r"/burs\b", "/ Burs", t)
    t = re.sub(r"\s+I\s+(?=[A-ZÇĞİÖŞÜ])", ": ", t)

    # Ulusal Ajans, VGM ve dış site kart kuyruklarını temizle
    t = re.sub(r"\s*-->\s*\d{2}\.\d{2}\.\d{4}.*$", "", t)
    t = re.sub(r"\s+-\s+https?://\S+.*$", "", t)
    t = re.sub(r"\s+-\s+Dünyanın En Büyük.*$", "", t, flags=re.I)
    t = re.sub(r"\s+İhlas Haber Ajansı$", "", t, flags=re.I)
    t = re.sub(r":\s*Herand Akademi ile.*$", "", t, flags=re.I)
    if "..." in t and "Vakıflar Genel Müdürlüğü" in t:
        parts = [p.strip() for p in t.split("...") if len(p.strip()) > 25]
        if len(parts) >= 2:
            t = f"Vakıflar Genel Müdürlüğü {parts[-1]}"
    t = re.sub(r"\bsona ermiştir\.?$", "Tamamlandı", t, flags=re.I)
    t = re.sub(r"\s+(?:Türkiye Ulusal Ajansı tarafından|Değerli Başvuru Sahipleri|Erasmus\+ programı ülke merkezli|Mesleki Eğitim Öğrenici ve Personel Hareketliliği için|2025 başvuru döneminde Erasmus\+).*$", "", t)
    t = re.sub(r"\(2026-YÖK-ykds\)\s*başvur$", "(2026-YÖK-YKDS) Başvuruları Başladı", t, flags=re.I)
    t = re.sub(r"\.{2,}|…", " ", t).strip()

    # Clickbait giriş hitaplarını temizle
    t = re.sub(r"^(?:son dakika|flaş|üniversitelilere müjde|üniversite öğrencilerine müjde|milyonlarca öğrencinin gözü gsb['’]de|gözler 2026 vgm burs başvuru sonuçlarında|burs arayan üniversiteliler için kritik gün|üniversite öğrencileri dikkat|hakkari['’]deki öğrenciler dikkat|hafta sonu sınav var mı)\s*[:\-!|.?]?\s*", "", t, flags=re.I)
    t = re.sub(r"^Sevgili\s+(?:TEV['’]liler|Gençler),\s*", "", t, flags=re.I)

    if " | " in t:
        parts = [p.strip() for p in t.split(" | ") if len(p.strip()) > 12]
        if parts:
            all_entities = [ent for ent in SPECIFIC_ENTITIES if any(ent in tr_lower(p) for p in parts)]
            scored = sorted(parts, key=lambda p: (
                sum(1 for ent in SPECIFIC_ENTITIES if ent in tr_lower(p)),
                -(sum(1 for c in p if c.isupper()) / max(1, len(p)))
            ), reverse=True)
            chosen = scored[0]
            if all_entities and not any(ent in tr_lower(chosen) for ent in all_entities):
                chosen = f"{all_entities[0].upper()} {tr_lower(chosen)}"
            t = chosen

    if ":" in t:
        left, right = [x.strip() for x in t.split(":", 1)]
        ll, rl = tr_lower(left), tr_lower(right)
        if re.search(r"\b(sorgulama ekranı|başvuru ekranı|sonuç ekranı|sonuç tarihi|son güncel durum)\b", ll):
            left_entities = [ent for ent in SPECIFIC_ENTITIES if ent in ll]
            if left_entities and not any(ent in rl for ent in left_entities):
                ent_label = left_entities[0].upper()
                t = f"2026-2027 {ent_label} Burs ve Sınav Süreci: {right}"
            elif rl in ("e-devlet ile hemen öğren", "işte detaylar"):
                t = re.sub(r"\bsorgulama ekranı\b", "ve Sorgulama Süreci", left, flags=re.I)
            else:
                t = right
        elif rl in ("e-devlet ile hemen öğren", "işte detaylar", "başvuru şartları ve detaylar"):
            t = left

    # Çoklu clickbait sorularını tek ve net bilgi başlığına dönüştür
    if "?" in t:
        q_parts = [p.strip() for p in t.split("?") if p.strip()]
        first_q = q_parts[0] + "?"
        if len(q_parts) >= 2 and not any(ent in tr_lower(first_q) for ent in SPECIFIC_ENTITIES) and any(ent in tr_lower(q_parts[1]) for ent in SPECIFIC_ENTITIES):
            t = q_parts[1].strip(" -–|.,!") + "?"
        elif len(first_q) >= 28:
            t = first_q

    # Soru kalıplarını doğal ve resmiyet dengeli bilgi başlıklarına dönüştür (kelime tekrarı yapmadan)
    if "?" in t:
        t = re.sub(r"(?:başvuru\s+)?(?:sonuçları\s+)?açıklandı mı,?\s*ne zaman açıklanacak(?:,\s*erken açıklanır mı)?\??", "başvuru sonuçları ve açıklanma takvimi", t, flags=re.I)
        t = re.sub(r"(?:başvuru\s+)?(?:sonuçları\s+)?ne zaman açıklanacak,?\s*açıklandı mı\??", "sonuçlarında son durum ve takvim", t, flags=re.I)
        t = re.sub(r"(?:başvuru\s+)?(?:sonuçları\s+)?açıklandı mı\s+ve\s+ne zaman ilan edilecek\??", "sonuçları ve ilan takvimi", t, flags=re.I)
        t = re.sub(r"(?:başvuru\s+)?(?:sonuçları\s+)?ne zaman,?\s*hangi gün açıklanacak\??", "sonuçlarının açıklanma takvimi", t, flags=re.I)
        t = re.sub(r"(?:başvuru\s+)?(?:sonuçları\s+)?ne zaman açıklanacak,?\s*hangi tarihte\??", "sonuçları ve sorgulama süreci", t, flags=re.I)
        t = re.sub(r"(?:başvuruları\s+)?başladı mı,?\s*ne zaman başlıyor\??", "başvuru takvimi ve şartları", t, flags=re.I)
        t = re.sub(r"\bson gün ne zaman,?\s*saat kaçta bitiyor\??", "son başvuru tarihi ve saati", t, flags=re.I)
        t = re.sub(r"(?:başvuru\s+)?(?:sonuçları\s+)?(?:nereden sorgulanır|nasıl(?:\s+ve\s+nereden)?\s+öğrenilir)\??", "sonuç sorgulama ekranı ve değerlendirme süreci", t, flags=re.I)
        t = re.sub(r"\bnasıl yapılır(?:,\s*şartları neler.*)?\??", "başvuru adımları ve şartları", t, flags=re.I)
        t = re.sub(r"\bne zaman açıklanacak(?:\s+2026)?\??|\bne zaman\s+2026\??", "takvimi ve son durum", t, flags=re.I)
        t = re.sub(r"\bne zaman yapılacak\??", "takvimi ve uygulama detayları", t, flags=re.I)
        t = re.sub(r"\bne zaman alınacak\??", "başvuru takvimi ve ücretleri", t, flags=re.I)
        t = re.sub(r"\bne zaman belli olacak\??", "takvimi ve değerlendirme süreci", t, flags=re.I)
        t = re.sub(r"\bbu hafta açıklanacak mı\??", "değerlendirme süreci ve beklenen takvim", t, flags=re.I)
        t = re.sub(r"\baçıklandı mı\??|\berişime açıldı mı\??|\bbelli oldu mu\??|\bbaşladı mı\??", "son durum ve sorgulama süreci", t, flags=re.I)
        t = re.sub(r"\bne kadar\??", "güncel tutarları ve detayları", t, flags=re.I)
        t = re.sub(r"\bhangi durumlarda kesilir\??", "kesilme nedenleri ve uygulama kuralları", t, flags=re.I)
        t = re.sub(r"\bnasıl bir yol izlenmeli\??", "başvuru ve hazırlık rehberi", t, flags=re.I)
        t = re.sub(r"\bnelere dikkat etmelisiniz\??", "dikkat edilmesi gereken kurallar", t, flags=re.I)
        t = re.sub(r"\bşartları neler\??", "başvuru şartları ve detayları", t, flags=re.I)
        t = re.sub(r"\bkimler başvurabilir\??", "başvuru şartları", t, flags=re.I)
        t = re.sub(r"\bders var mı yok mu\??", "eğitim-öğretim durumu", t, flags=re.I)
        t = re.sub(r"\bbugün ne sınavı var\??", "hafta sonu sınav uygulamaları", t, flags=re.I)
        t = re.sub(r"\botomatik mi veriliyor\??", "öğrenim kredisi uygulaması", t, flags=re.I)
        t = re.sub(r"\bhangi üniversiteye ayrıldı\??", "üniversitelere göre dağılımı", t, flags=re.I)

    # Kalan ünlem ve geri sayım kalıplarını sadeleştir
    t = re.sub(r"\biçin geri sayım(?: başladı)?!?\s*", "Değerlendirme Süreci: ", t, flags=re.I)
    t = re.sub(r"!\s+", ": ", t)

    alpha = [c for c in t if c.isalpha()]
    if alpha and sum(1 for c in alpha if c.isupper()) / len(alpha) > 0.60:
        t = tr_capitalize(tr_lower(t))

    t = fix_acronyms(t)
    t = re.sub(r"\?+\s*:", ":", t)
    t = re.sub(r":\s*:", ":", t)
    t = re.sub(r"\s+", " ", t).strip(" -–|.,!?")

    # Çok kısa/eksik kalan başlıkları tamamla
    short_expansions = {
        "brezilya burs programı": "Yükseköğretim Kurulu Brezilya Hükümeti Burs Programı Duyurusu",
        "kbü'den erasmus başarısı": "Karabük Üniversitesi'nden Erasmus+ Projelerinde Önemli Başarı",
        "ösym 3 sınav düzenledi": "ÖSYM Hafta Sonu Üç Ayrı Sınav Uygulamasını Tamamladı",
        "3 yeni fakülte ve 2 enstitü kuruldu": "Üniversitelerde 3 Yeni Fakülte ve 2 Enstitü Kurulmasına İlişkin Karar",
        "rabve vakfı burs": "Rabve Vakfı 2026-2027 Eğitim Dönemi Burs Başvuruları",
        "yks 19-20 haziran’da": "2027 YKS Sınav Takvimi Açıklandı: Sınav 19-20 Haziran'da Yapılacak",
        "yks 19-20 haziran'da": "2027 YKS Sınav Takvimi Açıklandı: Sınav 19-20 Haziran'da Yapılacak",
        "kpss ortaöğretim yapıldı": "2026 KPSS Ortaöğretim Sınavı Tamamlandı",
        "95 yılda on binlerce mezun": "TED Ankara Koleji'nde 95 Yılda On Binlerce Mezun Başarısı",
        "aftan yararlananlara yatay geçiş yolu": "Öğrenci Affından Yararlananlar İçin Yatay Geçiş Düzenlemesi",
    }
    if tr_lower(t) in short_expansions:
        t = short_expansions[tr_lower(t)]

    if len(t) > 110 and ":" in t:
        l_part, r_part = [x.strip() for x in t.split(":", 1)]
        if len(l_part) >= 35:
            t = l_part
    return tr_capitalize(t)


def clean_glued_text(text: str) -> str:
    """Metin içindeki HTML entity'leri, yapışık BÜYÜK HARF ara başlıkları ve nokta sonrası eksik boşlukları temizler."""
    t = html.unescape(text or "")
    # Emojileri ve madde işaretlerini temizle
    t = re.sub(r"[🟠🔴🟢🔵🟡🟣⚫⚪✓✔•▪▸►]+", " ", t)
    # Cümle ortasındaki BÜYÜK HARF parantez içi ara başlıkları temizle
    t = re.sub(r"\([A-ZÇĞİÖŞÜ\s]{8,45}\)", " ", t)
    # Ham URL'leri temiz domain adına dönüştür (örn. https://ais.osym.gov.tr -> ais.osym.gov.tr)
    t = re.sub(r"https?://(?:www\.)?([a-zA-Z0-9.\-]+)(?:/[^\s,.)]*)?", r"\1", t)
    # 1. Cümle arasına yapışmış BÜYÜK HARF ara başlıkları kes (örn. ".KÖKLÜ BİR GEÇMİŞUzun yıllar...") - rakamla başlayan tarihleri koru!
    t = re.sub(
        r"([.!?]|^)\s*[A-ZÇĞİÖŞÜ]{2,}[A-ZÇĞİÖŞÜ0-9\s,’'.,:\-]{4,75}?(?=[A-ZÇĞİÖŞÜ][a-zçğıöşü]{2,}|(?:KPSS|YKS|ÖSYM|YÖK|KYK|VGM|TÜBİTAK|TEV|İBB|GSB|ABD|AB)\s+[a-zçğıöşü]{2,})",
        r"\1 ",
        t,
    )
    # 2. YÖK vb. sayfalarda nokta konulmadan biten özet fiillerinden sonra nokta ekle
    t = re.sub(
        r"\b(bulundu|belirtti|söyledi|vurguladı|kaydetti|ifade etti|katıldı|açıkladı|bildirdi|duyurdu|verdi)\s+(?=[A-ZÇĞİÖŞÜ“\"])",
        r"\1. ",
        t,
    )
    t = re.sub(r":\.", ".", t)
    # 3. "Katılımcılar ve kurum temsilcileri:Toplantıya" veya "Okul Seçimi: Okul" gibi yapışık etiket başlıkları kes
    t = re.sub(r"(?:[.!?]|^)\s*[A-ZÇĞİÖŞÜ][a-zçğıöşüA-ZÇĞİÖŞÜ\s(),]{2,45}:\s*(?=[A-ZÇĞİÖŞÜ])", ". ", t)
    # 4. Küçük harften hemen sonra başlayan Büyük+küçük harf yapışıklıklarını ayır (örn. "sona eriyorVakıflar")
    t = re.sub(r"([a-zçğıöşü])([A-ZÇĞİÖŞÜ][a-zçğıöşü]{2,})", r"\1. \2", t)
    # 5. Nokta/soru/ünlem işaretinden sonra unutulmuş boşlukları ekle
    t = re.sub(r"([a-zçğıöşü0-9”\"')])([.!?])([A-ZÇĞİÖŞÜ“\"])", r"\1\2 \3", t)
    return re.sub(r"\s+", " ", t).strip()


def split_sentences(text: str) -> list[str]:
    """Kısaltmaları (Prof., Dr., T.C.) ve sıra sayılarını (2. Dönem) bölmeden cümlelere ayırır."""
    t = clean_glued_text(text)
    if not t:
        return []
    # Kısaltmaları koru
    t = re.sub(r"\bT\.C\.", "T∯C∯", t)
    t = re.sub(
        r"\b(Prof|Doç|Dr|Öğr|Gör|Arş|Uzm|Av|Müh|Yrd|Bşk|Gen|Md|No|Tel|Cad|Sok|Mah|Bul|vb|vs|bkz|örn|yak|ort)\.",
        r"\1∯",
        t,
        flags=re.I,
    )
    # Sıra sayılarını koru (örn. 2. Dönem, 11. Avrasya, 1. sınıf)
    t = re.sub(
        r"\b(\d{1,2})\.(?=\s*(?:Dönem|dönem|Sınıf|sınıf|Basamak|basamak|Oturum|oturum|Çağrı|çağrı|Yıl|yıl|Grup|grup|Kademe|kademe|Derece|derece|Bölge|bölge|Aşama|aşama|Adım|adım|Kura|kura|Tercih|tercih|Avrasya|Uluslararası|Ulusal|sırada|sıraya|kez|gün|hafta|ay))",
        r"\1∯",
        t,
    )
    parts = re.split(r"(?<=[.!?”\"'])\s+(?=[A-ZÇĞİÖŞÜ0-9“\"])", t)
    return [p.replace("∯", ".").strip() for p in parts if p.strip()]


def strip_page_chrome(s: str, title: str) -> str:
    """Kaynak sayfadan sızan 'Ana Sayfa > Kategori > Başlık etiket' kalıntılarını ve kesik başlangıçları onarır."""
    out = clean_glued_text(s)
    out = re.sub(r"^.*?\b(Ana Sayfa|Kaynak Ekle|Anasayfa)\b\s*(?:Eğitim\s*(?:&\s*Sağlık)?\s*)?", "", out, flags=re.I)
    out = re.sub(r"^Yayınlanma:\s*\d{1,2}[./]\d{1,2}[./]\d{4}\s*\d{1,2}:\d{2}\s*", "", out, flags=re.I)
    out = re.sub(r"^[a-zçğıöşüA-ZÇĞİÖŞÜ\s]+resmî internet sayfasında yayımlanan duyuru:.*?(?=[A-ZÇĞİÖŞÜ0-9]|$)", "", out)
    out = re.sub(r"\s*-->\s*\d{2}\.\d{2}\.\d{4}.*$", "", out)
    tl, ol = tr_lower(title.rstrip("…. ")), tr_lower(out)
    if len(tl) >= 22:
        pos = ol.find(tl)
        end = pos + len(tl)
        if 0 <= pos < 180 and len(out) - end > 45 and (end >= len(out) or not out[end].isalnum()):
            out = out[end:].lstrip(" :!?.-–—•")
    out = re.sub(r"^[\-–—•'\"”]+\s*", "", out)
    out = re.sub(r"\s+[\-–—•]+\s*(?=[A-ZÇĞİÖŞÜ“\"0-9])", ". ", out)
    # Başta kalan kesik ek veya tek kelimelik etiketleri temizle (DİKKAT: büyük/küçük harf duyarlı!)
    out = re.sub(r"^(Nde|İnde|Ünde|Dan|Den|Nin|Nın|E Yenilik [^\n.]{5,55}|TS Diş [^\n.]{5,55}|Av Günü [^\n.]{5,50}|İtiminde [^\n.]{5,50}|Li [^\n.]{5,45}!)\s*", "", out)
    out = re.sub(r"^(?:[Bb]aşvuruları?\s+[Bb]aşladı!?\.?\s+)?(?:Burs|BURS|Haber|HABER|Eğitim|EĞİTİM|Üniversite|ÜNİVERSİTE|Başvuruları)\s+(?=[A-ZÇĞİÖŞÜ0-9])", "", out)
    out = re.sub(r"^(?:Temel Soru\s+)?Kitapçıkları ve Cevap Anahtarları Yayımlandı\s+", "", out)
    out = re.sub(r"^Öğrencilerine Karşılıksız Burslar\s+(?=[A-ZÇĞİÖŞÜ])", "", out)
    out = re.sub(r"^Binlerce Öğrencinin Beklediği [^\n.]{5,50} İçin\s+", "", out)
    out = re.sub(r"^Türkiye['’]nin dijital üniversitesinde \d+ bin kişi ücretsiz eğitim alacak\s+", "", out)
    out = re.sub(r"^Tazelenme Üniversitesi[^\n.]{5,60}talebi\s+", "", out)
    out = re.sub(r"\bÜniversitede bilgi aktarma dönemi değişiyor\s+", "", out)
    # Başta duran YÖK tırnak içi spotlarını temizle
    out = re.sub(r"^(?:Yükseköğretim Kurulu Başkanı (?:Erol\s+)?Özvar:\s*)?(?:[“\"][^”\"]+[”\"]\s*)+(?=[A-ZÇĞİÖŞÜ])", "", out)

    # Önceki kesimlerden dolayı başı eksik kalmış cümleleri tam öznesiyle onar
    out = re.sub(r"^İşte,?\s+o\s+detaylar\.?\s*", "", out, flags=re.I)
    out = re.sub(r"^Ekim\s+2026\s+tarihleri\s+arasında\b", "20-31 Ekim 2026 tarihleri arasında", out)
    out = re.sub(r"^Yüksek\s+[Ll]isans\s+öğrencileri\s+için\b", "Lisansüstü burs ödemeleri yüksek lisans öğrencileri için", out)
    out = re.sub(r"^Giderlerine\s+katkı\s+sağlamak\b", "Eğitim giderlerine katkı sağlamak", out)
    out = re.sub(r"^[Kk]imlik\s+(numaralar[ıi]|numaras[ıi]|şifre)", r"Adaylar, T.C. kimlik \1", out)
    out = re.sub(r"^Öğrencilerinin\b", "Üniversite öğrencilerinin", out)
    out = re.sub(r"^Öğrencilerine\b", "Üniversite öğrencilerine", out)
    out = re.sub(r"^Öğrencileri\s+için\b", "Üniversite öğrencileri için", out)
    out = re.sub(r"^Eğitiminde\b", "Üniversite eğitiminde", out)
    out = re.sub(r"^Eğitimi\s+(sırasında|başka|için)\b", r"Üniversite eğitimi \1", out)
    out = re.sub(r"^Dönemi\s+boyunca\b", "Eğitim öğretim dönemi boyunca", out)
    out = re.sub(r"^Ödemeleri\b", "Burs ödemeleri", out)
    out = re.sub(r"^Verilirken\b", "Burs verilirken", out)
    out = re.sub(r"^Arayan\s+üniversite\b", "Burs arayan üniversite", out)
    out = re.sub(r"^Başvuruları\s+her\s+yıl\b", "Burs başvuruları her yıl", out)
    out = re.sub(r"^Başvuruları,\s+", "Burs başvuruları, ", out)
    out = re.sub(r"^Değerlendirmeleri\s+tamamlandığında\b", "Başvuru değerlendirmeleri tamamlandığında", out)
    out = re.sub(r"^Başvurusu\s+(yapmak|değerlendirme)\b", r"Burs başvurusu \1", out)
    out = re.sub(r"^Başvuruları\s+(\d{1,2}\s+Ocak)", r"Sınav başvuruları \1", out)
    out = re.sub(r"^Ve\s+öğrenim\s+kredisi\b", "KYK burs ve öğrenim kredisi", out)
    out = re.sub(r"^Ve\s+günlük\s+yaşam\b", "Eğitim ve günlük yaşam", out)
    out = re.sub(r"^Dönem\s+(tercih|yerleştirme|kontenjan|sınav)\b", r"İlgili dönem \1", out)
    out = re.sub(r"^döneminde\s+aşağıdaki\b", "Yeni başvuru döneminde ilgili", out)
    return tr_capitalize(out.strip(" -–—•"))


def ensure_sentence_end(s: str) -> str:
    """Cümle sonundaki yarım kalmış ifadeleri onarır ve tek nokta ile bitmesini sağlar."""
    out = re.sub(r"\.{2,}|…", ".", s.strip(" -–—•"))
    if "“" not in out and out.endswith("”"):
        out = out[:-1].rstrip()
    if out.count('"') == 1 and out.endswith('"'):
        out = out[:-1].rstrip()
    out = re.sub(r"\bbaşvurularının ardından\.?$", "başvurularının ardından değerlendirme süreci devam ediyor.", out, flags=re.I)
    out = re.sub(r"\bsonuçları için\.?$", "sonuçları için bekleyiş sürüyor.", out, flags=re.I)
    out = re.sub(r",\s*sözlerini şöyle sürdürdü:?\.?$", " açıklamasında bulundu.", out, flags=re.I)
    out = re.sub(r"\bişaret eden\.?$", "işaret etti.", out, flags=re.I)
    if out and out[-1] not in ".!?”\"":
        out += "."
    out = re.sub(r"\.+", ".", out)
    return tr_capitalize(out)


def is_complete_sentence(s: str) -> bool:
    """Cümlenin anlamlı, başı ve sonu tam bir Türkçe cümle olup olmadığını denetler."""
    txt = s.strip()
    if len(txt) < 45 or len(txt) > 460:
        return False
    if "?" in txt or "-->" in txt or "..." in txt or "…" in txt:
        return False
    if txt.startswith(("'", "’", "”", "“", "\"", ")", "E Yenilik", "TS Diş", "Av Günü", "İtiminde", "Li ", "Nde ", "Den ", "Nin ", "Dönem'", "Dönem,", "Dönem ", "Sınavlarının ", "Ve ", "1 doktor", "Yönetmeliği hükümlerine")):
        return False
    if txt.endswith(":"):
        return False
    # Kısaltma veya sıra sayısı ile biten yarım cümleleri reddet (örn. "Prof.", "Dr.", "T.C.", "2.")
    if re.search(r"(?:\b(?:Prof|Doç|Dr|Öğr|Gör|Arş|Uzm|Av|Sayın|T\.C)|\b\d{1,2})\.$", txt, flags=re.I):
        return False
    # Tablo veya üst üste binmiş başlık kalıntısı kontrolü
    if len(re.findall(r"\d[\d.]*\s*TL", txt, flags=re.I)) >= 3 and "," not in txt:
        return False
    if "•" in txt or "Not: Bu tablo" in txt:
        return False
    words = re.findall(r"[a-zçğıöşüA-ZÇĞİÖŞÜ0-9]+", tr_lower(txt))
    if not words or len(words) < 6:
        return False
    last_w = words[-1]
    last_two = f"{words[-2]} {words[-1]}" if len(words) >= 2 else last_w
    if last_w in DANGLING_ENDINGS or last_two in DANGLING_ENDINGS:
        return False
    return True


def paraphrase_sentence(s: str) -> str:
    out = s.strip(" -–—•")
    out = re.sub(r"^Ana Sayfa\s+[^\n.]{5,90}\b(burs|haber|eğitim)\s+", "", out, flags=re.I)
    out = re.sub(r"^[A-ZÇĞİÖŞÜ][a-zçğıöşü]+\s+burs\s+başvuruları\s+(?=[A-ZÇĞİÖŞÜ])", "", out)
    alpha = [c for c in out if c.isalpha()]
    if alpha and sum(1 for c in alpha if c.isupper()) / len(alpha) > 0.65:
        return ""
    for pat, repl in REWRITE_MAP:
        out = re.sub(pat, repl, out, flags=re.I)
    out = fix_acronyms(out)
    out = re.sub(r"\s+", " ", out).strip(" -–—•")
    if not out:
        return ""
    out = ensure_sentence_end(out)
    return out if is_complete_sentence(out) else ""


def is_seo_spam_sentence(s: str) -> bool:
    sl = tr_lower(s.strip())
    if len(sl) < 42:
        return True
    if "?" in sl or "-->" in sl or "..." in sl or "…" in sl:
        return True
    if sl.startswith(("peki", "işte ", "işte,", "ancak ne zaman", "uygulama el kitabı", "' başlıklı")):
        return True
    if "resmî internet sayfasında yayımlanan duyuru:" in sl:
        return True
    if any(j in sl for j in JUNK_PHRASES):
        return True
    if any(p in sl for p in [
        "haberimizde", "işte detaylar", "merak konusu oldu", "yoğun şekilde araştırılıyor",
        "aramaları hız kazandı", "gündemdeki yerini koruyor", "sorularının yanıtı",
        "detaylar haberimizde", "haberin detayları", "merak edilen tarih",
        "şu adımlar izlenecek:", "temel hususlar şunlar:", "detaylar şunlardır:",
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
        with urllib.request.urlopen(req, timeout=10, context=SSL_CTX) as resp:
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
        if len(txt) >= 45:
            paragraphs.append(txt)

    # 3. Resmî kurum sayfalarında (ÖSYM, VGM, YÖK vb.) metin bazen <div> veya <li> içindedir
    if len(paragraphs) < 2:
        for blk in re.findall(r"<(?:div|li)[^>]*>(.*?)</(?:div|li)>", cleaned_html, flags=re.S | re.I):
            if "<div" in blk.lower():
                continue
            txt = strip_html(blk)
            if 50 <= len(txt) <= 650 and txt not in paragraphs:
                paragraphs.append(txt)

    return real_url, paragraphs


def official_context_paragraphs(title: str, source: str, category: str) -> list[str]:
    """Doğrudan ana kaynaktan (ÖSYM, YÖK, TÜBİTAK, VGM, TEV vb.) alınan veya kısa kalan duyurular için dengeli ve anlaşılır haber metni üretir."""
    tl = tr_lower(title)
    if category == "KYK & Yurtlar" or "kyk" in tl:
        return [
            "Gençlik ve Spor Bakanlığı (GSB) Kredi ve Yurtlar Genel Müdürlüğü tarafından yürütülen burs, öğrenim kredisi ve yurt süreçleri e-Devlet kapısı üzerinden takip ediliyor. Başvuruda bulunan öğrencilerin beyan ettiği ekonomik, sosyal ve akademik bilgiler kamu kurumları aracılığıyla doğrulanıyor.",
            "Sonuçların ilan edilmesinin ardından burs veya öğrenim kredisi hakkı kazanan öğrencilerin, belirtilen süre içinde e-Devlet üzerinden taahhütname onayını tamamlaması gerekiyor. Ödemeler, öğrencilerin T.C. kimlik numaralarının son hanesine göre belirlenen günlerde Ziraat Bankası hesaplarına yatırılıyor.",
        ]
    if source == "ÖSYM" or category == "Sınavlar":
        return [
            "Ölçme, Seçme ve Yerleştirme Merkezi (ÖSYM) tarafından yayımlanan duyuruyla birlikte ilgili sınav ve yerleştirme takvimindeki güncel uygulama adımları netleşti. Adaylar, T.C. kimlik numaraları ve şifreleriyle ÖSYM Aday İşlemleri Sistemi (ais.osym.gov.tr) veya Sonuç Açıklama Sistemi (sonuc.osym.gov.tr) üzerinden işlemlerini doğrudan yapabiliyor.",
            "Başvuru tarihleri, sınav giriş belgeleri ve kılavuzda yer alan kuralların hak kaybı yaşanmaması için resmî duyuru metninden dikkatle takip edilmesi öneriliyor. Sürece ilişkin tüm güncellemeler ÖSYM'nin resmî internet sayfası üzerinden adayların bilgisine sunuluyor.",
        ]
    if source == "YÖK":
        return [
            "Yükseköğretim Kurulu (YÖK) tarafından paylaşılan açıklama, üniversite öğrencileri ve akademik birimler için yürürlüğe giren yeni uygulamaları kapsıyor. YÖK'ün yükseköğretim kurumlarına ilettiği kararlar doğrultusunda üniversite yönetimleri ve öğrenci işleri birimleri ilgili takvimi yürütecek.",
            "Düzenlemenin ayrıntılarına ve uygulama esaslarına Yükseköğretim Kurulu'nun resmî internet sayfası üzerinden ulaşılabiliyor. Öğrencilerin kendi üniversitelerinin duyuru ekranlarını da eş zamanlı olarak kontrol etmesi gerekiyor.",
        ]
    if source == "TÜBİTAK" or "tübitak" in tl:
        return [
            "TÜBİTAK Bilim İnsanı Destek Programları Başkanlığı (BİDEB) ve ilgili araştırma grupları tarafından yeni dönem çağrı ve destek duyurusu yayımlandı. Lisans, yüksek lisans ve doktora öğrencileri ile araştırmacıları kapsayan programlara başvurular TÜBİTAK Yönetim Bilgi Sistemi (tybs.tubitak.gov.tr) üzerinden çevrim içi olarak alınıyor.",
            "Başvuru yapacak adayların son başvuru tarihinden önce Araştırmacı Bilgi Sistemi (ARBİS) kayıtlarını güncellemesi ve çağrı metninde istenen belgeleri eksiksiz yüklemesi gerekiyor.",
        ]
    if source in ("VGM", "TEV") or category == "Burslar":
        return [
            "Üniversite öğrencilerine yönelik burs ve eğitim desteği sürecinde başvuru ile değerlendirme takvimi kurumun resmî duyuru ekranı üzerinden yürütülüyor. Adayların başvuru aşamasında öğrenim durumu, başarı şartı ve gelir beyanı bilgilerini eksiksiz ve doğru şekilde girmesi gerekiyor.",
            "Değerlendirme işlemlerinin tamamlanmasının ardından sonuç açıklamaları, belge teslimi ve aylık ödeme takvimi ilgili kurumun resmî internet sayfası üzerinden duyuruluyor.",
        ]
    if source == "Türkiye Ulusal Ajansı" or category == "Yurt Dışı":
        return [
            "Türkiye Ulusal Ajansı ve yükseköğretim kurumları tarafından yürütülen uluslararası değişim programları, öğrencilere yurt dışında eğitim ve staj deneyimi kazanma imkânı sunuyor. Erasmus+ ve ikili iş birliği programlarına ilişkin güncel uygulama kuralları resmî rehberler doğrultusunda belirleniyor.",
            "Yurt dışı öğrenim ve staj hareketliliğine katılacak adayların üniversitelerindeki uluslararası ilişkiler ofisleri ile Türkiye Ulusal Ajansı duyurularını düzenli olarak takip etmesi gerekiyor.",
        ]
    if category == "Kariyer & Staj" or "staj" in tl or "işkur" in tl:
        return [
            "Üniversite öğrencilerinin eğitim süreçleri devam ederken mesleki deneyim kazanmalarını ve iş gücü piyasasına hazırlanmalarını amaçlayan programlar kamu ve özel sektör iş birliğiyle yürütülüyor.",
            "Adayların başvuru şartlarını, kontenjan dağılımlarını ve son başvuru tarihlerini ilgili kurumların resmî başvuru ekranları üzerinden kontrol ederek işlemlerini tamamlaması gerekiyor.",
        ]
    if source == "Resmî Gazete":
        return [
            "Resmî Gazete'de yayımlanan yeni düzenleme bugün itibarıyla yürürlüğe girdi. Üniversitelerin eğitim-öğretim, sınav ve araştırma merkezlerini ilgilendiren yönetmelik hükümleri ilgili yükseköğretim kurumları tarafından uygulanacak.",
            "Öğrenciler ve akademik personel, yönetmelik kapsamındaki uygulama esaslarını üniversitelerinin resmî duyuru sayfalarından inceleyebiliyor.",
        ]
    return [
        "Yükseköğretim gündeminde yer alan çalışmanın uygulama adımları ve takvimi ilgili kurumların resmî internet sayfaları üzerinden paylaşıldı. Üniversite öğrencileri ve akademik paydaşlar sürece ilişkin ayrıntıları kurum duyurularından takip edebiliyor.",
        "Başvuru, kayıt ve uygulama takviminde olası güncellemeler için ilgili üniversite ve kurumların resmî açıklamalarının dikkate alınması öneriliyor.",
    ]


def build_editorial_article(title: str, raw_desc: str, raw_paragraphs: list[str], category: str, source: str) -> tuple[str, list[str]]:
    """Ham paragrafları ve açıklamayı temizler, yeniden yazar ve (summary, body_list) döndürür."""
    candidates: list[str] = []
    for block in ([raw_desc] if raw_desc else []) + raw_paragraphs:
        sub_blocks = re.split(r"\s+[\-–—•]\s+(?=[A-ZÇĞİÖŞÜ“\"0-9])", block or "")
        for sb in sub_blocks:
            for s in split_sentences(sb):
                if len(s.strip()) >= 42:
                    candidates.append(s.strip())

    # SEO spam, tekrar ve başlık kopyalarını ele
    seen_norms: list[str] = [norm_title(title)]
    clean_sentences: list[str] = []
    for s in candidates:
        if is_seo_spam_sentence(s):
            continue
        rw = paraphrase_sentence(strip_page_chrome(s, title))
        if len(rw) < 45:
            continue
        nt = norm_title(rw)
        if any(nt[:45] == sn[:45] or is_similar(rw, sn) for sn in seen_norms):
            continue
        seen_norms.append(nt)
        clean_sentences.append(rw)
        if len(clean_sentences) >= 14:
            break

    # Önce başlıktaki konunun en net özetini seç, kalan cümleler "Ayrıntılar" olsun
    answer, clean_sentences = pick_answer(title, clean_sentences)

    # Cümleleri 2'şerli akıcı paragraflar halinde grupla
    body: list[str] = []
    for i in range(0, len(clean_sentences), 2):
        para = " ".join(clean_sentences[i:i + 2]).strip()
        if para:
            body.append(para)
        if len(body) >= 6:
            break

    # Eğer gövde 2 paragraftan az kaldıysa, konuya uygun dengeli editoryal paragraflarla tamamla
    if len(body) < 2:
        ctx_paras = official_context_paragraphs(title, source, category)
        for cp in ctx_paras:
            if not any(is_similar(cp, existing) for existing in ([answer] if answer else []) + body):
                body.append(cp)
            if len(body) >= 2:
                break

    if not answer:
        if body:
            answer = body[0]
            body = body[1:]
        else:
            ctx = official_context_paragraphs(title, source, category)
            answer = ctx[0]
            body = ctx[1:]
    if not body:
        body = official_context_paragraphs(title, source, category)[:2]
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
    with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as r:
        return r.read()


def fetch_official_sources() -> list[dict]:
    """Gazetelerin haber kaynağı aldığı birincil resmî kurumların (ÖSYM, YÖK, TÜBİTAK, VGM, TEV, Ulusal Ajans, Resmî Gazete)
    duyuru sayfalarını doğrudan tarar."""
    now_iso = datetime.now(timezone.utc).isoformat()
    results: list[dict] = []

    targets = [
        ("ÖSYM", "https://www.osym.gov.tr/", "https://www.osym.gov.tr/",
         r'<a[^>]+href=["\'](/(?:202[67]-|osym-)[^"\'#?]+)["\'][^>]*>(.*?)</a>'),
        ("YÖK", "https://www.yok.gov.tr/", "https://www.yok.gov.tr/",
         r'<a[^>]+href=["\']((?:https://www\.yok\.gov\.tr)?/tr/(?:news|announcements)/[^"\'#?]+)["\'][^>]*>(.*?)</a>'),
        ("TÜBİTAK", "https://tubitak.gov.tr/tr/duyuru", "https://tubitak.gov.tr/",
         r'<a[^>]+href=["\'](/tr/duyuru/[^"\'#?]+)["\'][^>]*>(.*?)</a>'),
        ("VGM", "https://www.vgm.gov.tr/duyurular", "https://www.vgm.gov.tr/",
         r'<a[^>]+href=["\'](/duyurular/[^"\'#?]+)["\'][^>]*>(.*?)</a>'),
        ("TEV", "https://www.tev.org.tr/", "https://www.tev.org.tr/",
         r'<a[^>]+href=["\']([^"\']*duyuru/tr/[^"\'#?]+)["\'][^>]*>(.*?)</a>'),
        ("Türkiye Ulusal Ajansı", "https://www.ua.gov.tr/", "https://www.ua.gov.tr/",
         r'<a[^>]+href=["\'](/(?:haber|duyuru)/[^"\'#?]+)["\'][^>]*>(.*?)</a>'),
        ("Resmî Gazete", "https://www.resmigazete.gov.tr/", "https://www.resmigazete.gov.tr/",
         r'<a[^>]+href=["\'](https://www\.resmigazete\.gov\.tr/eskiler/\d{4}/\d{2}/\d{8}-\d+\.htm)["\'][^>]*>(.*?)</a>'),
    ]

    for source, page_url, base_url, pattern in targets:
        try:
            raw_html = http_get(page_url, timeout=12).decode("utf-8", errors="ignore")
            seen_u: set[str] = set()
            count = 0
            for href_val, inner in re.findall(pattern, raw_html, flags=re.S | re.I):
                title = strip_html(inner).lstrip("–—-• ")
                if len(title) < 22 or any(k in tr_lower(title) for k in ("devamını oku", "detaylar", "tümü", "tıklayınız", "e-devlet ile giriş yap", "aday işlemleri sistemi")):
                    continue
                full_url = urllib.parse.urljoin(base_url, href_val.strip())
                if full_url in seen_u:
                    continue
                seen_u.add(full_url)
                results.append({
                    "source": source,
                    "source_url": full_url,
                    "raw_title": title,
                    "raw_desc": "",
                    "published": now_iso,
                })
                count += 1
                if count >= 12:
                    break
            print(f"✓ [Ana Kaynak] {source}: {count} duyuru")
        except Exception as e:
            print(f"! [Ana Kaynak] {source} taranamadı: {e}", file=sys.stderr)

    return results


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
    if any(x in title for x in ["sözleşmeli personel", "meclisi üyesi", "ihale", "kuruluşunda amaçlarına"]):
        return False
    if item.get("source") in ("ÖSYM", "YÖK", "TEV", "Türkiye Ulusal Ajansı"):
        return True
    return any(k in title for k in KEYWORDS) or sum(k in text for k in KEYWORDS) >= 2


def rule_category(title: str, desc: str = "", source: str = "") -> str:
    for text in (title, title + " " + desc):
        t = tr_lower(text)
        for cat, kws in CATEGORY_RULES:
            if any(k in t for k in kws):
                return cat
    if source == "ÖSYM":
        return "Sınavlar"
    if source in ("VGM", "TEV", "TÜBİTAK"):
        return "Burslar"
    if source == "Türkiye Ulusal Ajansı":
        return "Yurt Dışı"
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
        if not is_candidate({"raw_title": rt, "raw_desc": e.get("summary", ""), "source": e.get("source", "")}):
            continue
        ct = clean_title(rt)
        if any(is_similar(ct, st) for st in seen_titles):
            continue
        e["title"] = ct
        e["category"] = rule_category(ct, e.get("summary", ""), e.get("source", ""))
        seen_links.add(e["source_url"])
        seen_titles.append(ct)
        used_slugs.add(e["slug"])
        existing.append(e)

    # 1. Önce doğrudan resmî kurumları (Ana Kaynakları) tara
    fetched: list[dict] = fetch_official_sources()

    # 2. Ardından haber ajanslarını ve gazeteleri tara
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
        cat = rule_category(ct, it["raw_desc"], it["source"])
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
