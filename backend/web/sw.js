/* ToolShare service worker: Web Push display + click-through. */
"use strict";

self.addEventListener("push", (event) => {
  let data = { title: "ToolShare", body: "", url: "/app/#/rentals" };
  try { data = { ...data, ...event.data.json() }; } catch { /* plain text */ }
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      data: { url: data.url },
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || "/app/#/rentals";
  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((wins) => {
      for (const w of wins) {
        if (w.url.includes("/app/")) { w.focus(); w.navigate(url); return; }
      }
      return clients.openWindow(url);
    })
  );
});
