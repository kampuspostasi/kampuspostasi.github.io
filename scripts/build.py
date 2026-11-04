#!/usr/bin/env python3
"""Kampüs Postası - statik site üretici. data/news.json -> _site/"""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone, timedelta
from html import escape
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "_site"
SITE_NAME = "Kampüs Postası"
TAGLINE = "Üniversite, burs ve sınav gündemi"
DESC = "Kampüs Postası: KYK, burslar, YKS ve KPSS gibi sınavlar, YÖK kararları ve üniversite haberleri."
BASE_URL = os.environ.get("SITE_URL", "http://localhost:8000").rstrip("/")
BASE_PATH = os.environ.get("BASE_PATH", "").rstrip("/")
TR = timezone(timedelta(hours=3))

CATS = {
    "Burslar": ("burslar", "Devlet, vakıf, belediye ve özel sektör bursları"),
    "KYK & Yurtlar": ("kyk-yurtlar", "KYK burs ve kredileri, yurt başvuruları"),
    "Sınavlar": ("sinavlar", "YKS, KPSS, ALES, YDS, DGS ve ÖSYM duyuruları"),
    "Üniversiteler": ("universiteler", "YÖK kararları ve üniversitelerden haberler"),
    "Yurt Dışı": ("yurt-disi", "Erasmus, yurt dışı burslar ve değişim programları"),
    "Kariyer & Staj": ("kariyer-staj", "Staj programları, kariyer ve mezunlar"),
}
AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
GUNLER = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
PER_PAGE = 30
NOW = datetime.now(TR)


def u(path: str = "/") -> str:
    return f"{BASE_PATH}{path}"


def abs_u(path: str = "/") -> str:
    return f"{BASE_URL}{path}"


def dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso).astimezone(TR)


def long_date(d: datetime) -> str:
    return f"{d.day} {AYLAR[d.month - 1]} {d.year}"


def short_when(iso: str) -> str:
    d = dt(iso)
    if d.date() == NOW.date():
        return f"{d:%H:%M}"
    if d.date() == (NOW - timedelta(days=1)).date():
        return "Dün"
    return f"{d.day} {AYLAR[d.month - 1]}"


def cat_slug(name: str) -> str:
    return CATS.get(name, CATS["Üniversiteler"])[0]


def write(path: str, content: str) -> None:
    p = OUT / path.lstrip("/")
    if path.endswith("/"):
        p = p / "index.html"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, "utf-8")


