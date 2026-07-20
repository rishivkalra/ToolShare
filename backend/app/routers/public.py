"""Public share pages — the viral surface.

/kit/{id}   a saved project kit ("raised garden bed — 6 tools, $54/day vs
            $610 to buy") with OG tags so it unfurls nicely when shared
/n/{gh}     a neighborhood scoreboard (tools, $ saved, wanted list) with the
            unlock-progress bar and invite CTA

Server-rendered HTML: no auth, no JS required, crawlable.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from html import escape

from ..deps import Container, get_container
from .neighborhoods import compute_stats

router = APIRouter(tags=["public"], include_in_schema=False)


def _page(title: str, og_desc: str, og_image: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<meta property="og:title" content="{escape(title)}">
<meta property="og:description" content="{escape(og_desc)}">
{f'<meta property="og:image" content="{escape(og_image)}">' if og_image else ''}
<meta name="twitter:card" content="summary">
<meta name="description" content="{escape(og_desc)}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,700;12..96,800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/app/landing.css">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🛠️</text></svg>">
<style>
  .pubwrap {{ max-width: 720px; margin: 0 auto; padding: 24px clamp(16px,4vw,40px) 60px; }}
  .pubcard {{ background:#fff; border:1px solid #E6EAE7; border-radius:22px;
             box-shadow: 0 2px 4px rgba(18,24,28,.06), 0 16px 34px -14px rgba(18,24,28,.18);
             padding: clamp(20px,4vw,34px); margin-top:18px; }}
  .krow {{ display:flex; align-items:center; gap:10px; padding:10px 0;
           border-bottom:1px solid #F0F3F1; font-weight:650; font-size:15px; }}
  .krow:last-child {{ border-bottom:0 }}
  .krow small {{ color:#5F6B66; font-weight:500 }}
  .kprice {{ margin-left:auto; font-family:var(--display); font-weight:800; color:#0A5A34; white-space:nowrap }}
  .bignum {{ font: 800 clamp(30px,6vw,44px) var(--display); color:#0A5A34; letter-spacing:-.03em }}
  .statrow {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:16px; text-align:center; margin:18px 0 }}
  .statrow .lbl {{ color:#5F6B66; font-size:13px }}
  .progress-outer {{ height:12px; background:#EFF7F1; border-radius:999px; overflow:hidden; margin:14px 0 6px }}
  .progress-inner {{ height:100%; background:linear-gradient(135deg,#12925A,#0A5A34); border-radius:999px }}
  .ctas {{ display:flex; flex-wrap:wrap; gap:12px; margin-top:22px }}
</style>
</head><body>
<header class="topbar">
  <a class="brand" href="/"><svg class="brand-mark" viewBox="0 0 32 32" aria-hidden="true">
    <rect x="3" y="13" width="26" height="16" rx="3" fill="#0E7A46"/>
    <path d="M4 14 16 4l12 10" fill="none" stroke="#0E7A46" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M12 22h8M16 18v8" stroke="#fff" stroke-width="2.6" stroke-linecap="round"/></svg>
    <span>ToolShare</span></a>
  <div class="nav-cta"><a class="btn btn-primary" href="/app/#/browse">Open the app</a></div>
</header>
<main class="pubwrap">{body}</main>
</body></html>"""


