#!/usr/bin/env python3
# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only
"""Build the roadmap pages published on GitHub Pages from roadmap.json.

Usage: python3 site/build.py [output_dir]   (default: site/_build)
"""

import json
import os
import shutil
import sys
from html import escape

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_URL = "https://github.com/atsanna/merginmaps-server"
# branch the published page links to (set by the Pages workflow)
BRANCH = os.environ.get("SITE_BRANCH", "main")

TEXT = {
    "it": {
        "file": "roadmap.html",
        "other": ("en", "roadmap-en.html", "English"),
        "title": "Roadmap — Mergin Maps Server, edizione open con funzioni Enterprise",
        "desc": "Stato e prossimi passi del fork open source di Mergin Maps Server che reimplementa le funzioni della Enterprise Edition.",
        "eyebrow": "Roadmap",
        "h1": "Dove siamo, <em>dove andiamo</em>",
        "lead": "Questo fork di Mergin Maps Server porta nel server open source le funzioni della Enterprise Edition, riscritte da zero partendo solo dalla documentazione pubblica. La pagina si aggiorna a ogni passo completato.",
        "stats": ["passi completati", "passi pianificati", "delle funzioni coperte", "test automatici"],
        "toc": ["Disponibile", "Passi", "Copertura", "Fuori ambito"],
        "avail_eyebrow": "Disponibile oggi",
        "avail_h2": "Cosa funziona già",
        "avail_sub": "Funzioni del backend già pronte e provate dai test; l'interfaccia web arriva nei prossimi passi.",
        "steps_eyebrow": "Prossimi passi",
        "steps_h2": "{n} passi, in ordine di dipendenza",
        "steps_sub": "Ogni milestone dipende da quelle prima: prima i workspace, poi membri, quote, trasferimenti, SSO e mappe web.",
        "pill": {"done": "Fatto", "wip": "In corso", "todo": "Da fare"},
        "cov_eyebrow": "Copertura delle funzionalità",
        "cov_h2": "Quanto della Enterprise Edition è già qui",
        "cov_sub": "Per ogni area contiamo i passi fatti, in corso e da fare (quelli in corso valgono metà). Aggiornato il {date}.",
        "total": "Totale",
        "legend": ["fatto", "in corso"],
        "out_eyebrow": "Fuori ambito",
        "out_h2": "Cosa questo fork non farà",
        "final_h2": "Segui lo sviluppo",
        "final_sub": "Codice, piano di lavoro e analisi delle funzioni sono pubblici su GitHub.",
        "btn_repo": "Codice su GitHub",
        "btn_plan": "Piano di lavoro",
        "theme": "Cambia tema",
        "top": "Torna all'inizio",
        "footer": "Software libero con licenza AGPL-3.0 · Sviluppato con",
        "disclaimer": "Progetto indipendente: non affiliato, sponsorizzato né approvato da Mergin Maps o Lutra Consulting Ltd. «Mergin Maps» e i relativi nomi e loghi sono marchi dei rispettivi proprietari, usati solo per indicare il software originale da cui deriva questo fork. Le funzioni sono reimplementate dalla documentazione pubblica, senza codice proprietario.",
    },
    "en": {
        "file": "roadmap-en.html",
        "other": ("it", "roadmap.html", "Italiano"),
        "title": "Roadmap — Mergin Maps Server, open edition with Enterprise features",
        "desc": "Status and next steps of the open-source Mergin Maps Server fork reimplementing the Enterprise Edition features.",
        "eyebrow": "Roadmap",
        "h1": "Where we are, <em>where we are going</em>",
        "lead": "This fork of Mergin Maps Server brings the Enterprise Edition features to the open-source server, rewritten from scratch using public documentation only. This page is updated at every completed step.",
        "stats": ["steps completed", "planned steps", "of features covered", "automated tests"],
        "toc": ["Available", "Steps", "Coverage", "Out of scope"],
        "avail_eyebrow": "Available today",
        "avail_h2": "What already works",
        "avail_sub": "Backend features ready and covered by tests; the web interface comes in the next steps.",
        "steps_eyebrow": "Next steps",
        "steps_h2": "{n} steps, in dependency order",
        "steps_sub": "Each milestone builds on the previous ones: workspaces first, then members, quotas, transfers, SSO and web maps.",
        "pill": {"done": "Done", "wip": "In progress", "todo": "To do"},
        "cov_eyebrow": "Feature coverage",
        "cov_h2": "How much of the Enterprise Edition is already here",
        "cov_sub": "For each area we count done, in-progress and to-do steps (in-progress ones count half). Updated on {date}.",
        "total": "Total",
        "legend": ["done", "in progress"],
        "out_eyebrow": "Out of scope",
        "out_h2": "What this fork will not do",
        "final_h2": "Follow the development",
        "final_sub": "Code, work plan and feature analysis are public on GitHub.",
        "btn_repo": "Code on GitHub",
        "btn_plan": "Work plan",
        "theme": "Toggle theme",
        "top": "Back to top",
        "footer": "Free software licensed under AGPL-3.0 · Developed with",
        "disclaimer": "Independent project: not affiliated with, sponsored or endorsed by Mergin Maps or Lutra Consulting Ltd. “Mergin Maps” and related names and logos are trademarks of their respective owners, used only to identify the original software this fork is based on. Features are reimplemented from public documentation, without proprietary code.",
    },
}