def layout(title: str, body: str, *, desc: str = DESC, path: str = "/", jsonld: str = "", active: str = "") -> str:
    full_title = f"{title} — {SITE_NAME}" if title != SITE_NAME else f"{SITE_NAME} | {TAGLINE}"
    nav = f'<a href="{u("/")}" class="{"on" if active == "home" else ""}">Ana Sayfa</a>' + "".join(
        f'<a href="{u(f"/kategori/{slug}/")}" class="{"on" if active == name else ""}">{escape(name)}</a>'
        for name, (slug, _) in CATS.items()
    )
    adsense = os.environ.get("ADSENSE_CLIENT", "")
    ads = (f'<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={adsense}" '
           f'crossorigin="anonymous"></script>') if adsense else ""
    gsv = os.environ.get("GOOGLE_SITE_VERIFICATION", "")
    gsv_tag = f'<meta name="google-site-verification" content="{escape(gsv)}">' if gsv else ""
    return f"""<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(full_title)}</title>
<meta name="description" content="{escape((desc or DESC)[:160])}">
<link rel="canonical" href="{abs_u(path)}">
<meta property="og:title" content="{escape(full_title)}">
<meta property="og:description" content="{escape((desc or DESC)[:200])}">
<meta property="og:type" content="website">
<meta property="og:url" content="{abs_u(path)}">
<meta property="og:site_name" content="{SITE_NAME}">
<meta property="og:locale" content="tr_TR">
{gsv_tag}
<link rel="icon" href="{u('/assets/favicon.svg')}" type="image/svg+xml">
<link rel="alternate" type="application/rss+xml" title="{SITE_NAME}" href="{u('/rss.xml')}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;0,8..60,700;1,8..60,400&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{u('/assets/style.css')}">
<script>
(function(){{try{{var t=localStorage.getItem('kp_theme');if(t==='dark'||(!t&&window.matchMedia('(prefers-color-scheme: dark)').matches))document.documentElement.setAttribute('data-theme','dark');}}catch(e){{}}}})();
</script>
{ads}
{jsonld}
</head>
<body>
<div class="strip"><div class="wrap">
  <span class="strip-l">{GUNLER[NOW.weekday()]}, {long_date(NOW)}</span>
  <div class="strip-r">
    <form class="quick-search" action="{u('/ara/')}" method="get">
      <input type="search" name="q" placeholder="Arşivde ara…" aria-label="Arşivde ara">
    </form>
    <a href="{u('/arsiv/')}" class="hide-sm">Arşiv</a>
    <a href="{u('/hakkinda/')}" class="hide-sm">Künye</a>
    <button id="theme-btn" class="theme-btn" type="button" aria-label="Görünüm değiştir">Gece</button>
  </div>
</div></div>
<header class="masthead">
  <div class="wrap">
    <a class="brand" href="{u('/')}">Kampüs <i>Postası</i></a>
    <div class="motto">{escape(TAGLINE)}</div>
  </div>
</header>
<nav class="sections"><div class="wrap">{nav}</div></nav>
<main class="wrap">
{body}
</main>
<footer class="foot">
  <div class="wrap foot-grid">
    <div>
      <div class="foot-brand">Kampüs <i>Postası</i></div>
      <p>Öğrenciler ve adaylar için üniversite, burs ve sınav haberleri. Haberler ilgili yayın kuruluşlarına
      kaynak gösterilerek kısaca aktarılır; tam metin için kaynağa bağlantı verilir.</p>
    </div>
    <div>
      <h4>Bölümler</h4>
      {"".join(f'<a href="{u(f"/kategori/{s}/")}">{escape(n)}</a>' for n, (s, _) in CATS.items())}
    </div>
    <div>
      <h4>Kampüs Postası</h4>
      <a href="{u('/hakkinda/')}">Künye ve iletişim</a>
      <a href="{u('/ara/')}">Arşivde ara</a>
      <a href="{u('/rss.xml')}">RSS beslemesi</a>
      <a class="mail-link mail-show" data-u="kampuspostasi" data-d="gmail.com" href="{u('/hakkinda/')}">İletişim</a>
    </div>
  </div>
  <div class="wrap copy">© {NOW.year} Kampüs Postası. Başvuru tarihleri ve şartlar için ilgili kurumların resmî duyurularını esas alınız.</div>
</footer>
<script>
(function(){{
  document.querySelectorAll('.mail-link').forEach(el=>{{
    const m=el.getAttribute('data-u')+'@'+el.getAttribute('data-d');
    el.href='mailto:'+m;
    if(el.classList.contains('mail-show'))el.textContent=m;
  }});
  const btn=document.getElementById('theme-btn');
  function syncBtn(){{
    if(!btn)return;
    const dark=document.documentElement.getAttribute('data-theme')==='dark';
    btn.textContent=dark?'Gündüz':'Gece';
  }}
  syncBtn();
  if(btn)btn.addEventListener('click',()=>{{
    const dark=document.documentElement.getAttribute('data-theme')==='dark';
    if(dark){{document.documentElement.removeAttribute('data-theme');try{{localStorage.setItem('kp_theme','light');}}catch(e){{}}}}
    else{{document.documentElement.setAttribute('data-theme','dark');try{{localStorage.setItem('kp_theme','dark');}}catch(e){{}}}}
    syncBtn();
  }});
  const cp=document.getElementById('copy-link');
  if(cp)cp.addEventListener('click',()=>{{
    navigator.clipboard.writeText(location.href).then(()=>{{
      const orig=cp.textContent;cp.textContent='Kopyalandı';
      setTimeout(()=>{{cp.textContent=orig;}},2000);
    }}).catch(()=>{{}});
  }});
  try{{
    const sp=new URLSearchParams(location.search);
    if(sp.get('admin')==='1')localStorage.setItem('kp_ignore','1');
    if(sp.get('admin')==='0')localStorage.removeItem('kp_ignore');
    if(localStorage.getItem('kp_ignore')==='1')return;
  }}catch(e){{}}
  if(location.hostname!=='kampuspostasi.github.io')return;
  const b='https://abacus.jasoncameron.dev/hit/kampuspostasi_v2/',d=new Date().toISOString().slice(0,10);
  fetch(b+'total_views').catch(()=>{{}});
  fetch(b+'views_'+d).catch(()=>{{}});
  try{{
    if(!localStorage.getItem('kp_u')){{localStorage.setItem('kp_u','1');fetch(b+'unique_visitors').catch(()=>{{}});}}
    if(localStorage.getItem('kp_d')!==d){{localStorage.setItem('kp_d',d);fetch(b+'uniques_'+d).catch(()=>{{}});}}
  }}catch(e){{}}
}})();
</script>
</body>
</html>"""


