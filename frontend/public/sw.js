/* Smart Resume web push service worker (IMPLEMENTATION_PLAN §6b) */
const SW_VERSION = "dev";

self.addEventListener("install", (event) => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("push", (event) => {
  event.waitUntil(
    (async () => {
      let payload = {};
      try {
        payload = event.data ? event.data.json() : {};
      } catch {
        payload = {};
      }
      const title = payload.title || "Smart Resume";
      const body = payload.body || "You have a new notification";
      const tag = payload.tag || "smart-resume";
      const url = payload.url || "/notifications";
      const notificationId = payload.notification_id || null;

      if (!event.data || !payload.title) {
        try {
          const base = self.location.origin;
          await fetch(`${base}/api/notifications/unread-count`, { credentials: "include" });
        } catch {
          /* offline — ignore */
        }
      }

      await self.registration.showNotification(title, {
        body,
        tag,
        data: { url, notification_id: notificationId, sw_version: SW_VERSION },
      });
    })()
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const data = event.notification.data || {};
  const targetUrl = data.url || "/notifications";
  const notificationId = data.notification_id;

  event.waitUntil(
    (async () => {
      if (notificationId) {
        try {
          const base = self.location.origin;
          await fetch(`${base}/api/notifications/${notificationId}/read`, {
            method: "PATCH",
            credentials: "include",
          });
        } catch {
          /* best-effort offline */
        }
      }
      const clients = await self.clients.matchAll({
        type: "window",
        includeUncontrolled: true,
      });
      for (const client of clients) {
        if (client.url.includes(targetUrl) && "focus" in client) {
          return client.focus();
        }
      }
      if (self.clients.openWindow) {
        return self.clients.openWindow(targetUrl);
      }
    })()
  );
});

self.addEventListener("pushsubscriptionchange", (event) => {
  event.waitUntil(
    (async () => {
      const base = self.location.origin;
      let subscription = event.newSubscription;
      if (!subscription) {
        subscription = await self.registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: undefined,
        });
      }
      if (!subscription) return;
      const json = subscription.toJSON();
      await fetch(`${base}/api/notifications/web-push/subscribe`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          endpoint: json.endpoint,
          expiration_time: json.expirationTime
            ? new Date(json.expirationTime).toISOString()
            : null,
          keys: json.keys,
          user_agent: "",
          platform_hint: "pushsubscriptionchange",
        }),
      });
    })()
  );
});
