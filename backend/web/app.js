/* ToolShare web app — no build step, talks to the same-origin API. */
"use strict";

/* ---------------- state, api & helpers ---------------- */

const DEMO_LOC = { lat: 37.7749, lng: -122.4194, label: "Demo neighborhood (SF)" };
const CATEGORIES = {
  power_tools: "🪚", hand_tools: "🔨", garden: "🌱", ladders_access: "🪜",
  painting_decorating: "🎨", plumbing: "🔧", automotive: "🚗",
  cleaning: "🧽", measuring: "📏", other: "🧰",
};
const STATE_LABEL = {
  requested: ["Awaiting approval", "warn"], approved: ["Payment pending", "warn"],
  confirmed: ["Confirmed — arrange pickup", "ok"], picked_up: ["Rental in progress", "ok"],
  returned: ["Returned", "ok"], completed: ["Completed", "ok"],
  declined: ["Declined", "bad"], expired: ["Expired", "bad"],
  cancelled_by_borrower: ["Cancelled by borrower", "bad"],
  cancelled_by_lender: ["Cancelled by owner", "bad"], disputed: ["In dispute", "bad"],
};

const store = {
  get uid() { return localStorage.getItem("ts_uid") || "demo"; },
  set uid(v) { localStorage.setItem("ts_uid", v); },
  // Session token from Google Sign-In on the landing page; when absent we
  // fall back to the staging dev:<uid> identity.
  get token() { return localStorage.getItem("ts_token") || ""; },
  loc: { ...DEMO_LOC, usingDemo: true },
  profiles: {},   // uid -> public profile cache
  photoBlobs: [], // pending listing photos (≤4)
  view: "list",   // browse presentation: list | map
  lastResults: [], // cached search results shared by list + map
  filters: { category: "", availNow: false, sort: "distance" },
};

const PROTECTION_FEE_CENTS = 150;  // mirrors server; server-computed price is authoritative

function authHeader() {
  return `Bearer ${store.token || "dev:" + store.uid}`;
}

async function api(method, path, body) {
  const resp = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json", Authorization: authHeader() },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return handleResp(resp);
}

async function apiUpload(path, blob, filename) {
  const form = new FormData();
  form.append("file", blob, filename);
  const resp = await fetch(path, {
    method: "POST",
    headers: { Authorization: authHeader() },
    body: form,
  });
  return handleResp(resp);
}

async function handleResp(resp) {
  const data = resp.status === 204 ? null : await resp.json().catch(() => null);
  if (resp.status === 401 && store.token) {
    localStorage.removeItem("ts_token");
    location.href = "/";  // session expired — back to the landing sign-in
    return null;
  }
  if (!resp.ok) {
    const detail = data && data.detail
      ? (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail))
      : resp.statusText;
    const err = new Error(detail);
    err.status = resp.status;
    throw err;
  }
  return data;
}

async function profileOf(uid) {
  if (!store.profiles[uid]) {
    store.profiles[uid] = await api("GET", `/v1/users/${encodeURIComponent(uid)}`).catch(() => ({ uid, display_name: uid }));
  }
  return store.profiles[uid];
}

const $ = (sel) => document.querySelector(sel);
const dollars = (c) => `$${(c / 100).toFixed(2).replace(/\.00$/, "")}`;
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
const initial = (name) => (name || "?").trim()[0] || "?";

function toast(msg, isErr = false) {
  const el = document.createElement("div");
  el.className = "toast" + (isErr ? " err" : "");
  el.textContent = msg;
  $("#toast-root").appendChild(el);
  setTimeout(() => el.remove(), 4200);
}

/* ---------------- in-app sign-in ---------------- */

async function authConfig() {
  if (!store.authCfg) {
    store.authCfg = await api("GET", "/v1/auth/config")
      .catch(() => ({ google_client_id: "", dev_auth: true }));
  }
  return store.authCfg;
}

async function openSignIn() {
  const cfg = await authConfig();
  modal(`
    <div class="inner" style="text-align:center;padding-top:34px">
      <button class="closex" style="position:absolute;top:10px;right:10px" onclick="closeModal()">✕</button>
      <span class="kicker">🏡 Join your neighborhood</span>
      <h2>Sign in to ToolShare</h2>
      <p style="color:var(--muted);margin:8px 0 20px">One account for renting, lending,
        your trust badges and your $10 invites.</p>
      <div id="gsi-app" style="display:flex;justify-content:center;min-height:44px"></div>
      ${cfg.dev_auth ? `
        <div style="margin-top:18px">
          <button class="btn" id="demo-continue">Continue with a demo account</button>
          <p class="fineprint">Staging only — demo identities disappear at launch.</p>
        </div>` : ""}
    </div>`);
  if (cfg.google_client_id) {
    const mount = () => {
      google.accounts.id.initialize({
        client_id: cfg.google_client_id,
        callback: async (resp) => {
          try {
            const d = await api("POST", "/v1/auth/google", {
              credential: resp.credential,
              ref: localStorage.getItem("ts_ref") || "",
            });
            localStorage.setItem("ts_token", d.token);
            localStorage.setItem("ts_uid", d.uid);
            location.reload();
          } catch (e) { toast(e.message, true); }
        },
      });
      google.accounts.id.renderButton($("#gsi-app"),
        { theme: "outline", size: "large", shape: "pill", text: "continue_with" });
    };
    if (window.google && google.accounts) mount();
    else {
      const s = document.createElement("script");
      s.src = "https://accounts.google.com/gsi/client"; s.async = true;
      s.onload = mount;
      document.head.appendChild(s);
    }
  } else if (cfg.dev_auth) {
    $("#gsi-app").innerHTML = `<span class="opt">Google sign-in goes live once the OAuth client is configured.</span>`;
  }
  const demo = $("#demo-continue");
  if (demo) demo.onclick = () => {
    localStorage.removeItem("ts_token");
    localStorage.setItem("ts_uid", "demo");
    location.reload();
  };
}

function renderWhoami() {
  const me = store.me || {};
  const name = store.token ? (me.display_name || "Neighbor") : (me.display_name || "Guest");
  $("#whoami-name").textContent = name;
  $("#whoami-dot").innerHTML = me.photo_url
    ? `<img src="${esc(me.photo_url)}" alt="" referrerpolicy="no-referrer">`
    : esc(initial(name));
}

function handleAuthRequired(e) {
  // Signed-out visitor hit an auth-only action: offer sign-in, not a raw 401.
  if (e.status === 401 && !store.token) {
    openSignIn();
    return true;
  }
  return false;
}

function handleCardRequired(e) {
  if (handleAuthRequired(e)) return true;
  if (e.status === 402) {
    toast("💳 Add a payment method first — it backs the deposit that protects owners.", true);
    location.hash = "#/profile";
    return true;
  }
  return false;
}

function isoInDays(n) {
  return new Date(Date.now() + n * 86400000).toISOString().slice(0, 10);
}

function daysBetween(startIso, endIso) {
  return Math.round((new Date(endIso) - new Date(startIso)) / 86400000) + 1;
}

/* ---------------- routing ---------------- */

const TABS = ["browse", "project", "list", "rentals", "profile"];

function route() {
  const tab = (location.hash.replace("#/", "") || "browse").split("?")[0];
  const active = TABS.includes(tab) ? tab : "browse";
  TABS.forEach((t) => $(`#tab-${t}`).classList.toggle("active", t === active));
  document.querySelectorAll("[data-tab]").forEach((a) =>
    a.classList.toggle("active", a.dataset.tab === active));
  if (active === "browse") { loadBrowse(); loadHood(); }
  if (active === "list") loadWanted();
  if (active === "rentals") loadRentals();
  if (active === "profile") loadProfile();
  window.scrollTo({ top: 0 });
}
window.addEventListener("hashchange", route);

/* ---------------- location ---------------- */

function renderLocRow() {
  const other = store.loc.usingDemo ? "use my location" : "use demo neighborhood";
  $("#locrow").innerHTML = `📍 ${esc(store.loc.label)} · <button id="loc-toggle">${other}</button>`;
  $("#loc-toggle").onclick = toggleLocation;
}

function toggleLocation() {
  if (!store.loc.usingDemo) {
    store.loc = { ...DEMO_LOC, usingDemo: true };
    renderLocRow(); loadBrowse();
    return;
  }
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      store.loc = { lat: pos.coords.latitude, lng: pos.coords.longitude, label: "Your location", usingDemo: false };
      renderLocRow(); loadBrowse();
    },
    () => toast("Location permission denied — staying on the demo neighborhood", true),
  );
}

/* ---------------- browse ---------------- */

async function loadBrowse() {
  const grid = $("#browse-results");
  grid.innerHTML = `<div class="skeleton"><span class="spin">🛠️</span> Finding tools near you…</div>`;
  try {
    const q = $("#search-input").value.trim();
    const params = new URLSearchParams({ lat: store.loc.lat, lng: store.loc.lng, radius_km: 8 });
    if (q) params.set("q", q);
    if (store.filters.category) params.set("category", store.filters.category);
    store.lastResults = await api("GET", `/v1/listings/search?${params}`);
    renderFilterbar();
    renderBrowse();
  } catch (e) {
    grid.innerHTML = `<div class="empty">⚠️ ${esc(e.message)}</div>`;
  }
}

function renderFilterbar() {
  const bar = $("#filterbar");
  const f = store.filters;
  bar.innerHTML = `
    <button class="fchip ${!f.category ? "on" : ""}" data-cat="">All</button>
    ${Object.keys(CATEGORIES).map((c) =>
      `<button class="fchip ${f.category === c ? "on" : ""}" data-cat="${c}">${CATEGORIES[c]} ${c.replace(/_/g, " ")}</button>`).join("")}
    <button class="fchip ${f.availNow ? "on" : ""}" id="f-avail">✅ Available now</button>
    <select id="f-sort" class="fsort">
      <option value="distance" ${f.sort === "distance" ? "selected" : ""}>Nearest first</option>
      <option value="price" ${f.sort === "price" ? "selected" : ""}>Cheapest first</option>
    </select>`;
  bar.querySelectorAll("[data-cat]").forEach((b) => {
    b.onclick = () => { f.category = b.dataset.cat; loadBrowse(); };
  });
  $("#f-avail").onclick = () => { f.availNow = !f.availNow; renderFilterbar(); renderBrowse(); };
  $("#f-sort").onchange = (e) => { f.sort = e.target.value; renderBrowse(); };
}