def kicker(e: dict) -> str:
    return f'<a class="kicker" href="{u(f"/kategori/{cat_slug(e["category"])}/")}">{escape(e["category"])}</a>'


def href(e: dict) -> str:
    return u(f"/haber/{e['slug']}/")


def trim(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 10].rsplit(" ", 1)[0] + "…"


def src_label(e: dict) -> str:
    return escape(e["source"])


def story(e: dict, size: str = "m", summary_len: int = 200, show_kicker: bool = True) -> str:
    summ = f'<p class="dek">{escape(trim(e["summary"], summary_len))}</p>' if e.get("summary") and summary_len else ""
    return f"""<article class="story s-{size}">
  {kicker(e) if show_kicker else ""}
  <h3><a href="{href(e)}">{escape(e['title'])}</a></h3>
  {summ}
  <div class="byline">{src_label(e)} · <time datetime="{e['published']}">{short_when(e['published'])}</time></div>
</article>"""


def row(e: dict) -> str:
    summ = f'<p class="dek">{escape(trim(e["summary"], 260))}</p>' if e.get("summary") else ""
    return f"""<article class="row">
  <div class="row-when"><time datetime="{e['published']}">{short_when(e['published'])}</time></div>
  <div class="row-body">
    {kicker(e)}
    <h3><a href="{href(e)}">{escape(e['title'])}</a></h3>
    {summ}
    <div class="byline">{src_label(e)}</div>
  </div>
</article>"""


def pager(base: str, page: int, pages: int) -> str:
    if pages <= 1:
        return ""
    link = lambda p: u(base if p == 1 else f"{base}sayfa/{p}/")
    prev = f'<a href="{link(page - 1)}">← Daha yeni</a>' if page > 1 else "<span></span>"
    nxt = f'<a href="{link(page + 1)}">Daha eski →</a>' if page < pages else "<span></span>"
    return f'<nav class="pager">{prev}<span>{page} / {pages}</span>{nxt}</nav>'


