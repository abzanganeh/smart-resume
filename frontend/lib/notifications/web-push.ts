const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const VAPID_PUBLIC = process.env.NEXT_PUBLIC_WEB_PUSH_VAPID_PUBLIC_KEY ?? "";

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  const arr = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i);
  return arr;
}

export async function registerWebPush(accessToken: string): Promise<boolean> {
  if (!VAPID_PUBLIC) {
    throw new Error("Web push is not configured (missing VAPID public key)");
  }
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    throw new Error("This browser does not support web push");
  }

  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    return false;
  }

  const registration = await navigator.serviceWorker.register("/sw.js", {
    scope: "/",
  });
  await navigator.serviceWorker.ready;

  let subscription = await registration.pushManager.getSubscription();
  if (!subscription) {
    subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC),
    });
  }

  const json = subscription.toJSON();
  const res = await fetch(`${BASE}/api/notifications/web-push/subscribe`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify({
      endpoint: json.endpoint,
      expiration_time: json.expirationTime
        ? new Date(json.expirationTime).toISOString()
        : null,
      keys: json.keys,
      user_agent: navigator.userAgent,
      platform_hint: navigator.platform,
    }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `Subscribe failed (${res.status})`);
  }
  return true;
}

export async function unregisterWebPush(accessToken: string): Promise<void> {
  const registration = await navigator.serviceWorker.getRegistration("/");
  const sub = await registration?.pushManager.getSubscription();
  if (sub) {
    await fetch(
      `${BASE}/api/notifications/web-push/subscribe?endpoint=${encodeURIComponent(sub.endpoint)}`,
      {
        method: "DELETE",
        headers: { Authorization: `Bearer ${accessToken}` },
      }
    );
    await sub.unsubscribe();
  }
}