function renderBrowse() {
  const grid = $("#browse-results");
  let results = store.lastResults;
  if (store.filters.availNow) results = results.filter((r) => !r.rented_until);
  if (store.filters.sort === "price") {
    results = [...results].sort((a, b) => a.listing.price_per_day_cents - b.listing.price_per_day_cents);
  }
  const mapMode = store.view === "map";
  $("#view-list").classList.toggle("active", !mapMode);
  $("#view-map").classList.toggle("active", mapMode);
  $("#map").hidden = !mapMode;
  grid.hidden = mapMode;
  if (mapMode) { renderMap(results); return; }
  const q = $("#search-input").value.trim();
  if (!results.length) {
    grid.innerHTML = `<div class="empty"><span class="big">🌱</span>No tools here yet.<br>
      ${q ? `<button class="btn btn-primary" id="alert-me" style="margin-top:12px">🔔 Alert me when a neighbor lists “${esc(q)}”</button>`
          : `Be the first — list one from the <b>List</b> tab.`}</div>`;
    const ab = $("#alert-me");
    if (ab) ab.onclick = async () => {
      try {
        await api("POST", "/v1/searches", { term: q, lat: store.loc.lat, lng: store.loc.lng });
        toast("You'll get a notification the moment one is listed nearby 🔔");
        ab.disabled = true;
      } catch (e) { if (!handleAuthRequired(e)) toast(e.message, true); }
    };
    return;
  }
  grid.innerHTML = results.map(toolCard).join("");
  grid.querySelectorAll(".toolcard").forEach((el) => {
    el.onclick = (ev) => {
      if (ev.target.closest("[data-fav]")) return;
      openListing(el.dataset.id);
    };
  });
  grid.querySelectorAll("[data-fav]").forEach((btn) => {
    btn.onclick = () => toggleFav(btn.dataset.fav, btn);
  });
}

/* ---------------- onboarding & setup checklist ---------------- */

function maybeOnboard() {
  if (localStorage.getItem("ts_onboarded")) return;
  if (store.me && store.me.display_name && store.me.card_on_file) {
    localStorage.setItem("ts_onboarded", "1");  // returning power user
    return;
  }
  modal(`
    <div class="inner" style="padding-top:30px">
      <span class="kicker">👋 Welcome to the neighborhood</span>
      <h2>Every tool on your street,<br>one tap away.</h2>
      <p style="color:var(--muted);margin:10px 0 16px">Rent from neighbors for a few
        dollars a day — or turn your idle tools into income. Two quick questions:</p>
      <label style="font-weight:700;font-size:14px">What should neighbors call you?
        <input id="ob-name" placeholder="e.g. Maya R." style="margin-top:6px;font-weight:400">
      </label>
      <p style="font-weight:700;font-size:14px;margin-top:16px">What brings you here?</p>
      <div class="obrow">
        <button class="btn obchoice" data-role="borrow">🔍 <b>Borrow tools</b><span>for projects, without buying</span></button>
        <button class="btn obchoice" data-role="lend">🧰 <b>Lend my tools</b><span>earn from the garage</span></button>
        <button class="btn obchoice" data-role="both">🔁 <b>Both</b><span>the full neighbor experience</span></button>
      </div>
      <p class="fineprint" style="margin-top:14px">You can change everything later in Profile.</p>
    </div>`);
  document.querySelectorAll(".obchoice").forEach((btn) => {
    btn.onclick = async () => {
      const name = $("#ob-name").value.trim();
      if (name) {
        await api("PATCH", "/v1/users/me", { display_name: name }).catch(() => {});
        if (store.me) store.me.display_name = name;
        renderWhoami();
      }
      localStorage.setItem("ts_onboarded", "1");
      closeModal();
      const role = btn.dataset.role;
      if (role === "lend") { location.hash = "#/list"; toast("Snap a photo of any tool — the AI writes the listing ✨"); }
      else { location.hash = "#/browse"; toast(name ? `Welcome, ${name}! Here's what your neighbors share 🏡` : "Here's what your neighbors share 🏡"); }
      renderChecklist();
    };
  });
}

function checklistItems() {
  const me = store.me || {};
  return [
    { done: !!me.display_name, label: "Add your name", hash: "#/profile" },
    { done: !!me.card_on_file, label: "Add a payment method", hash: "#/profile" },
    { done: !!me.id_verified, label: "Verify your ID", hash: "#/profile" },
  ];
}

function renderChecklist() {
  const box = $("#checklist-box");
  if (!box) return;
  // No profile (signed-out visitor in prod) -> nothing actionable to show.
  if (!store.me || localStorage.getItem("ts_checklist_done")) { box.innerHTML = ""; return; }
  const items = checklistItems();
  const done = items.filter((i) => i.done).length;
  if (done === items.length) { box.innerHTML = ""; return; }
  box.innerHTML = `<div class="checklist">
    <div class="cl-head"><b>🚀 Get set up — ${done} of ${items.length}</b>
      <button class="cl-x" id="cl-dismiss" title="Dismiss">✕</button></div>
    ${items.map((i) => `
      <a class="cl-item ${i.done ? "done" : ""}" href="${i.hash}">
        <span>${i.done ? "✅" : "⬜"}</span>${i.label}</a>`).join("")}
  </div>`;
  $("#cl-dismiss").onclick = () => {
    localStorage.setItem("ts_checklist_done", "1");
    box.innerHTML = "";
  };
}

/* ---------------- neighborhood bar & wanted-nearby ---------------- */

async function loadHood() {
  const bar = $("#hoodbar");
  try {
    const s = await api("GET",
      `/v1/neighborhoods?lat=${store.loc.lat}&lng=${store.loc.lng}`);
    store.hood = s;
    const inviteUrl = `${location.origin}/?ref=${encodeURIComponent(store.uid)}`;
    const pct = Math.min(100, Math.round(s.listings * 100 / s.unlock_target));
    bar.innerHTML = `<div class="hoodbar">
      <span class="hb-text">${s.unlocked
        ? `🏡 Your neighborhood is live — ${s.listings} tools · $${(s.saved_cents / 100).toFixed(0)} in purchases avoided`
        : `🔓 ${s.listings} of ${s.unlock_target} tools to unlock your neighborhood`}</span>
      <a href="${esc(s.page_path)}" target="_blank">scoreboard ↗</a>
      <button id="hb-invite">invite a neighbor (+$10 each)</button>
      ${s.unlocked ? "" : `<div class="hb-bar"><div class="hb-fill" style="width:${pct}%"></div></div>
      <span class="hb-sub">Every tool listed gets the whole street closer. Inviting a garage-owning neighbor is worth $10 to you both.</span>`}
    </div>`;
    $("#hb-invite").onclick = async () => {
      if (navigator.share) {
        navigator.share({ title: "ToolShare — rent any tool from a neighbor", url: inviteUrl }).catch(() => {});
      } else {
        await navigator.clipboard.writeText(inviteUrl).catch(() => {});
        toast("Invite link copied — worth $10 to you and your neighbor 🎁");
      }
    };
  } catch { bar.innerHTML = ""; }
}

async function loadWanted() {
  const box = $("#wanted-box");
  try {
    const s = store.hood || await api("GET",
      `/v1/neighborhoods?lat=${store.loc.lat}&lng=${store.loc.lng}`);
    if (!s.wanted.length) { box.innerHTML = ""; return; }
    box.innerHTML = `<div class="wantedbox">
      <div class="wb-title">🔥 Wanted nearby — neighbors searched for these and found nothing</div>
      <div class="chips">${s.wanted.map((w) =>
        `<button class="wantedchip" data-term="${esc(w.term)}"><b>${esc(w.term)}</b>${w.count > 1 ? ` · ${w.count} asks` : ""}</button>`).join("")}</div>
    </div>`;
    box.querySelectorAll(".wantedchip").forEach((el) => {
      el.onclick = () => {
        const f = $("#list-form");
        f.title.value = el.dataset.term;
        f.title.focus();
        toast("Pre-filled — neighbors are already searching for this 🔥");
      };
    });
  } catch { box.innerHTML = ""; }
}

/* ---------------- map view (vendored Leaflet + OSM tiles) ---------------- */

let map = null, mapMarkers = [];

function renderMap(results) {
  if (typeof L === "undefined") { toast("Map library failed to load", true); return; }
  if (!map) {
    map = L.map("map", { scrollWheelZoom: true });
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(map);
  }
  map.setView([store.loc.lat, store.loc.lng], 14);
  setTimeout(() => map.invalidateSize(), 60);  // container was just unhidden
  mapMarkers.forEach((m) => m.remove());
  mapMarkers = results.map((r) => {
    const l = r.listing;
    const icon = L.divIcon({
      className: "",
      html: `<div class="pricepin">${dollars(l.price_per_day_cents)} · ${esc(l.title.slice(0, 18))}${l.title.length > 18 ? "…" : ""}</div>`,
      iconSize: [0, 0],
    });
    return L.marker([l.approx_lat, l.approx_lng], { icon })
      .addTo(map)
      .on("click", () => openListing(l.id));
  });
  // Approximate-location reminder ring around the searcher.
  const me = L.circleMarker([store.loc.lat, store.loc.lng],
    { radius: 7, color: "#0E7A46", fillColor: "#12925A", fillOpacity: 0.9 }).addTo(map);
  mapMarkers.push(me);
}

function photoHtml(l, cls = "") {
  return l.photos && l.photos.length
    ? `<img src="${esc(l.photos[0])}" alt="${esc(l.title)}" loading="lazy">`
    : `<span class="ph ${cls}">${CATEGORIES[l.category] || "🧰"}</span>`;
}

function isFav(id) {
  return !!(store.me && store.me.favorites && store.me.favorites.includes(id));
}