def sidebar(items: list[dict], exclude: str = "") -> str:
    radar_Pool = [
        e for e in items
        if e["category"] in ("Burslar", "KYK & Yurtlar", "Sınavlar", "Yurt Dışı")
        and any(k in (e["title"] + " " + e.get("summary", "")).lower()
                for k in ("başvuru", "sonuç", "takvim", "tarih", "burs", "kredi", "yurt", "sınav", "erasmus"))
    ][:4]
    if not radar_Pool:
        radar_Pool = items[:4]
    radar_html = "".join(
        f'<li><span class="r-badge">{escape(e["category"].split()[0])}</span>'
        f'<a href="{href(e)}">{escape(e["title"])}</a></li>'
        for e in radar_Pool
    )
    latest = "".join(
        f'<li><time>{short_when(e["published"])}</time><a href="{href(e)}">{escape(e["title"])}</a></li>'
        for e in items[:10]
    )
    secs = "".join(
        f'<li><a href="{u(f"/kategori/{s}/")}">{escape(n)}</a><span>{sum(1 for e in items if e["category"] == n)}</span></li>'
        for n, (s, _) in CATS.items() if n != exclude
    )
    return f"""<aside class="side">
  <section class="radar-box"><h4 class="label">Burs ve Sınav Gündemi</h4><ul class="radar-list">{radar_html}</ul></section>
  <section><h4 class="label">Son Dakika</h4><ol class="ticker">{latest}</ol></section>
  <section><h4 class="label">Bölümler</h4><ul class="seclist">{secs}</ul></section>
</aside>"""


def pick_lead(items: list[dict]) -> dict:
    # En güncel (son 10) haber içinden burs/KYK/sınav/üniversite manşetini seç
    recent = items[:10]
    for pref in ("Burslar", "KYK & Yurtlar", "Üniversiteler", "Sınavlar"):
        for e in recent:
            if e["category"] == pref and e.get("summary"):
                return e
    for pref in ("Burslar", "KYK & Yurtlar", "Üniversiteler", "Sınavlar"):
        for e in recent:
            if e["category"] == pref:
                return e
    return items[0]