CSS = """
  :root {
    --ink: #0f2742; --ink-soft: #3c4f66; --muted: #66768a; --paper: #f7f6f2; --card: #ffffff;
    --line: #dfe3e8; --blue: #1d5fbf; --blue-soft: #e7effa; --terra: #c4553a; --on-blue: #ffffff;
    --green: #2e9d5b; --amber: #e0a526;
    --shadow: 0 1px 2px rgba(15,39,66,.06), 0 8px 24px rgba(15,39,66,.08);
    --radius: 14px;
    --font: system-ui, -apple-system, "Segoe UI", Roboto, Ubuntu, Cantarell, "Noto Sans", "Helvetica Neue", Arial, sans-serif;
    --mono: ui-monospace, "SFMono-Regular", "Cascadia Mono", "Ubuntu Mono", Menlo, Consolas, monospace;
    color-scheme: light;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --ink: #e8eef5; --ink-soft: #bccadb; --muted: #93a3b6; --paper: #0d1724; --card: #142235;
      --line: #22344b; --blue: #6ea4ff; --blue-soft: #16294a; --terra: #ea8a70; --on-blue: #08111c;
      --shadow: 0 1px 2px rgba(0,0,0,.3), 0 8px 24px rgba(0,0,0,.3); color-scheme: dark;
    }
  }
  :root[data-theme="dark"] {
    --ink: #e8eef5; --ink-soft: #bccadb; --muted: #93a3b6; --paper: #0d1724; --card: #142235;
    --line: #22344b; --blue: #6ea4ff; --blue-soft: #16294a; --terra: #ea8a70; --on-blue: #08111c;
    --shadow: 0 1px 2px rgba(0,0,0,.3), 0 8px 24px rgba(0,0,0,.3); color-scheme: dark;
  }
  * { box-sizing: border-box; }
  html { scroll-behavior: smooth; }
  body { margin: 0; background: var(--paper); color: var(--ink); font: 17px/1.6 var(--font); -webkit-font-smoothing: antialiased; }
  a { color: var(--blue); text-decoration-thickness: 1px; text-underline-offset: 3px; }
  code { font-family: var(--mono); font-size: .9em; background: var(--blue-soft); padding: 1px 5px; border-radius: 5px; }
  .wrap { width: min(1160px, 100% - 32px); margin-inline: auto; }
  .skip { position: absolute; inset-inline-start: -999px; }
  .skip:focus { inset-inline-start: 16px; top: 16px; background: var(--card); padding: 8px 12px; z-index: 10; }

  header.top { position: sticky; top: 0; z-index: 5; background: color-mix(in srgb, var(--paper) 88%, transparent); backdrop-filter: blur(10px); border-bottom: 1px solid var(--line); }
  .bar { display: flex; align-items: center; gap: 20px; height: 64px; }
  .brand { display: flex; align-items: center; gap: 10px; color: var(--ink); text-decoration: none; font-weight: 700; font-size: 19px; letter-spacing: -.01em; }
  .brand b { color: var(--blue); }
  .bar-right { display: flex; align-items: center; gap: 10px; margin-inline-start: auto; }
  .lang { color: var(--ink-soft); text-decoration: none; font-size: 14px; border: 1px solid var(--line); background: var(--card); border-radius: 8px; padding: 6px 10px; }
  .theme-toggle { width: 36px; height: 36px; border-radius: 8px; border: 1px solid var(--line); background: var(--card); color: var(--ink); cursor: pointer; display: grid; place-items: center; }
  .theme-toggle svg { width: 18px; height: 18px; }
  .theme-toggle .moon { display: none; }
  :root[data-theme="dark"] .theme-toggle .sun { display: none; }
  :root[data-theme="dark"] .theme-toggle .moon { display: block; }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) .theme-toggle .sun { display: none; }
    :root:not([data-theme="light"]) .theme-toggle .moon { display: block; }
  }
  .btn { display: inline-flex; align-items: center; gap: 8px; padding: 11px 18px; border-radius: 10px; font-weight: 600; font-size: 15px; text-decoration: none; border: 1px solid transparent; transition: transform .12s; }
  .btn:hover { transform: translateY(-1px); }
  .btn-primary { background: var(--blue); color: var(--on-blue); }
  .btn-ghost { border-color: var(--line); color: var(--ink); background: var(--card); }
  .bar .btn { padding: 8px 14px; }

  .eyebrow { display: inline-flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; color: var(--terra); }
  .eyebrow::before { content: ""; width: 18px; height: 2px; background: currentColor; }
  h1 { font-size: clamp(36px, 5.2vw, 60px); line-height: 1.06; letter-spacing: -.025em; margin: 14px 0 18px; max-width: 15em; }
  h1 em { font-style: normal; color: var(--blue); }
  .lead { font-size: 19px; color: var(--ink-soft); max-width: 40em; margin: 0 0 28px; }
  .cta { display: flex; flex-wrap: wrap; gap: 12px; }
  section { padding: 72px 0; }
  section.alt { background: var(--card); border-block: 1px solid var(--line); }
  h2 { font-size: clamp(28px, 3.4vw, 40px); line-height: 1.12; letter-spacing: -.02em; margin: 10px 0 14px; }
  .sub { color: var(--ink-soft); max-width: 46em; margin: 0 0 36px; font-size: 18px; }

  .rp-hero { position: relative; overflow: hidden; padding: 64px 0 40px; }
  .rp-hero::before { content: ""; position: absolute; inset: 0; background-image: linear-gradient(var(--line) 1px, transparent 1px), linear-gradient(90deg, var(--line) 1px, transparent 1px); background-size: 32px 32px; mask-image: radial-gradient(ellipse at 80% 20%, #000 0%, transparent 65%); opacity: .7; pointer-events: none; }
  .rp-hero .wrap { position: relative; }
  .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin: 36px 0 0; padding: 0; list-style: none; }
  .stats li { background: var(--card); border: 1px solid var(--line); border-radius: var(--radius); padding: 18px 20px; box-shadow: var(--shadow); }
  .stats b { display: block; font-size: clamp(28px, 3.6vw, 40px); line-height: 1.05; letter-spacing: -.02em; font-variant-numeric: tabular-nums; }
  .stats span { color: var(--muted); font-size: 14px; }
  .toc { display: flex; flex-wrap: wrap; gap: 8px; margin: 22px 0 0; padding: 0; list-style: none; }
  .toc a { display: inline-block; padding: 7px 14px; border-radius: 999px; border: 1px solid var(--line); background: var(--card); color: var(--ink-soft); text-decoration: none; font-size: 14px; }
  .toc a:hover { border-color: var(--blue); color: var(--blue); }

  .avail { columns: 2 320px; column-gap: 32px; list-style: none; padding: 0; margin: 0; }
  .avail li { break-inside: avoid; padding: 8px 0 8px 30px; position: relative; color: var(--ink-soft); border-bottom: 1px dashed var(--line); }
  .avail li::before { content: "✓"; position: absolute; inset-inline-start: 0; top: 9px; width: 20px; height: 20px; border-radius: 50%; background: var(--green); color: #fff; font-size: 12px; font-weight: 700; display: grid; place-items: center; }

  .phase { margin-top: 44px; }
  .phase-head { display: flex; align-items: center; gap: 14px; margin-bottom: 14px; }
  .phase-head .prio { font: 700 14px/1 var(--mono); padding: 9px 12px; border-radius: 9px; color: #fff; }
  .phase-head h3 { margin: 0; font-size: 22px; letter-spacing: -.01em; }
  .phase-head p { margin: 0; color: var(--muted); font-size: 15px; }
  .phase-head .count { margin-inline-start: auto; color: var(--muted); font-size: 14px; font-variant-numeric: tabular-nums; }
  .p0 .prio { background: var(--green); } .p1 .prio { background: var(--blue); } .p2 .prio { background: #7a5bd6; } .p3 .prio { background: var(--terra); }
  .steps { list-style: none; padding: 0; margin: 0; display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
  .step { display: grid; grid-template-columns: auto 1fr auto; gap: 14px; align-items: start; background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 16px 18px; min-width: 0; }
  .step .n { font: 700 13px/1 var(--mono); color: var(--muted); background: var(--blue-soft); border-radius: 8px; padding: 8px 0; width: 36px; text-align: center; }
  .step h4 { margin: 0 0 4px; font-size: 16.5px; line-height: 1.3; }
  .step p { margin: 0; color: var(--ink-soft); font-size: 14.5px; line-height: 1.5; }
  .pill { font-size: 12px; font-weight: 600; padding: 4px 10px; border-radius: 999px; white-space: nowrap; border: 1px solid var(--line); color: var(--muted); }
  .step.done { border-color: color-mix(in srgb, var(--green) 45%, var(--line)); }
  .step.done .pill { background: var(--green); border-color: var(--green); color: #fff; }
  .step.done .n { background: color-mix(in srgb, var(--green) 18%, transparent); color: var(--green); }
  .step.wip .pill { background: var(--amber); border-color: var(--amber); color: #1b1300; }

  .bars { display: grid; gap: 14px; margin: 0; padding: 0; list-style: none; }
  .bars li { display: grid; grid-template-columns: minmax(12em, 18em) 1fr 4.5em; gap: 16px; align-items: center; }
  .bars .name { font-weight: 600; font-size: 15.5px; }
  .bars .track { height: 14px; border-radius: 999px; background: var(--line); overflow: hidden; display: flex; }
  .bars .d { background: var(--blue); height: 100%; }
  .bars .p { background: color-mix(in srgb, var(--blue) 40%, transparent); height: 100%; }
  .bars .pct { text-align: end; font-variant-numeric: tabular-nums; font-weight: 600; }
  .bars li.total { border-top: 1px solid var(--line); padding-top: 14px; }
  .legend { display: flex; gap: 18px; margin: 18px 0 0; color: var(--muted); font-size: 14px; }
  .legend i { display: inline-block; width: 12px; height: 12px; border-radius: 3px; margin-inline-end: 6px; vertical-align: -1px; }
  .outs { list-style: none; padding: 0; margin: 0; display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
  .outs li { background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 14px 16px 14px 44px; position: relative; color: var(--ink-soft); font-size: 15px; }
  .outs li::before { content: "×"; position: absolute; inset-inline-start: 16px; top: 11px; color: var(--muted); font-size: 20px; line-height: 1; }

  .final { text-align: center; }
  .final .cta { justify-content: center; }
  footer { border-top: 1px solid var(--line); padding: 36px 0 48px; color: var(--muted); font-size: 14px; }
  footer small { display: block; margin-top: 16px; line-height: 1.5; max-width: 60em; }
  .to-top { position: fixed; bottom: 24px; inset-inline-end: 24px; width: 44px; height: 44px; border-radius: 50%; border: 1px solid var(--line); background: var(--card); color: var(--ink); display: grid; place-items: center; cursor: pointer; box-shadow: var(--shadow); opacity: 0; visibility: hidden; transition: opacity .2s, visibility .2s; z-index: 6; }
  .to-top svg { width: 20px; height: 20px; }
  .to-top.on { opacity: 1; visibility: visible; }

  @media (max-width: 920px) {
    .stats { grid-template-columns: repeat(2, 1fr); }
    .steps, .outs { grid-template-columns: 1fr; }
    .bars li { grid-template-columns: 1fr 4em; }
    .bars .track { grid-column: 1 / -1; grid-row: 2; }
  }
  @media (max-width: 560px) {
    body { font-size: 16px; }
    .bar .btn { display: none; }
    section { padding: 52px 0; }
    .phase-head { flex-wrap: wrap; }
    .phase-head .count { margin-inline-start: 0; }
  }
  @media (prefers-reduced-motion: reduce) { html { scroll-behavior: auto; } .btn, .to-top { transition: none; } }
"""

