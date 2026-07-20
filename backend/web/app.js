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
  loc: { ...DEMO_LOC, usingDemo: true },
  profiles: {},   // uid -> public profile cache
  photoBlob: null, // pending listing photo
};

async function api(method, path, body) {
  const resp = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json", Authorization: `Bearer dev:${store.uid}` },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return handleResp(resp);
}

async function apiUpload(path, blob, filename) {
  const form = new FormData();
  form.append("file", blob, filename);
  const resp = await fetch(path, {
    method: "POST",
    headers: { Authorization: `Bearer dev:${store.uid}` },
    body: form,
  });
  return handleResp(resp);
}

async function handleResp(resp) {
  const data = resp.status === 204 ? null : await resp.json().catch(() => null);
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
    const results = await api("GET", `/v1/listings/search?${params}`);
    if (!results.length) {
      grid.innerHTML = `<div class="empty"><span class="big">🌱</span>No tools here yet.<br>Be the first — list one from the <b>List</b> tab.</div>`;
      return;
    }
    grid.innerHTML = results.map(toolCard).join("");
    grid.querySelectorAll(".toolcard").forEach((el) => {
      el.onclick = () => openListing(el.dataset.id);
    });
  } catch (e) {
    grid.innerHTML = `<div class="empty">⚠️ ${esc(e.message)}</div>`;
  }
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

async function openListing(id) {
  const l = await api("GET", `/v1/listings/${id}`).catch((e) => (toast(e.message, true), null));
  if (!l) return;
  const owner = await profileOf(l.owner_uid);
  let days = 1;
  const fee = (rental) => Math.max(Math.round(rental * 0.15), 100);
  const render = () => {
    const rental = l.price_per_day_cents * days;
    $("#m-days").textContent = `${days} day${days > 1 ? "s" : ""} · starting tomorrow`;
    $("#m-total").innerHTML =
      `${dollars(rental)} rental + ${dollars(fee(rental))} service fee` +
      (l.deposit_cents ? `<br>+ ${dollars(l.deposit_cents)} refundable deposit hold (released on safe return)` : "") +
      `<div class="grand">Total ${dollars(rental + fee(rental))}</div>`;
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
        ${owner.rating_count ? `<span class="chip ok">★ ${owner.rating_avg}</span>` : `<span class="chip">new lender</span>`}</p>
      ${l.description ? `<p style="margin:10px 0">${esc(l.description)}</p>` : ""}
      <div class="stepper">
        <button id="m-minus">−</button><b id="m-days"></b><button id="m-plus">+</button>
      </div>
      <div class="totalbox" id="m-total"></div>
      <button class="btn btn-primary btn-big" id="m-request" style="width:100%">Request to rent</button>
      <p class="fineprint">You're only charged if the owner accepts. Exact pickup address is shared after confirmation.</p>
      <button class="report-link" id="m-report">Report this listing</button>
    </div>
  `);
  render();
  $("#m-minus").onclick = () => { days = Math.max(1, days - 1); render(); };
  $("#m-plus").onclick = () => { days = Math.min(7, days + 1); render(); };
  $("#m-report").onclick = () => reportTarget("listing", l.id);
  $("#m-request").onclick = async () => {
    try {
      await api("POST", "/v1/bookings", { listing_id: l.id, start_date: isoInDays(1), end_date: isoInDays(days) });
      closeModal();
      toast("Requested! The owner has 24h to accept — track it in Rentals.");
      location.hash = "#/rentals";
    } catch (e) {
      if (handleCardRequired(e)) { closeModal(); return; }
      toast(e.message, true);
    }
  };
}

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
    loadMyTools();
  } catch (e) { toast(e.message, true); }
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
      const rows = h && h.entries.length
        ? `<table><tr><th>Renter</th><th>Dates</th><th>Days</th><th>Earned</th></tr>` +
          h.entries.map((e) =>
            `<tr><td>${esc(e.borrower_name)}</td><td>${esc(e.start_date)} → ${esc(e.end_date)}</td>` +
            `<td>${e.days}</td><td>${dollars(e.earned_cents)}</td></tr>`).join("") + `</table>`
        : `<p class="opt" style="margin-top:8px">No rentals yet for this tool.</p>`;
      return `<div class="mytool" data-i="${i}">
        <div class="row1"><span>${CATEGORIES[t.category] || "🧰"}</span><span class="t">${esc(t.title)}</span>${active}</div>
        <div class="sub">${dollars(t.price_per_day_cents)}/day · rented ${h ? h.times_rented : 0}× · ${h ? h.total_days_rented : 0} days total · earned ${dollars(h ? h.total_earned_cents : 0)}</div>
        <div class="hist" style="display:none">${rows}</div>
      </div>`;
    }).join("");
    listEl.querySelectorAll(".mytool").forEach((el) => {
      el.onclick = () => {
        const hist = el.querySelector(".hist");
        hist.style.display = hist.style.display === "none" ? "block" : "none";
      };
    });
  } catch (e) {
    listEl.innerHTML = `<p class="opt">⚠️ ${esc(e.message)}</p>`;
  }
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
  store.uid = v;
  openBooking = null;
  toast(`You're now ${v}`);
  loadProfile();
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
  $("#whoami-name").textContent = store.uid;
  $("#whoami-dot").textContent = initial(store.uid);
  renderLocRow();
  route();
}
boot();
