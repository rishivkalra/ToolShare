/* ToolShare landing — Google Sign-In wiring.
   Asks the API which auth modes are live, renders the official GIS button
   into each .gsi-slot, exchanges the Google credential for a first-party
   session token, and drops the visitor into the app. */
"use strict";

let SLOTS = ["gsi-nav", "gsi-hero", "gsi-cta"];

function toast(msg, isErr = false) {
  const el = document.createElement("div");
  el.className = "toast" + (isErr ? " err" : "");
  el.textContent = msg;
  document.querySelector("#toast-root").appendChild(el);
  setTimeout(() => el.remove(), 4200);
}

function enterApp() {
  location.href = "/app/#/browse";
}

// Referral attribution: /?ref=<uid> from an invite link survives until the
// visitor actually signs in (give $10, get $10).
const refParam = new URLSearchParams(location.search).get("ref");
if (refParam) localStorage.setItem("ts_ref", refParam);

async function onGoogleCredential(resp) {
  try {
    const r = await fetch("/v1/auth/google", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        credential: resp.credential,
        ref: localStorage.getItem("ts_ref") || "",
      }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.detail || "Sign-in failed");
    localStorage.setItem("ts_token", data.token);
    localStorage.setItem("ts_uid", data.uid);
    toast(`Welcome, ${data.display_name || "neighbor"}! 👋`);
    setTimeout(enterApp, 600);
  } catch (e) {
    toast(e.message, true);
  }
}

function renderGoogleButtons(clientId) {
  google.accounts.id.initialize({
    client_id: clientId,
    callback: onGoogleCredential,
    auto_select: false,
  });
  for (const id of SLOTS) {
    const slot = document.getElementById(id);
    if (!slot) continue;
    google.accounts.id.renderButton(slot, {
      theme: "outline",
      size: slot.classList.contains("gsi-big") ? "large" : "medium",
      shape: "pill",
      text: "continue_with",
    });
  }
}

function renderDemoButtons() {
  // Staging fallback while the Google OAuth client is being provisioned:
  // one-tap demo identity so the full product is still explorable.
  for (const id of SLOTS) {
    const slot = document.getElementById(id);
    if (!slot) continue;
    const btn = document.createElement("button");
    btn.className = "btn btn-primary" + (slot.classList.contains("gsi-big") ? " btn-big" : "");
    btn.textContent = id === "gsi-nav" ? "Sign in" : "Try the demo →";
    btn.onclick = () => {
      localStorage.removeItem("ts_token");
      localStorage.setItem("ts_uid", "demo");
      enterApp();
    };
    slot.appendChild(btn);
  }
}

async function boot() {
  // Already signed in? The nav slot becomes a shortcut back into the app.
  if (localStorage.getItem("ts_token")) {
    const nav = document.getElementById("gsi-nav");
    const btn = document.createElement("a");
    btn.className = "btn btn-primary";
    btn.textContent = "Back to the app →";
    btn.href = "/app/#/browse";
    nav.appendChild(btn);
    SLOTS = SLOTS.filter((id) => id !== "gsi-nav");
  }

  let cfg = { google_client_id: "", dev_auth: true };
  try {
    cfg = await (await fetch("/v1/auth/config")).json();
  } catch { /* API down — leave static page usable */ }

  if (cfg.google_client_id) {
    const s = document.createElement("script");
    s.src = "https://accounts.google.com/gsi/client";
    s.async = true;
    s.onload = () => renderGoogleButtons(cfg.google_client_id);
    s.onerror = renderDemoButtons;
    document.head.appendChild(s);
  } else if (cfg.dev_auth) {
    renderDemoButtons();
  } else {
    // Neither mode available: hide empty slots.
    SLOTS.forEach((id) => document.getElementById(id)?.remove());
  }
}

boot();