LOGO = """<svg width="30" height="30" viewBox="0 0 32 32" aria-hidden="true">
        <path d="M16 3c-5 0-9 4-9 9 0 7 9 17 9 17s9-10 9-17c0-5-4-9-9-9z" fill="#1d5fbf"/>
        <circle cx="16" cy="12" r="3.6" fill="#f7f6f2"/>
      </svg>"""

SUN = '<svg class="sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>'
MOON = '<svg class="moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>'
UP = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 19V5M6 11l6-6 6 6"/></svg>'

WEIGHT = {"done": 1.0, "wip": 0.5, "todo": 0.0}


def coverage(steps):
    """Return (done %, in progress %, total %) of a list of steps"""
    if not steps:
        return 0.0, 0.0, 0
    done = 100.0 * sum(s["status"] == "done" for s in steps) / len(steps)
    wip = 100.0 * sum(s["status"] == "wip" for s in steps) / len(steps)
    return done, wip, round(done + wip / 2)


def bar(name, steps, cls=""):
    d, p, pct = coverage(steps)
    return (
        f'<li class="{cls}"><span class="name">{escape(name)}</span>'
        f'<span class="track" role="img" aria-label="{pct} %"><span class="d" style="width:{d:.1f}%"></span>'
        f'<span class="p" style="width:{p:.1f}%"></span></span><span class="pct">{pct} %</span></li>'
    )


