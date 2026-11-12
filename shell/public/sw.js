/* global self, URL */
self.addEventListener("push", (event) => {
  let message = { title: "arga", body: "", href: "/" };
  try {
    message = { ...message, ...event.data.json() };
  } catch {
  }
  event.waitUntil(
    self.registration.showNotification(message.title, {
      body: message.body,
      icon: "/icon-192.png",
      badge: "/icon-192.png",
      data: { href: message.href },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const href = (event.notification.data && event.notification.data.href) || "/";
  const target = new URL(href, self.location.origin).href;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      for (const one of windows) {
        if (one.url === target && "focus" in one) return one.focus();
      }
      return self.clients.openWindow(target);
    }),
  );
});
