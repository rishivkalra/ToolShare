/* ToolShare web app — no build step, talks to the same-origin API. */
"use strict";

/* ---------------- state & api ---------------- */

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
  loc: { ...DEMO_LOC, usingDemo: true },
  lastKit: null,
};

async function api(method, path, body) {
  const resp = await fetch(path, {
    method,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer dev:${store.uid}`,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = resp.status === 204 ? null : await resp.json().catch(() => null);
  if (!resp.ok) {
    const detail = data && data.detail ? (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail)) : resp.statusText;
    throw new Error(detail);
  }
  return data;
}

const $ = (sel) => document.querySelector(sel);
const dollars = (c) => `$${(c / 100).toFixed(2).replace(/\.00$/, "")}`;
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));

function toast(msg, isErr = false) {
  const el = document.createElement("div");
  el.className = "toast" + (isErr ? " err" : "");
  el.textContent = msg;
  $("#toast-root").appendChild(el);
  setTimeout(() => el.remove(), 4200);
}

/* ---------------- routing ---------------- */

const TABS = ["browse", "project", "list", "rentals", "profile"];

function route() {
  const tab = (location.hash.replace("#/", "") || "browse").split("?")[0];
  const active = TABS.includes(tab) ? tab : "browse";
  TABS.forEach((t) => {
    $(`#tab-${t}`).classList.toggle("active", t === active);
  });
  document.querySelectorAll("[data-tab]").forEach((a) => {
    a.classList.toggle("active", a.dataset.tab === active);
  });
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
    const results = await api("GET", `/v1/listings/search?${params}`);
    if (!results.length) {
      grid.innerHTML = `<div class="empty"><span class="big">🌱</span>No tools here yet.<br>Be the first — list one from the <b>List</b> tab.</div>`;
      return;
    }
    grid.innerHTML = results.map((r) => toolCard(r)).join("");
    grid.querySelectorAll(".toolcard").forEach((el) => {
      el.onclick = () => openListing(el.dataset.id);
    });
  } catch (e) {
    grid.innerHTML = `<div class="empty">⚠️ ${esc(e.message)}</div>`;
  }
}

function toolCard(r) {
  const l = r.listing;
  const rating = l.rating_count > 0 ? `<span class="chip">★ ${l.rating_avg}</span>` : "";
  return `<article class="toolcard" data-id="${esc(l.id)}">
    <span class="cat">${CATEGORIES[l.category] || "🧰"}</span>
    <h3>${esc(l.title)}</h3>
    <div class="meta">
      <span class="price">${dollars(l.price_per_day_cents)}<small>/day</small></span>
      <span class="chip ok">${r.distance_km.toFixed(1)} km</span>${rating}
    </div>
  </article>`;
}

/* ---------------- listing modal & booking ---------------- */

function isoInDays(n) {
  const d = new Date(Date.now() + n * 86400000);
  return d.toISOString().slice(0, 10);
}