def render(data: dict, lang: str) -> str:
    t = TEXT[lang]
    phases = data["phases"]
    all_steps = [s for ph in phases for s in ph["steps"]]
    done_count = sum(s["status"] == "done" for s in all_steps)
    total_pct = coverage(all_steps)[2]
    other_lang, other_file, other_name = t["other"]
    date = data["updated"]

    out = []
    w = out.append
    w(f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(t["title"])}</title>
<meta name="description" content="{escape(t["desc"])}">
<link rel="alternate" hreflang="{other_lang}" href="{other_file}">
<meta name="theme-color" content="#f7f6f2" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#0d1724" media="(prefers-color-scheme: dark)">
<script>
  try {{ var t = localStorage.getItem('theme'); if (t) document.documentElement.dataset.theme = t; }} catch (e) {{}}
</script>
<style>{CSS}</style>
</head>
<body>
<a class="skip" href="#main">Skip</a>
<header class="top">
  <div class="wrap bar">
    <a class="brand" href="#top" aria-label="merginmaps-server">
      {LOGO}
      <span>merginmaps<b>-server</b></span>
    </a>
    <div class="bar-right">
      <a class="lang" href="{other_file}" hreflang="{other_lang}" lang="{other_lang}">{other_name}</a>
      <button class="theme-toggle" id="themeToggle" type="button" aria-label="{escape(t["theme"])}">{SUN}{MOON}</button>
      <a class="btn btn-primary" href="{REPO_URL}">GitHub</a>
    </div>
  </div>