def main() -> None:
    items: list[dict] = json.loads((ROOT / "data" / "news.json").read_text("utf-8"))
    items.sort(key=lambda e: e["published"], reverse=True)
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "assets").mkdir(parents=True)
    shutil.copy(ROOT / "site" / "style.css", OUT / "assets" / "style.css")
    shutil.copy(ROOT / "site" / "favicon.svg", OUT / "assets" / "favicon.svg")

    # ---------------- Ana sayfa
    lead = pick_lead(items)
    used = {lead["slug"]}
    seconds = [e for e in items[:15] if e["slug"] not in used][:3]
    used |= {e["slug"] for e in seconds}
    briefs = [e for e in items if e["slug"] not in used][:6]
    used |= {e["slug"] for e in briefs}

    front = f"""<section class="front">
  <div class="lead-col">
    <article class="story s-xl">
      {kicker(lead)}
      <h2><a href="{href(lead)}">{escape(lead['title'])}</a></h2>
      {f'<p class="dek">{escape(trim(lead["summary"], 320))}</p>' if lead.get("summary") else ""}
      <div class="byline">{src_label(lead)} · <time datetime="{lead['published']}">{short_when(lead['published'])}</time></div>
    </article>
    <div class="seconds">{"".join(story(e, "m", 160) for e in seconds)}</div>
  </div>
  <div class="brief-col">
    <h4 class="label">Kısa Kısa</h4>
    {"".join(story(e, "s", 0) for e in briefs)}
  </div>
  {sidebar(items)}
</section>"""

    blocks = ""
    for name, (slug, cdesc) in CATS.items():
        sub = [e for e in items if e["category"] == name and e["slug"] not in used][:4]
        if not sub:
            continue
        blocks += f"""<section class="block">
  <header class="block-head"><h2><a href="{u(f'/kategori/{slug}/')}">{escape(name)}</a></h2>
  <a class="more" href="{u(f'/kategori/{slug}/')}">Tümü →</a></header>
  <div class="block-grid">{"".join(story(e, "m", 140, False) for e in sub)}</div>
</section>"""
    write("/", layout(SITE_NAME, front + blocks, path="/", active="home"))

    # Arşiv sayfaları
    pages = max(1, -(-len(items) // PER_PAGE))
    for p in range(1, pages + 1):
        chunk = items[(p - 1) * PER_PAGE: p * PER_PAGE]
        path = "/arsiv/" if p == 1 else f"/arsiv/sayfa/{p}/"
        body = f"""<header class="page-head"><h1>Tüm Haberler</h1><p>En yeni haberden eskiye doğru.</p></header>
<div class="two-col"><div class="list">{"".join(row(e) for e in chunk)}{pager("/arsiv/", p, pages)}</div>{sidebar(items)}</div>"""
        write(path, layout("Tüm Haberler" + (f" - Sayfa {p}" if p > 1 else ""), body, path=path))

    # ---------------- Kategoriler
    for name, (slug, cdesc) in CATS.items():
        sub = [e for e in items if e["category"] == name]
        base = f"/kategori/{slug}/"
        pages = max(1, -(-len(sub) // PER_PAGE))
        for p in range(1, pages + 1):
            chunk = sub[(p - 1) * PER_PAGE: p * PER_PAGE]
            path = base if p == 1 else f"{base}sayfa/{p}/"
            rows = "".join(row(e) for e in chunk) or '<p class="empty">Bu bölümde henüz haber yok.</p>'
            body = f"""<header class="page-head"><h1>{escape(name)}</h1><p>{escape(cdesc)}</p></header>
<div class="two-col"><div class="list">{rows}{pager(base, p, pages)}</div>{sidebar(items, name)}</div>"""
            write(path, layout(name + (f" - Sayfa {p}" if p > 1 else ""), body,
                               desc=f"{name}: {cdesc}. Güncel haberler Kampüs Postası'nda.", path=path, active=name))

    # ---------------- Haber sayfaları
    for e in items:
        related = [r for r in items if r["category"] == e["category"] and r["slug"] != e["slug"]][:5]
        tags = "".join(f'<a class="tag" href="{u("/ara/?q=" + t)}">{escape(t)}</a>' for t in e.get("tags", []))
        path = f"/haber/{e['slug']}/"
        d = dt(e["published"])
        ld = json.dumps({
            "@context": "https://schema.org", "@type": "NewsArticle", "headline": e["title"][:110],
            "datePublished": e["published"], "dateModified": e.get("added", e["published"]),
            "description": (e["summary"] or e["title"])[:300], "mainEntityOfPage": abs_u(path),
            "publisher": {"@type": "Organization", "name": SITE_NAME}, "isBasedOn": e["source_url"],
        }, ensure_ascii=False)
        answer = e.get("summary") or ""
        details = [p for p in (e.get("body") or []) if p.strip() and p.strip() != answer.strip()]
        lede = f'<p class="answer">{escape(answer or e["title"])}</p>'
        prose = ("<h2 class=\"details-h\">Ayrıntılar</h2><div class=\"prose\">"
                 + "".join(f"<p>{escape(p)}</p>" for p in details) + "</div>") if details else ""
        rel = "".join(
            f'<li><a href="{href(r)}">{escape(r["title"])}</a><time>{short_when(r["published"])}</time></li>' for r in related)
        full_url = abs_u(path)
        wa_text = quote(f"{e['title']} — {full_url}")
        tg_url = f"https://t.me/share/url?url={quote(full_url)}&text={quote(e['title'])}"
        tw_url = f"https://twitter.com/intent/tweet?url={quote(full_url)}&text={quote(e['title'])}"
        share_bar = f"""<div class="share-bar">
  <span class="share-label">Arkadaşına gönder:</span>
  <a class="share-btn share-wa" href="https://api.whatsapp.com/send?text={wa_text}" target="_blank" rel="noopener">WhatsApp</a>
  <a class="share-btn share-tg" href="{tg_url}" target="_blank" rel="noopener">Telegram</a>
  <a class="share-btn" href="{tw_url}" target="_blank" rel="noopener">X</a>
  <button id="copy-link" class="share-btn" type="button">Bağlantıyı Kopyala</button>
</div>"""
        body = f"""<div class="two-col article-wrap">
<article class="article">
  {kicker(e)}
  <h1>{escape(e['title'])}</h1>
  <div class="article-meta">
    <span>Kampüs Postası Haber Merkezi</span>
    <time datetime="{e['published']}">{d.day} {AYLAR[d.month - 1]} {d.year}, {d:%H:%M}</time>
  </div>
  {lede}
  {prose}
  {share_bar}
  <div class="tags">{tags}</div>
  <p class="disclaimer">Kaynak: <a href="{escape(e['source_url'])}" target="_blank" rel="noopener nofollow">{escape(e['source'])}</a> · Başvuru tarihleri, şartlar ve sonuçlar için ilgili kurumun resmî duyurusunu esas alınız.</p>
  {f'<section class="related"><h4 class="label">Bu bölümden</h4><ul>{rel}</ul></section>' if rel else ""}
</article>
{sidebar(items, "")}
</div>"""
        write(path, layout(e["title"], body, desc=e["summary"] or e["title"], path=path, active=e["category"],
                           jsonld=f'<script type="application/ld+json">{ld}</script>'))

    # ---------------- Arama
    idx = [{"t": e["title"], "s": e["summary"][:200], "c": e["category"], "u": href(e),
            "d": short_when(e["published"]), "k": " ".join(e.get("tags", []))} for e in items]
    (OUT / "search.json").write_text(json.dumps(idx, ensure_ascii=False), "utf-8")
    search_body = f"""<header class="page-head"><h1>Arşivde Ara</h1></header>
<input id="q" class="bigsearch" type="search" placeholder="Örn. KYK burs sonuçları, YKS takvimi, Erasmus" autofocus>
<p id="info" class="muted"></p><div id="res" class="list"></div>
<script>
const low=s=>s.replace(/İ/g,'i').replace(/I/g,'ı').toLowerCase();
const q=document.getElementById('q'),res=document.getElementById('res'),info=document.getElementById('info');
q.value=new URLSearchParams(location.search).get('q')||'';
let data=[];fetch('{u('/search.json')}').then(r=>r.json()).then(d=>{{data=d;run();}});
const esc=s=>s.replace(/[&<>"]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[c]));
function run(){{const w=low(q.value.trim()).split(/\\s+/).filter(Boolean);if(!w.length){{res.innerHTML='';info.textContent='';return;}}
const hits=data.filter(e=>{{const t=low(e.t+' '+e.s+' '+e.c+' '+e.k);return w.every(x=>t.includes(x));}}).slice(0,60);
info.textContent=hits.length+' sonuç bulundu';
res.innerHTML=hits.map(e=>`<article class="row"><div class="row-when">${{e.d}}</div><div class="row-body"><span class="kicker">${{esc(e.c)}}</span><h3><a href="${{e.u}}">${{esc(e.t)}}</a></h3>${{e.s?`<p class="dek">${{esc(e.s)}}</p>`:''}}</div></article>`).join('');}}
q.addEventListener('input',run);
</script>"""
    write("/ara/", layout("Arşivde Ara", search_body, path="/ara/"))

    # ---------------- Künye
    write("/hakkinda/", layout("Künye", f"""<div class="two-col"><article class="article">
<span class="kicker">Künye</span>
<h1>Kampüs Postası hakkında</h1>
<p class="lede">Kampüs Postası; üniversite öğrencileri, adaylar ve yeni mezunlar için burs, KYK, sınav ve
yükseköğretim gündemini tek sayfada toplayan bağımsız bir haber derleme yayınıdır.</p>
<div class="prose">
<p>Türkiye'nin ulusal ve yerel yayın kuruluşlarının eğitim haberlerini takip ediyor, öğrencileri doğrudan
ilgilendiren gelişmeleri seçiyor ve kısa özetleriyle yayımlıyoruz. Her haberde özgün kaynağa bağlantı yer alır;
haberin tam metni ve görselleri ilgili yayın kuruluşuna aittir.</p>
<p>Başvuru tarihleri, şartlar ve sonuçlar değişebilir. Karar vermeden önce ÖSYM, YÖK, GSB/KYK, üniversiteler
ve burs veren kurumların resmî duyurularını kontrol etmenizi öneririz.</p>
<h3>İletişim ve içerik kaldırma</h3>
<p>Düzeltme talepleri, haber ve burs duyurusu önerileri ile telif bildirimleri için bize doğrudan
<b><a class="mail-link mail-show" data-u="kampuspostasi" data-d="gmail.com" href="#">e-posta</a></b>
adresimizden ulaşabilirsiniz.</p>
</div></article>{sidebar(items)}</div>""", path="/hakkinda/"))

    write("/404.html", layout("Sayfa bulunamadı", f'<div class="empty"><h1>Aradığınız sayfa bulunamadı</h1><p><a href="{u("/")}">Ana sayfaya dönün</a> ya da <a href="{u("/ara/")}">arşivde arayın</a>.</p></div>', path="/404.html"))

    # ---------------- RSS / Sitemap / robots
    rss_xsl = f"""<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
<xsl:output method="html" encoding="UTF-8"/>
<xsl:template match="/rss/channel">
<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title><xsl:value-of select="title"/> — RSS Akışı</title>
<link rel="stylesheet" href="{u('/assets/style.css')}"/>
</head>
<body>
<header class="masthead"><div class="wrap">
  <a class="brand" href="{u('/')}">Kampüs <i>Postası</i></a>
  <div class="motto">RSS Haber Akışı</div>
</div></header>
<main class="wrap" style="max-width:820px;margin-top:24px">
  <p class="dek" style="padding:14px 16px;background:var(--card);border:1px solid var(--rule);margin-bottom:24px">
    Bu sayfa <b>Kampüs Postası</b>'nın otomatik RSS beslemesidir. Haber okuyucu uygulamalarınıza (Feedly, NetNewsWire vb.)
    <code>{abs_u('/rss.xml')}</code> adresini ekleyerek yeni haberleri anında takip edebilir veya aşağıdaki son başlıkları doğrudan okuyabilirsiniz.
  </p>
  <div class="list">
    <xsl:for-each select="item">
      <article class="row" style="grid-template-columns:1fr">
        <div class="row-body">
          <span class="kicker"><xsl:value-of select="category"/></span>
          <h3><a><xsl:attribute name="href"><xsl:value-of select="link"/></xsl:attribute><xsl:value-of select="title"/></a></h3>
          <p class="dek"><xsl:value-of select="description"/></p>
        </div>
      </article>
    </xsl:for-each>
  </div>
</main>
</body>
</html>
</xsl:template>
</xsl:stylesheet>"""
    (OUT / "rss.xsl").write_text(rss_xsl, "utf-8")
    rss_items = "".join(
        f"<item><title>{escape(e['title'])}</title><link>{abs_u(href(e)[len(BASE_PATH):])}</link>"
        f"<guid>{abs_u(href(e)[len(BASE_PATH):])}</guid><category>{escape(e['category'])}</category>"
        f"<pubDate>{datetime.fromisoformat(e['published']).strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate>"
        f"<description>{escape(e['summary'] or e['title'])}</description></item>"
        for e in items[:50]
    )
    (OUT / "rss.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?><?xml-stylesheet type="text/xsl" href="{u("/rss.xsl")}"?>'
        f'<rss version="2.0"><channel><title>{SITE_NAME}</title>'
        f'<link>{abs_u("/")}</link><description>{escape(DESC)}</description><language>tr</language>{rss_items}</channel></rss>', "utf-8")
    urls = ["/", "/arsiv/", "/hakkinda/"] + [f"/kategori/{s}/" for s, _ in CATS.values()] + [f"/haber/{e['slug']}/" for e in items]
    (OUT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(f"<url><loc>{abs_u(x)}</loc></url>" for x in urls) + "</urlset>", "utf-8")
    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {abs_u('/sitemap.xml')}\n", "utf-8")
    (OUT / "googlef4093a426f60860e.html").write_text("google-site-verification: googlef4093a426f60860e.html", "utf-8")
    (OUT / ".nojekyll").write_text("")
    print(f"✔ Site üretildi: {len(items)} haber, {len(urls)} URL -> {OUT}")


if __name__ == "__main__":
    main()