async function openListing(id) {
  const l = await api("GET", `/v1/listings/${id}`).catch((e) => (toast(e.message, true), null));
  if (!l) return;
  let days = 1;
  const fee = (rental) => Math.max(Math.round(rental * 0.15), 100);
  const render = () => {
    const rental = l.price_per_day_cents * days;
    $("#m-days").textContent = `${days} day${days > 1 ? "s" : ""} · starting tomorrow`;
    $("#m-total").innerHTML =
      `${dollars(rental)} rental + ${dollars(fee(rental))} service fee` +
      (l.deposit_cents ? ` · ${dollars(l.deposit_cents)} refundable deposit hold` : "") +
      `<div class="grand">Total ${dollars(rental + fee(rental))}</div>`;
  };
  modal(`
    <button class="closex" onclick="closeModal()">✕</button>
    <span class="cat">${CATEGORIES[l.category] || "🧰"}</span>
    <h2>${esc(l.title)}</h2>
    <p style="color:var(--muted);margin:6px 0 2px">Condition: ${esc(l.condition)}${l.rating_count ? ` · ★ ${l.rating_avg} (${l.rating_count})` : ""}</p>
    ${l.description ? `<p style="margin:8px 0">${esc(l.description)}</p>` : ""}
    <div class="stepper">
      <button id="m-minus">−</button><b id="m-days"></b><button id="m-plus">+</button>
    </div>
    <div class="totalbox" id="m-total"></div>
    <button class="btn btn-primary btn-big" id="m-request" style="width:100%">Request to rent</button>
    <p class="fineprint">You're only charged if the owner accepts. Exact pickup address is shared after confirmation.</p>
  `);
  render();
  $("#m-minus").onclick = () => { days = Math.max(1, days - 1); render(); };
  $("#m-plus").onclick = () => { days = Math.min(7, days + 1); render(); };
  $("#m-request").onclick = async () => {
    try {
      await api("POST", "/v1/bookings", { listing_id: l.id, start_date: isoInDays(1), end_date: isoInDays(days) });
      closeModal();
      toast("Requested! The owner has 24h to accept — track it in Rentals.");
      location.hash = "#/rentals";
    } catch (e) { toast(e.message, true); }
  };
}

function modal(html) {
  $("#modal-root").innerHTML = `<div class="modal-backdrop" onclick="if(event.target===this)closeModal()"><div class="modal">${html}</div></div>`;
}
window.closeModal = () => { $("#modal-root").innerHTML = ""; };

/* ---------------- project kit ---------------- */

async function planProject() {
  const description = $("#project-input").value.trim();
  if (description.length < 10) { toast("Describe your project in a sentence or two", true); return; }
  const btn = $("#plan-btn");
  btn.disabled = true; btn.textContent = "Planning your kit…";
  $("#kit-results").innerHTML = `<div class="skeleton"><span class="spin">✨</span> Gemini is planning your tool list…</div>`;
  try {
    const kit = await api("POST", "/v1/projects/plan", { description, lat: store.loc.lat, lng: store.loc.lng });
    store.lastKit = kit;
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
    const stat = best ? "✅" : "⏳";
    const match = best
      ? `<div class="match">${esc(best.title)} · ${dollars(best.price_per_day_cents)}/day nearby</div>`
      : `<div class="why">No neighbor has this yet — we'll flag it as wanted</div>`;
    return `<div class="kititem" ${best ? `data-listing="${esc(best.id)}"` : ""} ${best ? 'style="cursor:pointer"' : ""}>
      <span class="stat">${stat}</span>
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
    } catch (e) { toast(e.message, true); co.disabled = false; co.textContent = "Request whole kit"; }
  };
}

/* ---------------- list a tool ---------------- */

async function submitListing(ev) {
  ev.preventDefault();
  const f = ev.target;
  const btn = f.querySelector("button[type=submit]");
  btn.disabled = true; btn.textContent = "Listing…";
  try {
    await api("POST", "/v1/listings", {
      title: f.title.value.trim(),
      category: f.category.value,
      description: f.description.value.trim(),
      price_per_day_cents: Math.round(parseFloat(f.price.value || "0") * 100),
      deposit_cents: Math.round(parseFloat(f.deposit.value || "0") * 100),
      lat: store.loc.lat, lng: store.loc.lng,
      exact_address: f.address.value.trim(),
    });
    f.reset(); f.price.value = 8; f.deposit.value = 50;
    toast("Listed! Your tool is now visible to neighbors.");
    location.hash = "#/browse";
  } catch (e) { toast(e.message, true); }
  finally { btn.disabled = false; btn.textContent = "List my tool"; }
}

/* ---------------- rentals ---------------- */

let openBooking = null;

async function loadRentals() {
  const root = $("#rentals-list");
  root.innerHTML = `<div class="skeleton"><span class="spin">🤝</span> Loading…</div>`;
  try {
    const bookings = await api("GET", "/v1/bookings");
    if (!bookings.length) {
      root.innerHTML = `<div class="empty"><span class="big">🤝</span>No rentals yet.<br>Find a tool in <b>Browse</b> or plan a <b>Project kit</b>.</div>`;
      return;
    }
    root.innerHTML = `<div class="rentallist">${bookings.map(rentalCard).join("")}</div>`;
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

function rentalCard(b) {
  const [label, tone] = STATE_LABEL[b.state] || [b.state, ""];
  const role = b.lender_uid === store.uid ? "lending" : "borrowing";
  const open = openBooking === b.id;
  return `<article class="rental" data-id="${esc(b.id)}">
    <div class="row1">
      <h3>${esc(b.listing_title || "Tool")}</h3>
      <span class="chip ${tone}">${label}</span>
    </div>
    <div class="dates">${esc(b.start_date)} → ${esc(b.end_date)} · ${dollars(b.price.total_cents)} · <span class="role">${role}</span></div>
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
      </div>`;
    box.querySelectorAll("[data-act]").forEach((btn) => {
      btn.onclick = () => bookingAction(id, btn.dataset.act);
    });
    const input = $(`#chat-input-${CSS.escape(id)}`);
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") bookingAction(id, "send"); });
    box.querySelector(".msgs").scrollTop = 1e6;
  } catch (e) {
    box.innerHTML = `⚠️ ${esc(e.message)}`;
  }
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
    await api("POST", `/v1/bookings/${id}/${action}`);
    if (action === "approve") toast("Approved — borrower charged, deposit held.");
    if (action === "return") toast("Rental complete — payout released to you.");
    loadRentals();
  } catch (e) { toast(e.message, true); }
}

