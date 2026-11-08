// Makes the site installable. It caches nothing: every screen, price and verdict comes fresh from the server,
// and no chat or document is ever kept on the phone. With no connection, pages get a short offline message.
const OFFLINE = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Offline · Accel Business</title><style>body{font-family:system-ui,sans-serif;margin:0;padding:32px 20px;color:#1f2933;background:#fff}h1{font-size:20px;color:#930d26}p{line-height:1.5}</style></head>
<body><h1>You're offline</h1><p>Accel Business needs an internet connection. Please reconnect and try again.</p>
<h1 lang="hi">आप ऑफ़लाइन हैं</h1><p lang="hi">Accel Business के लिए इंटरनेट ज़रूरी है। कृपया फिर से कनेक्ट करके कोशिश करें।</p></body></html>`;

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", (e) => {
  if (e.request.mode !== "navigate") return;  // everything else goes straight to the network, untouched
  e.respondWith(fetch(e.request).catch(() => new Response(OFFLINE, { headers: { "Content-Type": "text/html; charset=utf-8" } })));
});