</header>

<main id="main">
  <section class="rp-hero" id="top">
    <div class="wrap">
      <span class="eyebrow">{t["eyebrow"]}</span>
      <h1>{t["h1"]}</h1>
      <p class="lead">{escape(t["lead"])}</p>
      <ul class="stats">
        <li><b>{done_count}</b><span>{t["stats"][0]}</span></li>
        <li><b>{len(all_steps)}</b><span>{t["stats"][1]}</span></li>
        <li><b>{total_pct} %</b><span>{t["stats"][2]}</span></li>
        <li><b>{data["stats"]["tests"]}</b><span>{t["stats"][3]}</span></li>
      </ul>
      <ul class="toc">
        <li><a href="#disponibile">{t["toc"][0]}</a></li>
        <li><a href="#passi">{t["toc"][1]}</a></li>
        <li><a href="#copertura">{t["toc"][2]}</a></li>
        <li><a href="#fuori">{t["toc"][3]}</a></li>
      </ul>
    </div>
  </section>

  <section id="disponibile" class="alt" aria-labelledby="disponibile-t">
    <div class="wrap">
      <span class="eyebrow">{t["avail_eyebrow"]}</span>
      <h2 id="disponibile-t">{t["avail_h2"]}</h2>
      <p class="sub">{escape(t["avail_sub"])}</p>
      <ul class="avail">""")
    for item in data["available"]:
        w(f"<li>{escape(item[lang])}</li>")
    w(f"""</ul>
    </div>
  </section>

  <section id="passi" aria-labelledby="passi-t">
    <div class="wrap">
      <span class="eyebrow">{t["steps_eyebrow"]}</span>
      <h2 id="passi-t">{t["steps_h2"].format(n=len(all_steps))}</h2>
      <p class="sub">{escape(t["steps_sub"])}</p>""")
    for ph in phases:
        done = sum(s["status"] == "done" for s in ph["steps"])
        w(f"""
    <div class="phase {ph["cls"]}">
      <div class="phase-head"><span class="prio">{ph["id"]}</span><div><h3>{escape(ph["title"][lang])}</h3><p>{escape(ph["desc"][lang])}</p></div><span class="count">{done}/{len(ph["steps"])}</span></div>
      <ol class="steps">""")
        for s in ph["steps"]:
            w(
                f'      <li class="step {s["status"]}"><span class="n">{s["n"]}</span><div><h4>{escape(s["title"][lang])}</h4>'
                f'<p>{escape(s["desc"][lang])}</p></div><span class="pill">{t["pill"][s["status"]]}</span></li>'
            )
        w("      </ol>\n    </div>")
    w(f"""    </div>
  </section>

  <section id="copertura" class="alt" aria-labelledby="copertura-t">
    <div class="wrap">
      <span class="eyebrow">{t["cov_eyebrow"]}</span>
      <h2 id="copertura-t">{t["cov_h2"]}</h2>
      <p class="sub">{escape(t["cov_sub"].format(date=date))}</p>
      <ul class="bars">""")
    for ph in phases:
        w(bar(f'{ph["id"]} · {ph["title"][lang]}', ph["steps"]))
    w(bar(t["total"], all_steps, "total"))
    w(f"""</ul>
      <p class="legend"><span><i style="background:var(--blue)"></i>{t["legend"][0]}</span><span><i style="background:color-mix(in srgb, var(--blue) 40%, transparent)"></i>{t["legend"][1]}</span></p>
    </div>
  </section>

  <section id="fuori" aria-labelledby="fuori-t">
    <div class="wrap">
      <span class="eyebrow">{t["out_eyebrow"]}</span>
      <h2 id="fuori-t">{t["out_h2"]}</h2>
      <ul class="outs">""")
    for item in data["out_of_scope"]:
        w(f"<li>{escape(item[lang])}</li>")
    w(f"""</ul>
    </div>
  </section>

  <section class="alt final">
    <div class="wrap">
      <h2>{t["final_h2"]}</h2>
      <p class="sub" style="margin-inline:auto">{escape(t["final_sub"])}</p>
      <div class="cta">
        <a class="btn btn-primary" href="{REPO_URL}">{t["btn_repo"]}</a>
        <a class="btn btn-ghost" href="{REPO_URL}/blob/{BRANCH}/docs/enterprise/ROADMAP.md">{t["btn_plan"]}</a>
      </div>
    </div>
  </section>