async function toggleFav(id, btn) {
  try {
    const r = await api("PUT", `/v1/listings/${id}/favorite`);
    if (r === null) return;
    if (store.me) {
      store.me.favorites = store.me.favorites || [];
      if (r.favorited) store.me.favorites.push(id);
      else store.me.favorites = store.me.favorites.filter((x) => x !== id);
    }
    btn.textContent = r.favorited ? "❤️" : "🤍";
    toast(r.favorited ? "Saved to your favorites ❤️" : "Removed from favorites");
  } catch (e) { if (!handleAuthRequired(e)) toast(e.message, true); }
}

function toolCard(r) {
  const l = r.listing;
  const rating = l.rating_count > 0 ? `<span class="chip">★ ${l.rating_avg}</span>` : "";
  const deposit = l.deposit_cents > 0 ? `<span class="chip">🛡 ${dollars(l.deposit_cents)} deposit</span>` : "";
  const instant = l.instant_book ? `<span class="chip warn">⚡ instant</span>` : "";
  const avail = r.rented_until
    ? `<span class="chip bad">⏳ back ${esc(String(r.rented_until).slice(5))}</span>`
    : `<span class="chip ok">✅ available</span>`;
  return `<article class="toolcard" data-id="${esc(l.id)}">
    <div class="toolphoto">${photoHtml(l)}
      <span class="pricepill">${dollars(l.price_per_day_cents)}<small>/day</small></span>
      <button class="favbtn" data-fav="${esc(l.id)}" title="Save">${isFav(l.id) ? "❤️" : "🤍"}</button>
    </div>
    <div class="body">
      <h3>${esc(l.title)}</h3>
      <div class="meta">
        ${avail}<span class="chip">📍 ${r.distance_km.toFixed(1)} km</span>${rating}${deposit}${instant}
      </div>
    </div>
  </article>`;
}

/* ---------------- listing modal & booking ---------------- */

/* Availability calendar: shared by the booking modal (pick a free range) and
   the owner blackout editor (toggle blocked days). */

function calBlockedSet(avail) {
  const blocked = new Set(avail.blackout_dates || []);
  for (const r of avail.booked || []) {
    for (let d = new Date(r.start_date + "T00:00Z"); ; d.setUTCDate(d.getUTCDate() + 1)) {
      const iso = d.toISOString().slice(0, 10);
      blocked.add(iso);
      if (iso >= r.end_date) break;
    }
  }
  return blocked;
}