@router.get("/kit/{kit_id}", response_class=HTMLResponse)
def kit_page(kit_id: str, c: Container = Depends(get_container)):
    kit = c.kits.get(kit_id)
    if not kit:
        body = ('<h1>Kit not found</h1><p style="color:#5F6B66">This project kit '
                'link has expired or never existed.</p>'
                '<div class="ctas"><a class="btn btn-primary btn-big" href="/app/#/project">'
                'Plan your own kit</a></div>')
        return HTMLResponse(_page("Kit not found — ToolShare",
                                  "Plan a project kit on ToolShare.", "", body),
                            status_code=404)

    n_tools = len(kit.items)
    day = kit.total_per_day_cents / 100
    buy = kit.buy_estimate_cents / 100
    title = f"{kit.summary} — {n_tools} tools from neighbors"
    desc = (f"Rent the whole kit from ${day:.0f}/day instead of ~${buy:.0f} to buy. "
            "Matched against tools your neighbors actually have, on ToolShare.")

    rows = "".join(
        f'<div class="krow"><span>{"🧰"}</span><div>{escape(i.name)}'
        + (f'<br><small>✓ {escape(i.listing_title)} · {i.distance_km} km away</small>'
           if i.listing_id else '<br><small>⏳ not listed nearby yet — own one? It could earn for you</small>')
        + '</div>'
        + (f'<span class="kprice">${i.price_per_day_cents / 100:.0f}/day</span>' if i.listing_id else '')
        + '</div>'
        for i in kit.items
    )
    body = f"""
    <span class="kicker">✨ AI project kit</span>
    <h1 style="font-size:clamp(28px,5vw,44px)">{escape(kit.summary)}</h1>
    <div class="pubcard">
      {rows}
      <div style="margin-top:16px;padding:14px 18px;border-radius:14px;background:#FDF3DF;font-weight:700;color:#7A5410">
        Whole kit from <span style="font-family:var(--display);font-size:20px;color:#12181C">${day:.0f}/day</span>
        &nbsp;·&nbsp; vs ~${buy:.0f} to buy it all
      </div>
      <div class="ctas">
        <a class="btn btn-primary btn-big" href="/app/#/project">Rent this kit near you</a>
        <a class="btn btn-ghost btn-big" href="/app/#/list">I own one of these — list it</a>
      </div>
    </div>
    <p style="color:#5F6B66;font-size:13.5px;margin-top:16px">Every rental is backed by the
    ToolShare Guarantee (up to $2,500), deposit holds and ID-verified profiles.</p>"""
    return HTMLResponse(_page(title, desc, "", body))


@router.get("/n/{gh5}", response_class=HTMLResponse)
def neighborhood_page(gh5: str, c: Container = Depends(get_container)):
    s = compute_stats(c, gh5[:5])
    title = f"This neighborhood shares {s.listings} tools — ToolShare"
    desc = (f"{s.listings} tools listed by {s.lenders} neighbors, "
            f"${s.saved_cents / 100:,.0f} of purchases avoided. "
            "See what your street already owns.")
    pct = min(100, round(s.listings * 100 / s.unlock_target))
    wanted = "".join(
        f'<div class="krow"><span>🔥</span><div>{escape(w.term)}'
        f'<br><small>{w.count} neighbor{"s" if w.count > 1 else ""} looked for this recently</small></div>'
        f'<span class="kprice">wanted</span></div>'
        for w in s.wanted
    ) or '<p style="color:#5F6B66">No unmet searches recently — the streets are stocked.</p>'
    gate = (
        f'<p style="font-weight:700;color:#0A5A34">✅ This neighborhood is live — {s.listings} tools and counting.</p>'
        if s.unlocked else
        f"""<p style="font-weight:700">🔓 {s.listings} of {s.unlock_target} tools to fully unlock this neighborhood</p>
        <div class="progress-outer"><div class="progress-inner" style="width:{pct}%"></div></div>
        <p style="color:#5F6B66;font-size:14px">Every listing gets the whole street closer. Invite a neighbor with a garage.</p>"""
    )
    body = f"""
    <span class="kicker">🏡 Neighborhood scoreboard</span>
    <h1 style="font-size:clamp(28px,5vw,44px)">Your street is<br><em>an inventory.</em></h1>
    <div class="pubcard">
      <div class="statrow">
        <div><div class="bignum">{s.listings}</div><div class="lbl">tools listed</div></div>
        <div><div class="bignum">{s.lenders}</div><div class="lbl">lending neighbors</div></div>
        <div><div class="bignum">{s.rentals}</div><div class="lbl">rentals</div></div>
        <div><div class="bignum">${s.saved_cents / 100:,.0f}</div><div class="lbl">purchases avoided</div></div>
      </div>
      {gate}
      <div class="ctas">
        <a class="btn btn-primary btn-big" href="/app/#/list">List a tool</a>
        <a class="btn btn-ghost btn-big" href="/app/#/browse">Browse these tools</a>
      </div>
    </div>
    <div class="pubcard">
      <h2 style="font-size:22px;margin-bottom:8px">Wanted nearby</h2>
      {wanted}
    </div>"""
    return HTMLResponse(_page(title, desc, "", body))
