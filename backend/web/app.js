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
  photoBlob: null, // pending listing photo
  view: "list",   // browse presentation: list | map
  lastResults: [], // cached search results shared by list + map
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

function handleCardRequired(e) {
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
  if (active === "browse") loadBrowse();
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
    store.lastResults = await api("GET", `/v1/listings/search?${params}`);
    renderBrowse();
  } catch (e) {
    grid.innerHTML = `<div class="empty">⚠️ ${esc(e.message)}</div>`;
  }
}

function renderBrowse() {
  const grid = $("#browse-results");
  const results = store.lastResults;
  const mapMode = store.view === "map";
  $("#view-list").classList.toggle("active", !mapMode);
  $("#view-map").classList.toggle("active", mapMode);
  $("#map").hidden = !mapMode;
  grid.hidden = mapMode;
  if (mapMode) { renderMap(results); return; }
  if (!results.length) {
    grid.innerHTML = `<div class="empty"><span class="big">🌱</span>No tools here yet.<br>Be the first — list one from the <b>List</b> tab.</div>`;
    return;
  }
  grid.innerHTML = results.map(toolCard).join("");
  grid.querySelectorAll(".toolcard").forEach((el) => {
    el.onclick = () => openListing(el.dataset.id);
  });
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

function toolCard(r) {
  const l = r.listing;
  const rating = l.rating_count > 0 ? `<span class="chip">★ ${l.rating_avg}</span>` : "";
  const deposit = l.deposit_cents > 0 ? `<span class="chip">🛡 ${dollars(l.deposit_cents)} deposit</span>` : "";
  return `<article class="toolcard" data-id="${esc(l.id)}">
    <div class="toolphoto">${photoHtml(l)}
      <span class="pricepill">${dollars(l.price_per_day_cents)}<small>/day</small></span>
    </div>
    <div class="body">
      <h3>${esc(l.title)}</h3>
      <div class="meta">
        <span class="chip ok">📍 ${r.distance_km.toFixed(1)} km</span>${rating}${deposit}
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
    const rental = l.price_per_day_cents * days;
    box.innerHTML =
      `<b>${esc(sel.start)} → ${esc(end)}</b> · ${days} day${days > 1 ? "s" : ""}<br>` +
      `${dollars(rental)} rental + ${dollars(fee(rental))} service fee + ${dollars(PROTECTION_FEE_CENTS)} protection` +
      (l.deposit_cents ? `<br>+ ${dollars(l.deposit_cents)} refundable deposit hold (released on safe return)` : "") +
      `<div class="grand">Total ${dollars(rental + fee(rental) + PROTECTION_FEE_CENTS)}</div>
       <div class="protectline">🛡️ ToolShare Guarantee — covered up to $2,500 against damage or theft</div>`;
    btn.disabled = false;
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
  modal(`
    <div class="mphoto">${photoHtml(l)}
      <button class="closex" onclick="closeModal()">✕</button>
    </div>
    <div class="inner">
      <h2>${esc(l.title)}</h2>
      <p style="color:var(--muted);margin:6px 0 2px">
        ${CATEGORIES[l.category] || "🧰"} ${esc(l.category.replace(/_/g, " "))} · condition: ${esc(l.condition)}
        ${l.rating_count ? ` · ★ ${l.rating_avg} (${l.rating_count})` : ""}</p>
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
  $("#m-report").onclick = () => reportTarget("listing", l.id);
  $("#m-request").onclick = async () => {
    try {
      await api("POST", "/v1/bookings",
        { listing_id: l.id, start_date: sel.start, end_date: sel.end || sel.start });
      closeModal();
      toast("Requested! The owner has 24h to accept — track it in Rentals.");
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
    <div class="kit-notes">
      ${kit.missing_tools.length ? `⏳ Not nearby yet: <b>${kit.missing_tools.map(esc).join(", ")}</b>. We'll notify you when a neighbor lists one.<br>` : ""}
      ${kit.plan.consumables_note ? `🛒 ${esc(kit.plan.consumables_note)}<br>` : ""}
      ${kit.plan.safety_note ? `⚠️ ${esc(kit.plan.safety_note)}` : ""}
    </div>`;
  document.querySelectorAll(".kititem[data-listing]").forEach((el) => {
    el.onclick = () => openListing(el.dataset.listing);
  });
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

/* ---------------- list a tool (with photo) ---------------- */

function bindPhotoPicker() {
  const pick = $("#photopick");
  const input = $("#photo-input");
  pick.onclick = () => input.click();
  input.onchange = async () => {
    const file = input.files && input.files[0];
    if (!file) return;
    store.photoBlob = await downscale(file, 1280, 0.85);
    const url = URL.createObjectURL(store.photoBlob);
    $("#photopick-icon").outerHTML = `<img id="photopick-icon" src="${url}" alt="preview">`;
    $("#photopick-label").textContent = "Looks great — tap to change";
  };
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
    });
    if (store.photoBlob) {
      btn.textContent = "Uploading photo…";
      await apiUpload(`/v1/listings/${listing.id}/photo`, store.photoBlob, "tool.jpg");
      store.photoBlob = null;
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
    const cards = await Promise.all(bookings.map(rentalCard));
    root.innerHTML = `<div class="rentallist">${cards.join("")}</div>`;
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
    if (b.state === "picked_up" && isLender) act("📦 Tool returned — all good", "return");
    if (b.state === "completed") acts.push(`<button class="btn" data-act="review">⭐ Leave a 5★ review</button>`);

    box.innerHTML = `
      ${b.exact_address ? `<div class="address">📍 Pickup: ${esc(b.exact_address)}</div>` : ""}
      <div class="actions">${acts.join("")}</div>
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
    if (action === "review") {
      await api("POST", `/v1/bookings/${id}/reviews`, { stars: 5, text: "" });
      toast("Thanks for the review! ⭐");
      return;
    }
    if (action === "cancel") {
      // Show the exact refund consequences before anything happens.
      const b = await api("GET", `/v1/bookings/${id}`);
      if (!confirm(refundMath(b, b.lender_uid === store.uid))) return;
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
    $("#profile-email").textContent = p.email || (store.token ? "" : "Demo identity — staging only");
    $("#whoami-name").textContent = name;
    $("#whoami-dot").textContent = initial(name);
    $("#profile-avatar").textContent = initial(name);
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
    loadMyTools();
  } catch (e) { toast(e.message, true); }
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
      const active = h && h.active_borrower
        ? `<span class="chip warn">with ${esc(h.active_borrower)} until ${esc(h.active_until)}</span>`
        : `<span class="chip ok">available</span>`;
      const rows = (h && h.entries.length
        ? `<table><tr><th>Renter</th><th>Dates</th><th>Days</th><th>Earned</th></tr>` +
          h.entries.map((e) =>
            `<tr><td>${esc(e.borrower_name)}</td><td>${esc(e.start_date)} → ${esc(e.end_date)}</td>` +
            `<td>${e.days}</td><td>${dollars(e.earned_cents)}</td></tr>`).join("") + `</table>`
        : `<p class="opt" style="margin-top:8px">No rentals yet for this tool.</p>`)
        + `<button class="btn" style="margin-top:10px" data-blackout="${esc(t.id)}">📅 Block dates</button>`;
      return `<div class="mytool" data-i="${i}">
        <div class="row1"><span>${CATEGORIES[t.category] || "🧰"}</span><span class="t">${esc(t.title)}</span>${active}</div>
        <div class="sub">${dollars(t.price_per_day_cents)}/day · rented ${h ? h.times_rented : 0}× · ${h ? h.total_days_rented : 0} days total · earned ${dollars(h ? h.total_earned_cents : 0)}</div>
        <div class="hist" style="display:none">${rows}</div>
      </div>`;
    }).join("");
    listEl.querySelectorAll(".mytool").forEach((el) => {
      el.onclick = (ev) => {
        if (ev.target.closest("[data-blackout]")) return;
        const hist = el.querySelector(".hist");
        hist.style.display = hist.style.display === "none" ? "block" : "none";
      };
    });
    listEl.querySelectorAll("[data-blackout]").forEach((btn) => {
      btn.onclick = () => openBlackoutEditor(tools.find((t) => t.id === btn.dataset.blackout));
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
  bindPhotoPicker();
  $("#uid-btn").onclick = switchUser;
  $("#uid-input").addEventListener("keydown", (e) => { if (e.key === "Enter") switchUser(); });
  $("#whoami").onclick = () => { location.hash = "#/profile"; };
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
}
boot();