function calHtml(ym, blocked, sel, opts = {}) {
  const [y, m] = ym;
  const today = new Date().toISOString().slice(0, 10);
  const first = new Date(Date.UTC(y, m, 1));
  const label = first.toLocaleDateString("en-US", { month: "long", year: "numeric", timeZone: "UTC" });
  let cells = ["S", "M", "T", "W", "T", "F", "S"].map((d) => `<div class="dow">${d}</div>`).join("");
  cells += `<div></div>`.repeat(first.getUTCDay());
  const daysInMonth = new Date(Date.UTC(y, m + 1, 0)).getUTCDate();
  for (let day = 1; day <= daysInMonth; day++) {
    const iso = `${y}-${String(m + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    const past = iso <= today && !(opts.allowToday && iso === today);
    const isBlocked = blocked.has(iso);
    const cls = ["cal-day"];
    if (past) cls.push("off");
    else if (isBlocked) cls.push("blocked");
    if (iso === today) cls.push("today");
    if (sel.start && iso === sel.start) cls.push("sel");
    if (sel.end && iso === sel.end) cls.push("sel");
    if (sel.start && sel.end && iso > sel.start && iso < sel.end) cls.push("inrange");
    cells += `<div class="${cls.join(" ")}" ${past ? "" : `data-day="${iso}"`}>${day}</div>`;
  }
  return `<div class="cal">
    <div class="cal-head">
      <button data-cal="prev">‹</button><b>${label}</b><button data-cal="next">›</button>
    </div>
    <div class="cal-grid">${cells}</div>
    <div class="cal-legend">
      <span><i style="background:var(--green-grad)"></i>selected</span>
      <span><i style="background:var(--wash);text-decoration:line-through">&nbsp;</i>unavailable</span>
    </div>
  </div>`;
}

function rangeIsFree(start, end, blocked) {
  for (let d = new Date(start + "T00:00Z"); ; d.setUTCDate(d.getUTCDate() + 1)) {
    const iso = d.toISOString().slice(0, 10);
    if (blocked.has(iso)) return false;
    if (iso >= end) return true;
  }
}

async function openListing(id) {
  const l = await api("GET", `/v1/listings/${id}`).catch((e) => (toast(e.message, true), null));
  if (!l) return;
  const [owner, avail] = await Promise.all([
    profileOf(l.owner_uid),
    api("GET", `/v1/listings/${id}/availability`).catch(() => ({ booked: [], blackout_dates: [] })),
  ]);
  const blocked = calBlockedSet(avail);
  const now = new Date();
  let calYM = [now.getUTCFullYear(), now.getUTCMonth()];
  // Preselect tomorrow when it's free, so one tap can already request.
  const sel = { start: null, end: null };
  if (!blocked.has(isoInDays(1))) { sel.start = isoInDays(1); sel.end = isoInDays(1); }

  const fee = (rental) => Math.max(Math.round(rental * 0.15), 100);
  const render = () => {
    $("#m-cal").innerHTML = calHtml(calYM, blocked, sel);
    bindCal();
    const box = $("#m-total");
    const btn = $("#m-request");
    if (!sel.start) {
      box.innerHTML = `<span class="opt">Pick your rental dates on the calendar.</span>`;
      btn.disabled = true;
      return;
    }
    const end = sel.end || sel.start;
    const days = daysBetween(sel.start, end);
    let rental = l.price_per_day_cents * days;
    let weeklyNote = "";
    if (l.price_per_week_cents > 0 && days >= 7) {
      const tiered = Math.floor(days / 7) * l.price_per_week_cents + (days % 7) * l.price_per_day_cents;
      if (tiered < rental) {
        weeklyNote = ` <span class="chip ok">weekly rate — save ${dollars(rental - tiered)}</span>`;
        rental = tiered;
      }
    }
    box.innerHTML =
      `<b>${esc(sel.start)} → ${esc(end)}</b> · ${days} day${days > 1 ? "s" : ""}${weeklyNote}<br>` +
      `${dollars(rental)} rental + ${dollars(fee(rental))} service fee + ${dollars(PROTECTION_FEE_CENTS)} protection` +
      (l.deposit_cents ? `<br>+ ${dollars(l.deposit_cents)} refundable deposit hold (released on safe return)` : "") +
      `<div class="grand">Total ${dollars(rental + fee(rental) + PROTECTION_FEE_CENTS)}</div>
       <div class="protectline">🛡️ ToolShare Guarantee — covered up to $2,500 against damage or theft</div>`;
    btn.disabled = false;
    btn.textContent = (l.instant_book && store.me && store.me.id_verified)
      ? "⚡ Book now — no approval wait"
      : "Request to rent";
  };
  const bindCal = () => {
    $("#m-cal [data-cal=prev]").onclick = () => { calYM = prevYM(calYM); render(); };
    $("#m-cal [data-cal=next]").onclick = () => { calYM = nextYM(calYM); render(); };
    document.querySelectorAll("#m-cal [data-day]:not(.blocked)").forEach((el) => {
      el.onclick = () => {
        const d = el.dataset.day;
        if (!sel.start || sel.end) { sel.start = d; sel.end = null; }
        else if (d >= sel.start && rangeIsFree(sel.start, d, blocked)) sel.end = d;
        else { sel.start = d; sel.end = null; }
        render();
      };
    });
  };
  const thumbs = (l.photos || []).length > 1
    ? `<div class="thumbs">${l.photos.map((p, i) =>
        `<img src="${esc(p)}" data-thumb="${i}" class="${i === 0 ? "on" : ""}" alt="">`).join("")}</div>`
    : "";
  modal(`
    <div class="mphoto" id="m-hero">${photoHtml(l)}
      <button class="closex" onclick="closeModal()">✕</button>
    </div>
    ${thumbs}
    <div class="inner">
      <h2>${esc(l.title)}
        ${avail.booked.some((b) => b.start_date <= isoInDays(0) && b.end_date >= isoInDays(0))
          ? '<span class="chip bad">⏳ out on a rental</span>'
          : '<span class="chip ok">✅ available</span>'}</h2>
      <p style="color:var(--muted);margin:6px 0 2px">
        ${CATEGORIES[l.category] || "🧰"} ${esc(l.category.replace(/_/g, " "))} · condition: ${esc(l.condition)}
        ${l.rating_count ? ` · ★ ${l.rating_avg} (${l.rating_count})` : ""}
        ${l.instant_book ? ' <span class="instantchip">⚡ Instant book</span>' : ""}</p>
      <p style="margin:6px 0 2px;font-size:14px">Owner: <b>${esc(owner.display_name || l.owner_uid)}</b>
        ${owner.id_verified ? `<span class="chip ok">🪪 ID verified</span>` : ""}
        ${owner.rating_count ? `<span class="chip ok">★ ${owner.rating_avg}</span>` : `<span class="chip">new lender</span>`}</p>
      ${l.description ? `<p style="margin:10px 0">${esc(l.description)}</p>` : ""}
      <div id="m-cal"></div>
      <div class="totalbox" id="m-total"></div>
      <button class="btn btn-primary btn-big" id="m-request" style="width:100%">Request to rent</button>
      <p class="fineprint">You're only charged if the owner accepts. Exact pickup address is shared after confirmation.</p>
      <button class="report-link" id="m-report">Report this listing</button>
    </div>
  `);
  render();
  document.querySelectorAll("[data-thumb]").forEach((img) => {
    img.onclick = () => {
      $("#m-hero").innerHTML = `<img src="${esc(l.photos[+img.dataset.thumb])}" alt="${esc(l.title)}">
        <button class="closex" onclick="closeModal()">✕</button>`;
      document.querySelectorAll("[data-thumb]").forEach((t) => t.classList.toggle("on", t === img));
    };
  });
  $("#m-report").onclick = () => reportTarget("listing", l.id);
  $("#m-request").onclick = async () => {
    try {
      const b = await api("POST", "/v1/bookings",
        { listing_id: l.id, start_date: sel.start, end_date: sel.end || sel.start });
      closeModal();
      toast(b.state === "confirmed"
        ? "⚡ Booked instantly — it's yours! Arrange pickup in chat."
        : "Requested! The owner has 24h to accept — track it in Rentals.");
      location.hash = "#/rentals";
    } catch (e) {
      if (handleCardRequired(e)) { closeModal(); return; }
      toast(e.message, true);
    }
  };
}

const prevYM = ([y, m]) => (m === 0 ? [y - 1, 11] : [y, m - 1]);
const nextYM = ([y, m]) => (m === 11 ? [y + 1, 0] : [y, m + 1]);

function modal(html) {
  $("#modal-root").innerHTML = `<div class="modal-backdrop" onclick="if(event.target===this)closeModal()"><div class="modal">${html}</div></div>`;
}
window.closeModal = () => { $("#modal-root").innerHTML = ""; };

async function reportTarget(type, id) {
  const reason = prompt("What's wrong? Your report goes straight to the ToolShare team.");
  if (!reason || reason.trim().length < 5) return;
  try {
    await api("POST", "/v1/reports", { target_type: type, target_id: id, reason: reason.trim() });
    toast("Report received — we review every one. Thank you. 🛡️");
  } catch (e) { toast(e.message, true); }
}
window.reportTarget = reportTarget;

/* ---------------- project kit ---------------- */

async function planProject() {
  const description = $("#project-input").value.trim();
  if (description.length < 10) { toast("Describe your project in a sentence or two", true); return; }
  const btn = $("#plan-btn");
  btn.disabled = true; btn.textContent = "Planning your kit…";
  $("#kit-results").innerHTML = `<div class="skeleton"><span class="spin">✨</span> Gemini is planning your tool list…</div>`;
  try {
    const kit = await api("POST", "/v1/projects/plan", { description, lat: store.loc.lat, lng: store.loc.lng });
    renderKit(kit);
  } catch (e) {
    $("#kit-results").innerHTML = "";
    toast(e.message, true);
  } finally {
    btn.disabled = false; btn.textContent = "Build my tool kit";
  }
}

function renderKit(kit) {
  const rentable = kit.kit.filter((i) => i.matches.length);
  const items = kit.kit.map((item) => {
    const best = item.matches[0];
    const match = best
      ? `<div class="match">✅ ${esc(best.title)} · ${dollars(best.price_per_day_cents)}/day nearby</div>`
      : `<div class="why">⏳ No neighbor has this yet — we'll flag it as wanted</div>`;
    return `<div class="kititem" ${best ? `data-listing="${esc(best.id)}" style="cursor:pointer"` : ""}>
      <span class="stat">${CATEGORIES[item.tool.category] || "🧰"}</span>
      <div class="body">
        <div class="name">${esc(item.tool.name)}${item.tool.optional ? ' <span class="chip">optional</span>' : ""}</div>
        <div class="why">${esc(item.tool.why)}</div>
        ${match}
      </div>
    </div>`;
  }).join("");
  const total = kit.total_estimated_per_day_cents;
  $("#kit-results").innerHTML = `
    <div class="kit-summary">${esc(kit.plan.project_summary)}</div>
    ${total ? `<div class="kit-total">Rent the kit from ${dollars(total)}/day — instead of buying it all.</div>` : ""}
    <div class="kitlist">${items}</div>
    ${rentable.length ? `<div class="kit-cta">
        <button class="btn btn-primary btn-big" id="kit-checkout">Request whole kit · ${rentable.length} tools</button>
        <span class="opt">for tomorrow — owners confirm individually</span>
      </div>` : ""}
    ${kit.kit_id ? `<div class="sharekit">
        <button class="btn" id="kit-share">🔗 Share this kit</button>
        <button class="btn" id="kit-guide">📖 Step-by-step build guide</button>
        <span class="opt">the guide references the exact tools in your kit</span>
      </div>` : ""}
    <div class="kit-notes">
      ${kit.missing_tools.length ? `⏳ Not nearby yet: <b>${kit.missing_tools.map(esc).join(", ")}</b>. We'll notify you when a neighbor lists one.<br>` : ""}
      ${kit.plan.consumables_note ? `🛒 ${esc(kit.plan.consumables_note)}<br>` : ""}
      ${kit.plan.safety_note ? `⚠️ ${esc(kit.plan.safety_note)}` : ""}
    </div>`;
  document.querySelectorAll(".kititem[data-listing]").forEach((el) => {
    el.onclick = () => openListing(el.dataset.listing);
  });
  const gbtn = $("#kit-guide");
  if (gbtn) gbtn.onclick = async () => {
    gbtn.disabled = true; gbtn.textContent = "📖 Writing your guide…";
    try {
      const g = await api("POST", `/v1/projects/${kit.kit_id}/guide`);
      showGuide(g);
    } catch (e) { toast(e.message, true); }
    finally { gbtn.disabled = false; gbtn.textContent = "📖 Step-by-step build guide"; }
  };
  const share = $("#kit-share");
  if (share) share.onclick = async () => {
    const url = location.origin + kit.share_path;
    if (navigator.share) {
      navigator.share({ title: kit.plan.project_summary, url }).catch(() => {});
    } else {
      await navigator.clipboard.writeText(url).catch(() => {});
      toast("Kit link copied — send it to a friend 🔗");
    }
  };
  const co = $("#kit-checkout");
  if (co) co.onclick = async () => {
    co.disabled = true; co.textContent = "Requesting kit…";
    try {
      const ids = rentable.map((i) => i.matches[0].id);
      const res = await api("POST", "/v1/projects/checkout", { listing_ids: ids, start_date: isoInDays(1), end_date: isoInDays(1) });
      toast(res.failed === 0
        ? `Requested ${res.requested} tools — owners have 24h to accept.`
        : `${res.requested} requested, ${res.failed} unavailable`);
      location.hash = "#/rentals";
    } catch (e) {
      co.disabled = false; co.textContent = "Request whole kit";
      if (handleCardRequired(e)) return;
      toast(e.message, true);
    }
  };
}

function showGuide(g) {
  const steps = g.steps.map((s, i) => `
    <div class="gstep">
      <div class="gnum">${i + 1}</div>
      <div>
        <div class="gtitle">${esc(s.title)}
          ${(s.tools || []).map((t) => `<span class="chip ok">🧰 ${esc(t)}</span>`).join(" ")}</div>
        <div class="gdetail">${esc(s.detail)}</div>
        ${s.safety ? `<div class="gsafety">⚠️ ${esc(s.safety)}</div>` : ""}
      </div>
    </div>`).join("");
  modal(`
    <div class="inner">
      <button class="closex" style="position:absolute;top:10px;right:10px" onclick="closeModal()">✕</button>
      <span class="kicker">📖 Your build guide</span>
      <h2>${esc(g.title)}</h2>
      <p style="color:var(--muted);margin:6px 0 12px">
        ${esc(g.difficulty)} · ~${g.est_hours}h with the tools in your kit</p>
      <div class="guide">${steps}</div>
      ${g.finish_note ? `<p class="protectline" style="margin-top:14px">🎉 ${esc(g.finish_note)}</p>` : ""}
    </div>`);
}

/* ---------------- list a tool (with photo) ---------------- */

function bindPhotoPicker() {
  const pick = $("#photopick");
  const input = $("#photo-input");
  pick.onclick = () => input.click();
  input.onchange = async () => {
    const files = [...(input.files || [])].slice(0, 4);
    if (!files.length) return;
    store.photoBlobs = await Promise.all(files.map((f) => downscale(f, 1280, 0.85)));
    const url = URL.createObjectURL(store.photoBlobs[0]);
    $("#photopick-icon").outerHTML = `<img id="photopick-icon" src="${url}" alt="preview">`;
    $("#photopick-label").textContent = files.length > 1
      ? `✨ Identifying your tool… (${files.length} photos)`
      : "✨ Identifying your tool…";
    identifyTool(store.photoBlobs[0]);
  };
}

async function priceHint() {
  const hint = $("#price-hint");
  try {
    const cat = $("#category-select").value;
    const s = await api("GET",
      `/v1/listings/price-suggestion?category=${cat}&lat=${store.loc.lat}&lng=${store.loc.lng}`);
    hint.textContent = s.based_on >= 3
      ? `💡 ${s.based_on} similar tools nearby go for ~${dollars(s.suggested_per_day_cents)}/day`
      : `💡 Suggested for this category: ~${dollars(s.suggested_per_day_cents)}/day`;
  } catch { hint.textContent = ""; }
}

async function identifyTool(blob) {
  // Photo-to-listing: Gemini names the tool and drafts the whole form.
  try {
    const s = await apiUpload("/v1/listings/identify", blob, "tool.jpg");
    const f = $("#list-form");
    f.title.value = s.title;
    f.category.value = s.category;
    if (s.description) f.description.value = s.description;
    f.price.value = (s.price_per_day_cents / 100).toFixed(0);
    f.deposit.value = (s.deposit_cents / 100).toFixed(0);
    $("#photopick-label").textContent = "Looks great — tap to change";
    priceHint();
    toast(s.confidence >= 0.5
      ? `✨ Recognized: ${s.title} — check the details and hit list!`
      : "✨ Best guess filled in — please double-check the details", false);
  } catch {
    $("#photopick-label").textContent = "Looks great — tap to change";
  }
}

function downscale(file, maxDim, quality) {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
      const scale = Math.min(1, maxDim / Math.max(img.width, img.height));
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(img.width * scale);
      canvas.height = Math.round(img.height * scale);
      canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
      canvas.toBlob((b) => resolve(b || file), "image/jpeg", quality);
    };
    img.onerror = () => resolve(file);
    img.src = URL.createObjectURL(file);
  });
}

async function submitListing(ev) {
  ev.preventDefault();
  const f = ev.target;
  const btn = f.querySelector("button[type=submit]");
  btn.disabled = true; btn.textContent = "Listing…";
  try {
    const listing = await api("POST", "/v1/listings", {
      title: f.title.value.trim(),
      category: f.category.value,
      description: f.description.value.trim(),
      price_per_day_cents: Math.round(parseFloat(f.price.value || "0") * 100),
      deposit_cents: Math.round(parseFloat(f.deposit.value || "0") * 100),
      lat: store.loc.lat, lng: store.loc.lng,
      exact_address: f.address.value.trim(),
      instant_book: $("#instant-check").checked,
      price_per_week_cents: Math.round(parseFloat(f.weekprice.value || "0") * 100),
    });
    if (store.photoBlobs && store.photoBlobs.length) {
      for (let i = 0; i < store.photoBlobs.length; i++) {
        btn.textContent = `Uploading photo ${i + 1}/${store.photoBlobs.length}…`;
        await apiUpload(`/v1/listings/${listing.id}/photo`, store.photoBlobs[i], `tool${i}.jpg`);
      }
      store.photoBlobs = [];
    }
    f.reset(); f.price.value = 8; f.deposit.value = 50;
    const icon = $("#photopick-icon");
    if (icon.tagName === "IMG") icon.outerHTML = `<span class="ph-icon" id="photopick-icon">📷</span>`;
    $("#photopick-label").textContent = "Tap to add a photo of your tool";
    toast("Listed! Your tool is now visible to neighbors. 🎉");
    location.hash = "#/browse";
  } catch (e) { toast(e.message, true); }
  finally { btn.disabled = false; btn.textContent = "List my tool"; }
}

/* ---------------- rentals ---------------- */

let openBooking = null;

function progressHtml(b) {
  if (!["confirmed", "picked_up"].includes(b.state)) return "";
  const total = daysBetween(b.start_date, b.end_date);
  const today = new Date().toISOString().slice(0, 10);
  const elapsed = Math.max(0, Math.min(total, daysBetween(b.start_date, today)));
  const overdue = b.state === "picked_up" && today > b.end_date;
  const pct = b.state === "picked_up" ? Math.round((elapsed / total) * 100) : 0;
  const label = overdue
    ? `⚠️ Overdue — was due back ${b.end_date}`
    : b.state === "picked_up"
      ? `Day ${elapsed} of ${total} · due back ${b.end_date}`
      : `Starts ${b.start_date} · ${total} day${total > 1 ? "s" : ""} booked`;
  return `<div class="progress">
    <div class="bar"><div class="fill${overdue ? " over" : ""}" style="width:${overdue ? 100 : pct}%"></div></div>
    <div class="lbl"${overdue ? ' style="color:var(--danger)"' : ""}>${label}</div>
  </div>`;
}

async function loadRentals() {
  const root = $("#rentals-list");
  root.innerHTML = `<div class="skeleton"><span class="spin">🤝</span> Loading…</div>`;
  try {
    const bookings = await api("GET", "/v1/bookings");
    if (!bookings.length) {
      root.innerHTML = `<div class="empty"><span class="big">🤝</span>No rentals yet.<br>Find a tool in <b>Browse</b> or plan a <b>Project kit</b>.</div>`;
      return;
    }
    const TERMINAL = ["completed", "declined", "expired", "cancelled_by_borrower", "cancelled_by_lender"];
    const active = bookings.filter((b) => !TERMINAL.includes(b.state));
    const history = bookings.filter((b) => TERMINAL.includes(b.state));
    const borrowing = active.filter((b) => b.borrower_uid === store.uid);
    const lending = active.filter((b) => b.lender_uid === store.uid);
    const section = async (title, list) => list.length
      ? `<div class="section-title">${title} <span class="chip">${list.length}</span></div>
         <div class="rentallist">${(await Promise.all(list.map(rentalCard))).join("")}</div>`
      : "";
    const historyHtml = history.length
      ? `<details class="historybox"${store.historyOpen ? " open" : ""}>
         <summary>🗂 History · ${history.length} finished rental${history.length > 1 ? "s" : ""}</summary>
         <div class="rentallist">${(await Promise.all(history.map(rentalCard))).join("")}</div></details>`
      : "";
    root.innerHTML =
      (await section("🔍 Borrowing", borrowing)) +
      (await section("🧰 Lending out", lending)) +
      historyHtml;
    const hb = root.querySelector(".historybox");
    if (hb) hb.addEventListener("toggle", () => { store.historyOpen = hb.open; });
    root.querySelectorAll(".rental").forEach((el) => {
      el.onclick = (ev) => {
        if (ev.target.closest("button, input")) return;
        openBooking = openBooking === el.dataset.id ? null : el.dataset.id;
        loadRentals();
      };
    });
    if (openBooking) renderBookingDetail(openBooking);
  } catch (e) {
    root.innerHTML = `<div class="empty">⚠️ ${esc(e.message)}</div>`;
  }
}

async function rentalCard(b) {
  const [label, tone] = STATE_LABEL[b.state] || [b.state, ""];
  const lending = b.lender_uid === store.uid;
  const otherUid = lending ? b.borrower_uid : b.lender_uid;
  const other = await profileOf(otherUid);
  const otherName = other.display_name || otherUid;
  const open = openBooking === b.id;
  return `<article class="rental" data-id="${esc(b.id)}">
    <div class="row1">
      <h3>${esc(b.listing_title || "Tool")}</h3>
      <span class="chip ${tone}">${label}</span>
    </div>
    <div class="who">
      <span class="dot">${esc(initial(otherName))}</span>
      ${lending ? "Renting to" : "Renting from"} <b>${esc(otherName)}</b>
      · ${esc(b.start_date)} → ${esc(b.end_date)} · ${dollars(b.price.total_cents)}
    </div>
    ${progressHtml(b)}
    ${open ? `<div class="rental-detail" id="detail-${esc(b.id)}"><div class="skeleton">…</div></div>` : ""}
  </article>`;
}

async function renderBookingDetail(id) {
  const box = $(`#detail-${CSS.escape(id)}`);
  if (!box) return;
  try {
    const [b, msgs] = await Promise.all([
      api("GET", `/v1/bookings/${id}`),
      api("GET", `/v1/bookings/${id}/messages`),
    ]);
    const isLender = b.lender_uid === store.uid;
    const acts = [];
    const act = (label, action, cls = "btn-primary") =>
      acts.push(`<button class="btn ${cls}" data-act="${action}">${label}</button>`);
    if (b.state === "requested" && isLender) { act("✅ Approve & charge borrower", "approve"); act("Decline", "decline", "btn-danger"); }
    if (b.state === "confirmed") {
      const mine = isLender ? b.lender_marked_pickup : b.borrower_marked_pickup;
      if (!mine) act("🤝 Confirm handoff", "pickup");
      act("Cancel booking", "cancel", "btn-danger");
    }
    if (b.state === "picked_up" && isLender) {
      act("📦 Tool returned — all good", "return");
      act("⚠️ Report damage", "dispute", "btn-danger");
    }
    if (b.state === "completed") acts.push(`<button class="btn" data-act="review">⭐ Leave a review</button>`);

    // Condition documentation: photos at each handoff + the AI comparison.
    let condition = "";
    if (["confirmed", "picked_up"].includes(b.state)) {
      const phase = b.state === "confirmed" ? "pickup" : "return";
      const counts = `📸 ${b.pickup_photos.length} pickup · ${b.return_photos.length} return photo${b.return_photos.length === 1 ? "" : "s"}`;
      const verdict = b.damage_verdict
        ? `<span class="chip ${b.damage_verdict === "ok" ? "ok" : b.damage_verdict === "damage_suspected" ? "bad" : "warn"}">
             AI check: ${esc(b.damage_verdict.replace(/_/g, " "))}</span>
           <div class="opt" style="margin-top:4px">${esc(b.damage_notes)}</div>`
        : "";
      condition = `<div class="conditionbox">
        <div class="opt" style="font-weight:700">${counts} — photos protect both of you under the Guarantee</div>
        <div class="actions" style="margin-top:8px">
          <button class="btn" data-photo="${phase}">📸 Add ${phase} photo</button>
          ${isLender && b.pickup_photos.length && b.return_photos.length
            ? `<button class="btn" data-act="damage-check">🔍 AI condition check</button>` : ""}
        </div>
        ${verdict}
      </div>`;
    }

    box.innerHTML = `
      ${b.exact_address ? `<div class="address">📍 Pickup: ${esc(b.exact_address)}</div>` : ""}
      <div class="actions">${acts.join("")}</div>
      ${condition}
      <div class="chat">
        <div class="msgs">${msgs.map((m) =>
          `<div class="msg ${m.sender_uid === store.uid ? "mine" : "theirs"}">${esc(m.text)}</div>`).join("") || '<span class="opt">Say hi and arrange the handoff 👋</span>'}</div>
        <div class="chatrow">
          <input id="chat-input-${esc(id)}" placeholder="Message your neighbor…">
          <button class="btn" data-act="send">Send</button>
        </div>
      </div>
      <button class="report-link" onclick="reportTarget('booking','${esc(id)}')">Report a problem with this rental</button>`;
    box.querySelectorAll("[data-act]").forEach((btn) => {
      btn.onclick = () => bookingAction(id, btn.dataset.act);
    });
    box.querySelectorAll("[data-photo]").forEach((btn) => {
      btn.onclick = () => {
        const input = document.createElement("input");
        input.type = "file"; input.accept = "image/*"; input.capture = "environment";
        input.onchange = async () => {
          const file = input.files && input.files[0];
          if (!file) return;
          try {
            const blob = await downscale(file, 1280, 0.85);
            await apiUpload(`/v1/bookings/${id}/photos?phase=${btn.dataset.photo}`, blob, "handoff.jpg");
            toast("Condition photo saved 📸");
            renderBookingDetail(id);
          } catch (e) { toast(e.message, true); }
        };
        input.click();
      };
    });
    $(`#chat-input-${CSS.escape(id)}`).addEventListener("keydown", (e) => {
      if (e.key === "Enter") bookingAction(id, "send");
    });
    box.querySelector(".msgs").scrollTop = 1e6;
  } catch (e) {
    box.innerHTML = `⚠️ ${esc(e.message)}`;
  }
}