/* ---------------- profile ---------------- */

async function loadProfile() {
  $("#uid-input").value = store.uid;
  $("#whoami-name").textContent = store.uid;
  try {
    const p = await api("GET", "/v1/users/me");
    $("#profile-name").textContent = p.display_name || p.uid;
    $("#profile-avatar").textContent = (p.uid[0] || "🙂").toUpperCase();
    $("#profile-rating").textContent = p.rating_count > 0
      ? `★ ${p.rating_avg} · ${p.rating_count} review${p.rating_count > 1 ? "s" : ""}`
      : "No reviews yet";
  } catch (e) { toast(e.message, true); }
}

function switchUser() {
  const v = $("#uid-input").value.trim().toLowerCase().replace(/[^a-z0-9_-]/g, "");
  if (!v) return;
  store.uid = v;
  toast(`You're now ${v}`);
  loadProfile(); loadRentals();
}

/* ---------------- boot ---------------- */

function boot() {
  $("#category-select").innerHTML = Object.keys(CATEGORIES)
    .map((c) => `<option value="${c}">${CATEGORIES[c]} ${c.replace(/_/g, " ")}</option>`).join("");
  $("#search-btn").onclick = loadBrowse;
  $("#search-input").addEventListener("keydown", (e) => { if (e.key === "Enter") loadBrowse(); });
  $("#plan-btn").onclick = planProject;
  $("#list-form").addEventListener("submit", submitListing);
  $("#uid-btn").onclick = switchUser;
  $("#uid-input").addEventListener("keydown", (e) => { if (e.key === "Enter") switchUser(); });
  $("#whoami").onclick = () => { location.hash = "#/profile"; };
  $("#pay-btn").onclick = async () => {
    try {
      const b = await api("POST", "/v1/users/me/setup-intent");
      toast(`Payment setup ready (${b.customer_id}). Stripe PaymentSheet opens here at launch.`);
    } catch (e) { toast(e.message, true); }
  };
  $("#connect-btn").onclick = async () => {
    try {
      const r = await api("POST", "/v1/users/me/connect");
      window.open(r.onboarding_url, "_blank");
      const sweep = await api("POST", "/v1/users/me/connect/complete").catch(() => null);
      if (sweep && sweep.paid_bookings.length) toast(`Pending payouts released: ${dollars(sweep.total_cents)} 🎉`);
    } catch (e) { toast(e.message, true); }
  };
  $("#whoami-name").textContent = store.uid;
  renderLocRow();
  route();
}
boot();