</main>

<footer>
  <div class="wrap">
    <span>© 2026 merginmaps-server · {t["footer"]} <a href="https://claude.com/claude-code" rel="noopener">Claude Code</a></span>
    <small>{escape(t["disclaimer"])}</small>
  </div>
</footer>

<button class="to-top" id="to-top" type="button" aria-label="{escape(t["top"])}">{UP}</button>
<script>
  (function () {{
    var root = document.documentElement;
    document.getElementById('themeToggle').addEventListener('click', function () {{
      var dark = root.dataset.theme ? root.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
      root.dataset.theme = dark ? 'light' : 'dark';
      try {{ localStorage.setItem('theme', root.dataset.theme); }} catch (e) {{}}
    }});
    var top = document.getElementById('to-top');
    addEventListener('scroll', function () {{ top.classList.toggle('on', scrollY > 600); }}, {{ passive: true }});
    top.addEventListener('click', function () {{ scrollTo(0, 0); }});
  }})();
</script>
</body>
</html>
""")
    return "\n".join(out)


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "_build")
    with open(os.path.join(HERE, "roadmap.json"), encoding="utf-8") as f:
        data = json.load(f)
    shutil.rmtree(out_dir, ignore_errors=True)
    os.makedirs(out_dir)
    for lang in TEXT:
        with open(os.path.join(out_dir, TEXT[lang]["file"]), "w", encoding="utf-8") as f:
            f.write(render(data, lang))
    # site root opens the roadmap
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(
            '<!doctype html><meta charset="utf-8"><title>merginmaps-server</title>'
            '<meta http-equiv="refresh" content="0; url=roadmap.html">'
            '<link rel="canonical" href="roadmap.html"><a href="roadmap.html">Roadmap</a>\n'
        )
    # plain static files, no Jekyll processing
    open(os.path.join(out_dir, ".nojekyll"), "w").close()
    print(f"Roadmap built in {out_dir}")


if __name__ == "__main__":
    main()