function refundMath(b, isLender) {
  if (b.state === "requested") {
    return "Cancel this request? No charge has been made.";
  }
  const paid = b.price.total_cents;
  if (isLender) {
    return `Cancel this booking? The borrower is refunded in full ` +
      `(${dollars(paid)}) and their deposit hold is released. Frequent ` +
      `owner cancellations hurt your profile.`;
  }
  const kept = b.price.service_fee_cents + b.price.protection_fee_cents;
  return `Cancel this booking? You get the rental back (${dollars(b.price.rental_cents)}) ` +
    `and the deposit hold is released. The ${dollars(kept)} in fees is not refunded.`;
}

async function bookingAction(id, action) {
  try {
    if (action === "send") {
      const input = $(`#chat-input-${CSS.escape(id)}`);
      const text = input.value.trim();
      if (!text) return;
      await api("POST", `/v1/bookings/${id}/messages`, { text });
      input.value = "";
      return renderBookingDetail(id);
    }
    if (action === "review") return openReviewComposer(id);
    if (action === "cancel") {
      // Show the exact refund consequences before anything happens.
      const b = await api("GET", `/v1/bookings/${id}`);
      if (!confirm(refundMath(b, b.lender_uid === store.uid))) return;
    }
    if (action === "dispute") {
      const reason = prompt(
        "Describe the damage or problem (this opens a formal claim — the "
        + "deposit hold is captured while ToolShare reviews it):");
      if (!reason || reason.trim().length < 5) {
        if (reason !== null) toast("Please describe the problem in a few words", true);
        return;
      }
      if (!confirm("Open a damage claim? The borrower's deposit is captured "
        + "and held by ToolShare until it's resolved. Run the AI condition "
        + "check first if you haven't.")) return;
      await api("POST", `/v1/bookings/${id}/dispute`, { reason: reason.trim() });
      toast("Claim opened — the deposit is held and our team will review it 🛡️");
      loadRentals();
      return;
    }
    if (action === "damage-check") {
      const r = await api("POST", `/v1/bookings/${id}/damage-check`);
      toast(r.verdict === "ok" ? "✅ AI check: no new damage visible"
        : r.verdict === "damage_suspected" ? "⚠️ AI check: possible damage — review the photos"
        : "🤔 AI check inconclusive — compare the photos yourself");
      return renderBookingDetail(id);
    }
    await api("POST", `/v1/bookings/${id}/${action}`);
    if (action === "cancel") toast("Cancelled — refunds per policy are on their way.");
    if (action === "approve") toast("Approved — borrower charged, deposit held. 💳");
    if (action === "return") toast("Rental complete — payout released to you. 🎉");
    loadRentals();
  } catch (e) { toast(e.message, true); }
}

