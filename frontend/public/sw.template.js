/* FlintApply web push service worker (IMPLEMENTATION_PLAN §6b) */
const SW_VERSION = process.env.NEXT_PUBLIC_GIT_SHA || "dev";
const VAPID_PUBLIC_KEY = "__VAPID_PUBLIC_KEY__";

function base64ToUint8Array(value) {
  const normalized = (value || "").replace(/-/g, "+").replace(/_/g, "/");
  const padding = "=".repeat((4 - (normalized.length % 4)) % 4);
  const raw = atob(normalized + padding);
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) out[i] = raw.charCodeAt(i);
  return out;
}

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

      const title = payload.title || "FlintApply";
      const body = payload.body || "You have a new notification";
      const url = payload.url || "/notifications";
      const tag = payload.tag || "flintapply";
      const notificationId = payload.notification_id || null;

      await self.registration.showNotification(title, {
        body,
        tag,
        data: {
          url,
          notification_id: notificationId,
          sw_version: SW_VERSION,
        },
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
          /* best-effort */
        }
      }

      const clients = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
      const target = new URL(targetUrl, self.location.origin).toString();
      for (const client of clients) {
        if (client.url === target && "focus" in client) {
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
      if (!VAPID_PUBLIC_KEY) return;
      const base = self.location.origin;
      const appServerKey = base64ToUint8Array(VAPID_PUBLIC_KEY);
      let subscription = event.newSubscription;
      if (!subscription) {
        subscription = await self.registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: appServerKey,
        });
      }
      const json = subscription ? subscription.toJSON() : null;
      if (!json?.endpoint || !json?.keys) return;

      await fetch(`${base}/api/notifications/web-push/subscribe`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          endpoint: json.endpoint,
          expiration_time: json.expirationTime ? new Date(json.expirationTime).toISOString() : null,
          keys: json.keys,
          user_agent: "",
          platform_hint: "pushsubscriptionchange",
        }),
      });
    })()
  );
});