/* ---------------- profile ---------------- */

async function loadProfile() {
  $("#uid-input").value = store.uid;
  $("#whoami-name").textContent = store.uid;
  $("#whoami-dot").textContent = initial(store.uid);
  try {
    const p = await api("GET", "/v1/users/me");
    const name = p.display_name || p.uid;
    $("#profile-name").textContent = name;
    $("#profile-email").textContent = p.email
      || (store.token ? "" : "Guest session — sign in with Google to keep your profile");
    store.me = p;
    renderWhoami();
    $("#profile-avatar").innerHTML = p.photo_url
      ? `<img src="${esc(p.photo_url)}" alt="" referrerpolicy="no-referrer">`
      : esc(initial(name));
    $("#profile-since").textContent = p.created_at
      ? "Member since " + new Date(p.created_at).toLocaleDateString("en-US", { month: "long", year: "numeric" })
      : "";
    $("#view-as-btn").onclick = () => openPublicProfile(p.uid);
    const cfg = await authConfig();
    document.querySelector(".switcher").style.display = cfg.dev_auth ? "" : "none";
    $("#profile-rating").textContent = p.rating_count > 0
      ? `★ ${p.rating_avg} · ${p.rating_count} review${p.rating_count > 1 ? "s" : ""}`
      : "No reviews yet";
    $("#name-input").value = p.display_name || "";
    $("#bio-input").value = p.bio || "";
    $("#profile-badges").innerHTML = [
      p.card_on_file ? `<span class="badge">💳 Card verified</span>` : "",
      p.stripe_connect_id ? `<span class="badge">🏦 Payouts active</span>` : "",
      p.rating_count > 0 ? `<span class="badge">⭐ Reviewed neighbor</span>` : "",
    ].join("") || `<span class="chip">New neighbor — add a card to start renting</span>`;
    renderCard(p, name);
    renderLadder(p);
    renderChecklist();
    loadLedger();
    loadFavorites();
    loadMyReviews(p.uid);
    loadAlerts();
    $("#ref-link").value = `${location.origin}/?ref=${encodeURIComponent(p.uid)}`;
    $("#credit-chip").innerHTML = p.credit_cents > 0
      ? `<span class="credit-pill">🎁 ${dollars(p.credit_cents)} rental credit — auto-applied at your next booking</span>`
      : `<span class="opt">No credit yet — every accepted invite is worth $10.</span>`;
    loadMyTools();
  } catch (e) { toast(e.message, true); }
}

function starRow(stars) {
  return "★".repeat(stars) + "☆".repeat(5 - stars);
}

async function reviewsHtml(uid) {
  const reviews = await api("GET", `/v1/users/${encodeURIComponent(uid)}/reviews`);
  if (!reviews.length) return { count: 0, html: `<p class="opt">No reviews yet — they arrive after completed rentals.</p>` };
  const rows = await Promise.all(reviews.slice(0, 10).map(async (r) => {
    const from = await profileOf(r.from_uid);
    return `<div class="reviewrow">
      <span class="dot">${esc(initial(from.display_name || r.from_uid))}</span>
      <div><div><b>${esc(from.display_name || r.from_uid)}</b>
        <span class="stars">${starRow(r.stars)}</span></div>
        ${r.text ? `<div class="opt">${esc(r.text)}</div>` : ""}</div>
    </div>`;
  }));
  return { count: reviews.length, html: rows.join("") };
}

async function loadMyReviews(uid) {
  try {
    const { count, html } = await reviewsHtml(uid);
    $("#reviews-count").textContent = `${count}`;
    $("#reviews-box").innerHTML = html;
  } catch { $("#reviews-box").innerHTML = ""; }
}

async function openPublicProfile(uid) {
  try {
    const [p, reviews] = await Promise.all([
      api("GET", `/v1/users/${encodeURIComponent(uid)}`),
      reviewsHtml(uid),
    ]);
    const name = p.display_name || uid;
    modal(`
      <div class="inner" style="padding-top:30px">
        <button class="closex" style="position:absolute;top:10px;right:10px" onclick="closeModal()">✕</button>
        <span class="kicker">👁 How neighbors see you</span>
        <div class="profile-head" style="margin-top:10px">
          <div class="avatar">${p.photo_url ? `<img src="${esc(p.photo_url)}" alt="" referrerpolicy="no-referrer">` : esc(initial(name))}</div>
          <div>
            <div class="profile-name">${esc(name)}</div>
            <div class="profile-rating">${p.rating_count ? `${starRow(Math.round(p.rating_avg))} ${p.rating_avg} · ${p.rating_count} review${p.rating_count > 1 ? "s" : ""}` : "No reviews yet"}</div>
          </div>
        </div>
        ${p.bio ? `<p style="margin:10px 0">${esc(p.bio)}</p>` : `<p class="opt" style="margin:10px 0">No bio yet — a friendly line builds trust.</p>`}
        <div class="badges">
          ${p.id_verified ? `<span class="badge">🪪 ID verified</span>` : ""}
          ${p.card_on_file ? `<span class="badge">💳 Card verified</span>` : ""}
        </div>
        <div class="section-title">⭐ Reviews</div>
        ${reviews.html}
      </div>`);
  } catch (e) { toast(e.message, true); }
}

function openReviewComposer(bookingId) {
  let stars = 5;
  modal(`
    <div class="inner" style="padding-top:30px">
      <button class="closex" style="position:absolute;top:10px;right:10px" onclick="closeModal()">✕</button>
      <span class="kicker">⭐ Rate this rental</span>
      <h2>How did it go?</h2>
      <div class="starpick" id="starpick"></div>
      <textarea id="review-text" rows="3" placeholder="e.g. Tool was in great shape, easy porch pickup 👍" style="margin-top:12px"></textarea>
      <button class="btn btn-primary btn-big" id="review-send" style="width:100%;margin-top:14px">Post review</button>
      <p class="fineprint">Reviews are public and build your neighbor's reputation.</p>
    </div>`);
  const paint = () => {
    $("#starpick").innerHTML = [1, 2, 3, 4, 5].map((n) =>
      `<button class="starbtn ${n <= stars ? "on" : ""}" data-n="${n}">★</button>`).join("");
    document.querySelectorAll(".starbtn").forEach((b) => {
      b.onclick = () => { stars = +b.dataset.n; paint(); };
    });
  };
  paint();
  $("#review-send").onclick = async () => {
    try {
      await api("POST", `/v1/bookings/${bookingId}/reviews`,
        { stars, text: $("#review-text").value.trim() });
      closeModal();
      toast("Review posted — thanks for building neighborhood trust ⭐");
      loadRentals();
    } catch (e) { toast(e.message, true); }
  };
}

async function loadAlerts() {
  const box = $("#alerts-box");
  try {
    const alerts = await api("GET", "/v1/searches");
    $("#alerts-count").textContent = `${alerts.length}`;
    if (!alerts.length) {
      box.innerHTML = `<p class="opt">None yet — search for a tool nobody has and tap “Alert me”.</p>`;
      return;
    }
    box.innerHTML = alerts.map((a) => `
      <div class="reviewrow" style="align-items:center">
        <span>🔔</span>
        <div style="flex:1"><b>${esc(a.term)}</b></div>
        <button class="btn" style="padding:4px 10px" data-del-alert="${esc(a.id)}">✕</button>
      </div>`).join("");
    box.querySelectorAll("[data-del-alert]").forEach((btn) => {
      btn.onclick = async () => {
        try {
          await api("DELETE", `/v1/searches/${btn.dataset.delAlert}`);
          toast("Alert removed");
          loadAlerts();
        } catch (e) { toast(e.message, true); }
      };
    });
  } catch { box.innerHTML = ""; }
}

async function loadLedger() {
  try {
    const l = await api("GET", "/v1/users/me/ledger");
    $("#ledger-tiles").innerHTML = `
      <div class="stat-tile"><div class="num">${dollars(l.saved_vs_buying_cents)}</div><div class="lbl">Saved vs buying</div></div>
      <div class="stat-tile"><div class="num">${l.rentals_as_borrower}</div><div class="lbl">Tools borrowed</div></div>
      <div class="stat-tile"><div class="num">${dollars(l.earned_cents)}</div><div class="lbl">Earned lending</div></div>
      <div class="stat-tile"><div class="num">${l.rentals_as_lender}</div><div class="lbl">Tools lent</div></div>`;
  } catch { $("#ledger-tiles").innerHTML = ""; }
}

async function loadFavorites() {
  const box = $("#fav-list");
  try {
    const favs = await api("GET", "/v1/users/me/favorites");
    $("#fav-count").textContent = `${favs.length} saved`;
    if (!favs.length) {
      box.innerHTML = `<p class="opt">Tap 🤍 on any tool to save it for later.</p>`;
      return;
    }
    box.innerHTML = favs.map((l) => `
      <div class="mytool" data-open="${esc(l.id)}" style="cursor:pointer">
        <div class="row1"><span>${CATEGORIES[l.category] || "🧰"}</span>
          <span class="t">${esc(l.title)}</span>
          <span class="chip ok">${dollars(l.price_per_day_cents)}/day</span></div>
      </div>`).join("");
    box.querySelectorAll("[data-open]").forEach((el) => {
      el.onclick = () => openListing(el.dataset.open);
    });
  } catch { box.innerHTML = ""; }
}

function renderLadder(p) {
  const rung = (done, icon, label, sub, stateHtml) => `
    <div class="rung ${done ? "done" : ""}">
      <span class="ic">${icon}</span>
      <div><div class="lbl">${label}</div><div class="sub">${sub}</div></div>
      <span class="state">${stateHtml}</span>
    </div>`;
  $("#ladder").innerHTML =
    rung(true, "🙂", "Neighbor account", "Google or invited sign-in", "✓") +
    rung(p.card_on_file, "💳", "Card on file", "Backs every deposit hold",
      p.card_on_file ? "✓ verified" : "add below") +
    rung(p.id_verified, "🪪", "Government ID", "Stripe Identity document check",
      p.id_verified ? "✓ verified"
        : `<button class="btn" id="verify-id-btn" style="padding:5px 12px">Verify my ID</button>`) +
    rung(p.rating_count > 0, "⭐", "Reviewed neighbor", "Earn reviews by completing rentals",
      p.rating_count > 0 ? `✓ ${p.rating_count} review${p.rating_count > 1 ? "s" : ""}` : "not yet");
  const btn = $("#verify-id-btn");
  if (btn) btn.onclick = async () => {
    btn.disabled = true;
    try {
      const r = await api("POST", "/v1/users/me/identity-session");
      if (r.id_verified) {
        toast("You're ID-verified 🪪 — trust badge unlocked!");
        loadProfile();
      } else if (r.verification_url) {
        window.open(r.verification_url, "_blank");
        toast("Complete the ID check in the new tab — your badge appears automatically.");
      }
    } catch (e) { toast(e.message, true); btn.disabled = false; }
  };
}

function renderCard(p, name) {
  $("#cc-visual").innerHTML = p.card_on_file
    ? `<div class="cc">
        <div class="row"><div class="chip-icon"></div><b style="letter-spacing:.06em">VISA</b></div>
        <div class="num">•••• •••• •••• ${esc(p.card_last4 || "4242")}</div>
        <div class="row">
          <div><div class="lbl">Card holder</div><div class="holder">${esc(name)}</div></div>
          <div><div class="lbl">Backs deposits</div><div class="holder">✓ Active</div></div>
        </div>
      </div>`
    : `<div class="cc empty-cc">
        <div class="num" style="letter-spacing:.05em">No card on file</div>
        <div>Add one to unlock renting — it's only charged when an owner accepts your request.</div>
      </div>`;
}

async function loadMyTools() {
  const listEl = $("#mytools-list");
  const statsEl = $("#mytools-stats");
  try {
    const tools = await api("GET", "/v1/listings/mine");
    $("#mytools-count").textContent = `${tools.length} listed`;
    if (!tools.length) {
      statsEl.innerHTML = "";
      listEl.innerHTML = `<p class="opt">Nothing listed yet — your garage is full of $8/day tools. Start with the <a href="#/list">List</a> tab.</p>`;
      return;
    }
    const histories = await Promise.all(
      tools.map((t) => api("GET", `/v1/listings/${t.id}/history`).catch(() => null)));
    const totalDays = histories.reduce((s, h) => s + (h ? h.total_days_rented : 0), 0);
    const totalEarned = histories.reduce((s, h) => s + (h ? h.total_earned_cents : 0), 0);
    const totalRentals = histories.reduce((s, h) => s + (h ? h.times_rented : 0), 0);
    statsEl.innerHTML = `
      <div class="stat-tile"><div class="num">${tools.length}</div><div class="lbl">Tools listed</div></div>
      <div class="stat-tile"><div class="num">${totalRentals}</div><div class="lbl">Times rented</div></div>
      <div class="stat-tile"><div class="num">${totalDays}</div><div class="lbl">Days on loan</div></div>
      <div class="stat-tile"><div class="num">${dollars(totalEarned)}</div><div class="lbl">Earned (100% yours)</div></div>`;
    listEl.innerHTML = tools.map((t, i) => {
      const h = histories[i];
      const today = new Date().toISOString().slice(0, 10);
      const overdue = h && h.active_borrower && h.active_until && h.active_until < today;
      const active = t.status === "paused"
        ? `<span class="chip">⏸ paused</span>`
        : overdue
          ? `<span class="chip bad">⚠️ overdue — with ${esc(h.active_borrower)} since ${esc(h.active_until)}</span>`
          : h && h.active_borrower
            ? `<span class="chip warn">with ${esc(h.active_borrower)} until ${esc(h.active_until)}</span>`
            : `<span class="chip ok">available</span>`;
      const rows = (h && h.entries.length
        ? `<table><tr><th>Renter</th><th>Dates</th><th>Days</th><th>Earned</th></tr>` +
          h.entries.map((e) =>
            `<tr><td>${esc(e.borrower_name)}</td><td>${esc(e.start_date)} → ${esc(e.end_date)}</td>` +
            `<td>${e.days}</td><td>${dollars(e.earned_cents)}</td></tr>`).join("") + `</table>`
        : `<p class="opt" style="margin-top:8px">No rentals yet for this tool.</p>`)
        + `<div class="actions" style="margin-top:10px">
             <button class="btn" data-blackout="${esc(t.id)}">📅 Block dates</button>
             <button class="btn" data-price="${esc(t.id)}">✏️ Change price</button>
             <button class="btn" data-pause="${esc(t.id)}">${t.status === "paused" ? "▶️ Reactivate" : "⏸ Pause listing"}</button>
           </div>`;
      return `<div class="mytool" data-i="${i}">
        <div class="row1"><span>${CATEGORIES[t.category] || "🧰"}</span><span class="t">${esc(t.title)}</span>${active}</div>
        <div class="sub">${dollars(t.price_per_day_cents)}/day · rented ${h ? h.times_rented : 0}× · ${h ? h.total_days_rented : 0} days total · earned ${dollars(h ? h.total_earned_cents : 0)}</div>
        <div class="hist" style="display:none">${rows}</div>
      </div>`;
    }).join("");
    listEl.querySelectorAll(".mytool").forEach((el) => {
      el.onclick = (ev) => {
        if (ev.target.closest("[data-blackout],[data-price],[data-pause]")) return;
        const hist = el.querySelector(".hist");
        hist.style.display = hist.style.display === "none" ? "block" : "none";
      };
    });
    listEl.querySelectorAll("[data-blackout]").forEach((btn) => {
      btn.onclick = () => openBlackoutEditor(tools.find((t) => t.id === btn.dataset.blackout));
    });
    listEl.querySelectorAll("[data-price]").forEach((btn) => {
      btn.onclick = async () => {
        const t = tools.find((x) => x.id === btn.dataset.price);
        const v = prompt("New price per day ($):", (t.price_per_day_cents / 100).toFixed(0));
        const cents = Math.round(parseFloat(v || "") * 100);
        if (!cents || cents < 500) { if (v !== null) toast("Minimum price is $5/day", true); return; }
        try {
          await api("PATCH", `/v1/listings/${t.id}`, { price_per_day_cents: cents });
          toast(`Price updated to ${dollars(cents)}/day ✓`);
          loadMyTools();
        } catch (e) { toast(e.message, true); }
      };
    });
    listEl.querySelectorAll("[data-pause]").forEach((btn) => {
      btn.onclick = async () => {
        const t = tools.find((x) => x.id === btn.dataset.pause);
        const to = t.status === "paused" ? "active" : "paused";
        try {
          await api("PATCH", `/v1/listings/${t.id}`, { status: to });
          toast(to === "paused" ? "Listing paused — hidden from browse ⏸" : "Listing live again ▶️");
          loadMyTools();
        } catch (e) { toast(e.message, true); }
      };
    });
  } catch (e) {
    listEl.innerHTML = `<p class="opt">⚠️ ${esc(e.message)}</p>`;
  }
}

async function openBlackoutEditor(tool) {
  if (!tool) return;
  const avail = await api("GET", `/v1/listings/${tool.id}/availability`)
    .catch(() => ({ booked: [], blackout_dates: [] }));
  const bookedOnly = calBlockedSet({ booked: avail.booked, blackout_dates: [] });
  const chosen = new Set(avail.blackout_dates);
  const now = new Date();
  let calYM = [now.getUTCFullYear(), now.getUTCMonth()];
  const render = () => {
    // Booked days are locked (can't blackout a confirmed rental); chosen
    // blackouts render as selected.
    $("#bo-cal").innerHTML = calHtml(calYM, bookedOnly,
      { start: null, end: null }, { allowToday: true });
    document.querySelectorAll("#bo-cal [data-day]").forEach((el) => {
      if (chosen.has(el.dataset.day)) el.classList.add("sel");
      el.onclick = () => {
        const d = el.dataset.day;
        chosen.has(d) ? chosen.delete(d) : chosen.add(d);
        render();
      };
    });
    $("#bo-cal [data-cal=prev]").onclick = () => { calYM = prevYM(calYM); render(); };
    $("#bo-cal [data-cal=next]").onclick = () => { calYM = nextYM(calYM); render(); };
    $("#bo-count").textContent = chosen.size
      ? `${chosen.size} day${chosen.size > 1 ? "s" : ""} blocked`
      : "No blocked days — tap days to block them";
  };
  modal(`
    <div class="inner">
      <button class="closex" style="position:absolute;top:10px;right:10px" onclick="closeModal()">✕</button>
      <h2>📅 Block dates</h2>
      <p style="color:var(--muted);margin:6px 0 2px">${esc(tool.title)} — tap days you don't want it rented (your own projects, trips…). Days with confirmed rentals are locked.</p>
      <div id="bo-cal"></div>
      <p class="opt" id="bo-count"></p>
      <button class="btn btn-primary btn-big" id="bo-save" style="width:100%">Save blocked dates</button>
    </div>
  `);
  render();
  $("#bo-save").onclick = async () => {
    try {
      await api("PATCH", `/v1/listings/${tool.id}`, { blackout_dates: [...chosen].sort() });
      closeModal();
      toast("Blocked dates saved — the calendar shows them as unavailable ✓");
    } catch (e) { toast(e.message, true); }
  };
}

async function saveProfile() {
  try {
    await api("PATCH", "/v1/users/me", {
      display_name: $("#name-input").value.trim(),
      bio: $("#bio-input").value.trim(),
    });
    delete store.profiles[store.uid];
    toast("Profile saved ✓");
    loadProfile();
  } catch (e) { toast(e.message, true); }
}

async function addPaymentMethod() {
  const btn = $("#pay-btn");
  btn.disabled = true;
  try {
    // 1. Backend creates the SetupIntent bundle (used by Stripe PaymentSheet
    //    on mobile; on web this seeds the customer).
    await api("POST", "/v1/users/me/setup-intent");
    // 2. Production: stripe.confirmSetup(...) with the card element here.
    //    Staging: the fake provider "saves" a 4242 test card instantly.
    const status = await api("POST", "/v1/users/me/payment-method");
    toast(status.card_on_file
      ? `Card •••• ${status.card_last4} saved — you can rent tools now 🎉`
      : "No card found — complete the Stripe form first", !status.card_on_file);
    loadProfile();
  } catch (e) { toast(e.message, true); }
  finally { btn.disabled = false; }
}

function switchUser() {
  const v = $("#uid-input").value.trim().toLowerCase().replace(/[^a-z0-9_-]/g, "");
  if (!v) return;
  localStorage.removeItem("ts_token");  // demo identities replace a Google session
  store.uid = v;
  openBooking = null;
  toast(`You're now ${v}`);
  loadProfile();
}

/* ---------------- notifications (bell + web push) ---------------- */

function timeAgo(iso) {
  if (!iso) return "";
  const s = Math.max(0, (Date.now() - new Date(iso)) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

async function loadNotifs() {
  try {
    const feed = await api("GET", "/v1/notifications");
    store.notifFeed = feed;
    const badge = $("#bell-badge");
    badge.hidden = feed.unread === 0;
    badge.textContent = feed.unread > 9 ? "9+" : feed.unread;
  } catch { /* not signed in yet — ignore */ }
}

async function toggleNotifPanel() {
  const panel = $("#notif-panel");
  if (!panel.hidden) { panel.hidden = true; return; }
  await loadNotifs();
  const feed = store.notifFeed || { items: [], unread: 0 };
  $("#notif-list").innerHTML = feed.items.length
    ? feed.items.map((n) => `
        <div class="notif ${n.read ? "" : "unread"}" data-booking="${esc(n.booking_id)}">
          <div class="t">${esc(n.title)}</div>
          ${n.body ? `<div class="b">${esc(n.body)}</div>` : ""}
          <div class="when">${timeAgo(n.created_at)}</div>
        </div>`).join("")
    : `<p class="opt" style="padding:14px 6px">Nothing yet — booking activity shows up here.</p>`;
  panel.hidden = false;
  $("#notif-list").querySelectorAll(".notif").forEach((el) => {
    el.onclick = () => {
      panel.hidden = true;
      if (el.dataset.booking) { openBooking = el.dataset.booking; location.hash = "#/rentals"; loadRentals(); }
    };
  });
  setupPushButton();
  if (feed.unread > 0) {
    await api("POST", "/v1/notifications/read").catch(() => {});
    $("#bell-badge").hidden = true;
  }
}

async function setupPushButton() {
  const btn = $("#push-btn");
  const supported = "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
  if (!supported || Notification.permission === "granted") { btn.hidden = true; return; }
  let cfg = { vapid_public_key: "" };
  try { cfg = await api("GET", "/v1/notifications/config"); } catch { /* ignore */ }
  if (!cfg.vapid_public_key) { btn.hidden = true; return; }
  btn.hidden = false;
  btn.onclick = () => enablePush(cfg.vapid_public_key);
}

function b64ToUint8(base64) {
  const pad = "=".repeat((4 - (base64.length % 4)) % 4);
  const raw = atob((base64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from([...raw].map((ch) => ch.charCodeAt(0)));
}

async function enablePush(vapidKey) {
  try {
    const perm = await Notification.requestPermission();
    if (perm !== "granted") { toast("Push permission declined", true); return; }
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: b64ToUint8(vapidKey),
    });
    const j = sub.toJSON();
    await api("POST", "/v1/notifications/subscriptions",
      { endpoint: sub.endpoint, p256dh: j.keys.p256dh, auth: j.keys.auth });
    $("#push-btn").hidden = true;
    toast("Push enabled — you'll hear about requests instantly 🔔");
  } catch (e) { toast("Couldn't enable push: " + e.message, true); }
}

/* ---------------- boot ---------------- */

function boot() {
  $("#category-select").innerHTML = Object.keys(CATEGORIES)
    .map((c) => `<option value="${c}">${CATEGORIES[c]} ${c.replace(/_/g, " ")}</option>`).join("");
  $("#search-btn").onclick = loadBrowse;
  $("#search-input").addEventListener("keydown", (e) => { if (e.key === "Enter") loadBrowse(); });
  $("#plan-btn").onclick = planProject;
  $("#list-form").addEventListener("submit", submitListing);
  $("#category-select").addEventListener("change", priceHint);
  bindPhotoPicker();
  $("#uid-btn").onclick = switchUser;
  $("#uid-input").addEventListener("keydown", (e) => { if (e.key === "Enter") switchUser(); });
  $("#whoami").onclick = () => {
    if (!store.token) openSignIn();
    else location.hash = "#/profile";
  };
  $("#save-profile-btn").onclick = saveProfile;
  $("#signout-btn").onclick = () => {
    localStorage.removeItem("ts_token");
    localStorage.removeItem("ts_uid");
    location.href = "/";
  };
  $("#pay-btn").onclick = addPaymentMethod;
  $("#connect-btn").onclick = async () => {
    try {
      const r = await api("POST", "/v1/users/me/connect");
      window.open(r.onboarding_url, "_blank");
      const sweep = await api("POST", "/v1/users/me/connect/complete").catch(() => null);
      if (sweep && sweep.paid_bookings.length) toast(`Pending payouts released: ${dollars(sweep.total_cents)} 🎉`);
      loadProfile();
    } catch (e) { toast(e.message, true); }
  };
  $("#view-list").onclick = () => { store.view = "list"; renderBrowse(); };
  $("#view-map").onclick = () => { store.view = "map"; renderBrowse(); };
  $("#ref-copy").onclick = async () => {
    await navigator.clipboard.writeText($("#ref-link").value).catch(() => {});
    toast("Invite link copied — worth $10 to you and your neighbor 🎁");
  };
  api("GET", "/v1/users/me").then((p) => {
    store.me = p;
    renderWhoami();
    renderChecklist();
    maybeOnboard();
  }).catch(() => {});
  $("#bell").onclick = toggleNotifPanel;
  document.addEventListener("click", (ev) => {
    if (!ev.target.closest("#notif-panel, #bell")) $("#notif-panel").hidden = true;
  });
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/app/sw.js").catch(() => {});
  }
  $("#whoami-name").textContent = store.uid;
  $("#whoami-dot").textContent = initial(store.uid);
  renderLocRow();
  route();
  loadNotifs();
  setInterval(loadNotifs, 45000);
  setInterval(pollChat, 6000);
}

async function pollChat() {
  // Live-ish chat: refresh only the message list of the open booking so a
  // draft being typed is never clobbered.
  if (document.hidden || !openBooking || !location.hash.includes("rentals")) return;
  const box = document.querySelector(`#detail-${CSS.escape(openBooking)} .msgs`);
  if (!box) return;
  try {
    const msgs = await api("GET", `/v1/bookings/${openBooking}/messages`);
    const html = msgs.map((m) =>
      `<div class="msg ${m.sender_uid === store.uid ? "mine" : "theirs"}">${esc(m.text)}</div>`).join("")
      || '<span class="opt">Say hi and arrange the handoff 👋</span>';
    if (box.innerHTML !== html) {
      box.innerHTML = html;
      box.scrollTop = 1e6;
    }
  } catch { /* transient */ }
}
boot();
