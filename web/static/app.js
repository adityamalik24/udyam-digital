"use strict";
// Draws what the server sends. It holds no prices or rules: every change goes to the server and comes back as a fresh view.
const root = document.getElementById("app");
let nav = { error: "Something went wrong. Please try again.", offline: "We can't reach the server. Check your connection and try again.", slow: "This is taking too long. Please try again." };
let renderToken = 0;
let draft = "";          // what's in the chat box, kept across redraws
let voiceNote = null;    // {tone, text} shown under the chat box
let voiceAsk = false;    // the first-use voice notice is open
let formState = {};      // call-back form values, kept across redraws
let openFolds = new Set(); // which sections the owner has opened
let kycMode = "specimen", kycApplicant = "K02", showDocs = false, kycProblems = [], pollTimer = null, kycNoGstin = false;

function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "class") el.className = v;
    else if (k === "value") el.value = v;
    else if (k === "checked" || k === "disabled" || k === "open" || k === "required" || k === "multiple") el[k] = !!v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat(Infinity)) if (kid !== null && kid !== undefined && kid !== false) el.append(kid);
  return el;
}

// Text from the server is never treated as HTML: this makes real elements for **bold** and "- " lists only.
function inline(text) {
  return String(text).split(/(\*\*[^*]+\*\*)/).filter(Boolean).map(p => p.startsWith("**") && p.endsWith("**") && p.length > 4 ? h("strong", null, p.slice(2, -2)) : p.replace(/\*\*/g, ""));
}
function rich(text) {
  const out = []; let list = null;
  for (const raw of String(text).split("\n")) {
    const line = raw.trim();
    const item = line.match(/^[-•*]\s+(.*)/);
    if (item) { if (!list) { list = h("ul"); out.push(list); } list.append(h("li", null, inline(item[1]))); continue; }
    list = null;
    if (line) out.push(h("p", null, inline(line.replace(/^#+\s*/, ""))));
  }
  return h("div", { class: "rich" }, out);
}

const ICONS = {
  chat: "M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z", price: "M6 4h12M6 9h12M6 4c7 0 9 2 9 5s-3 5-9 5l8 7", shield: "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10zM9 12l2 2 4-4", pin: "M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0zM12 13a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
  mic: "M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3zM19 11a7 7 0 0 1-14 0M12 18v4", stop: "M6 6h12v12H6z", person: "M3 18v-6a9 9 0 0 1 18 0v6M21 19a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3zM3 19a2 2 0 0 0 2 2h1a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2H3z", close: "M18 6 6 18M6 6l12 12", plus: "M12 5v14M5 12h14", speaker: "M11 5 6 9H2v6h4l5 4V5zM15.5 8.5a5 5 0 0 1 0 7M19 5a10 10 0 0 1 0 14", send: "M22 2 11 13M22 2l-7 20-4-9-9-4z",
};
function icon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24"); svg.setAttribute("class", "i"); svg.setAttribute("aria-hidden", "true");
  const p = document.createElementNS("http://www.w3.org/2000/svg", "path"); p.setAttribute("d", ICONS[name]); svg.append(p);
  return svg;
}

const go = to => (e) => { if (e) e.preventDefault(); history.pushState(null, "", to); route(); };
const link = (to, label, cls = "btn secondary full") => h("a", { href: to, class: cls, onclick: go(to) }, label);
const button = (label, onclick, cls = "btn secondary full", extra = {}) => h("button", { type: "button", class: cls, onclick, ...extra }, label);
const MARK = { success: "✓", warning: "!", danger: "!", neutral: "i" };
// Each piece of text gets its own line, so separate sentences never run together.
function note(tone, ...kids) { return h("div", { class: `note ${tone}`, role: tone === "danger" ? "alert" : "status" }, h("span", { class: "mark", "aria-hidden": "true" }, MARK[tone]), h("div", null, kids.flat(Infinity).filter(k => k !== null && k !== undefined && k !== false && k !== "").map(k => typeof k === "string" ? h("p", null, k) : k))); }
function fold(id, title, ...kids) {
  return h("details", { class: "fold", open: openFolds.has(id), ontoggle: (e) => e.target.open ? openFolds.add(id) : openFolds.delete(id) }, h("summary", null, title), h("div", { class: "inner" }, kids));
}
const check = (label, on, change, extra = {}) => h("label", { class: "check" + (extra.disabled ? " off" : "") }, h("input", { type: "checkbox", checked: on, onchange: change, ...extra }), h("span", null, label));
const field = (label, input) => h("label", { class: "field" }, label, input);
const select = (options, value, onchange, extra = {}) => h("select", { onchange, ...extra }, Object.entries(options).map(([k, v]) => { const o = h("option", { value: k }, v); if (k === value) o.selected = true; return o; }));

const WAIT_MS = 90000; // a reply that takes longer than this is given up, so nobody is left watching "Thinking…"
async function api(path, data, method = "POST") {
  let res;
  const stop = new AbortController(), timer = setTimeout(() => stop.abort(), WAIT_MS);
  try {
    res = await fetch(path, { method, credentials: "same-origin", signal: stop.signal, headers: { "X-Requested-With": "udyam", ...(data !== undefined ? { "Content-Type": "application/json" } : {}) }, body: data !== undefined ? JSON.stringify(data) : undefined });
  } catch (e) { throw new Error(e && e.name === "AbortError" ? nav.slow : nav.offline); }
  finally { clearTimeout(timer); }
  const out = await res.json().catch(() => ({}));
  if (!res.ok) { const e = new Error(out.problem || nav.error); e.status = res.status; e.problem = out.problem; throw e; }
  return out;
}
function showError(err) {
  const box = document.getElementById("flash");
  if (box) { box.replaceChildren(note("danger", err.message || nav.error)); box.scrollIntoView({ block: "nearest" }); }
}
// Runs a server action, with the button disabled meanwhile so a second tap can't repeat it.
function act(path, data, draw, method) {
  return async (e) => {
    const b = e && e.currentTarget; if (b && b.tagName === "BUTTON") b.disabled = true;
    try { const v = await api(path, data, method); if (draw) draw(v); else route(); }
    catch (err) { if (b && b.tagName === "BUTTON") b.disabled = false; showError(err); }
  };
}

function shell(v, ...content) {
  nav = { ...nav, ...v.nav };
  document.documentElement.lang = v.lang;
  document.title = (v.title ? v.title + " · " : "") + v.nav.title;
  const wide = location.pathname === "/partner";
  const setLang = (lang) => async () => { if (lang === v.lang) return; try { await api("/api/language", { lang }); } catch (err) { showError(err); return; } route(); };
  const newChat = async () => {
    if (!window.confirm(v.nav.new_confirm)) return;
    try { await api("/api/advisor/new", {}); draft = ""; quoteDraft = ""; personOpen = false; voiceNote = null; go("/advisor")(); } catch (err) { showError(err); }
  };
  const steps = v.journey && h("ol", { class: "steps" }, v.journey.map(s => h("li", { class: s.state + (s.now ? " now" : ""), "aria-current": s.now ? "step" : null },
    h("a", { href: { quote: "/quote", consent: "/consent", kyc: "/kyc", payment: "/tracker", tracker: "/tracker" }[s.key], onclick: go({ quote: "/quote", consent: "/consent", kyc: "/kyc", payment: "/tracker", tracker: "/tracker" }[s.key]), style: null, class: "steplink" },
      h("span", { class: "dot", "aria-hidden": "true" }, s.state === "done" ? "✓" : s.state === "attention" ? "!" : String(s.n)), s.label, h("span", { class: "sr" }, ` (${s.state_label})`)))));
  root.replaceChildren(h("div", { class: "shell" + (wide ? " wide" : "") },
    h("a", { class: "skip", href: "#main" }, v.nav.skip),
    h("header", { class: "top" }, h("div", { class: "bar" },
      h("a", { class: "brand", href: "/", onclick: go("/"), "aria-label": v.nav.title }, h("img", { src: "/static/icon.svg", alt: "" }), h("span", null, "Accel", h("span", { class: "brand-rest" }, " Business"))),
      h("div", { class: "bar-right" },
        !wide && h("button", { type: "button", class: "toplink plain", onclick: newChat, title: v.nav.new_chat }, icon("plus"), h("span", { class: "label" }, v.nav.new_chat)),
        h("a", { class: "toplink", href: "/data", onclick: go("/data") }, icon("shield"), h("span", { class: "label" }, v.nav.data)),
        h("div", { class: "langs", role: "group", "aria-label": v.nav.language },
          h("button", { type: "button", lang: "en", "aria-pressed": String(v.lang === "en"), onclick: setLang("en") }, "English"),
          h("button", { type: "button", lang: "hi", "aria-pressed": String(v.lang === "hi"), onclick: setLang("hi") }, "हिन्दी"))))),
    h("main", { id: "main", tabindex: "-1" }, steps, h("div", { id: "flash", "aria-live": "polite" }), content),
    h("footer", null, v.nav.banner)));
}

// ---- Home --------------------------------------------------------------------------------------------------------
function drawHome(v) {
  shell(v, h("div", { class: "stack" }, h("h1", null, v.title), h("p", { class: "muted" }, v.tag)),
    h("ul", { class: "points" }, v.points.map(p => h("li", null, h("span", { class: "bubble" }, icon(p.icon)), p.text))),
    v.resume && link(v.resume.to, v.resume.label),
    h("div", { class: "grow" }),
    h("div", { class: "sticky" }, h("p", { class: "small muted" }, v.voice), link("/advisor", v.start, "btn primary full"), link("/advisor#form", v.form)));
}

// ---- Advisor -----------------------------------------------------------------------------------------------------
let advisorView = null, sending = false, personOpen = false;
// One message bubble. A reply waiting for translation says so under it.
const bubble = (m, v) => h("li", { class: `msg ${m.role}` }, m.role === "assistant" ? [rich(m.text), m.translating ? h("p", { class: "small muted" }, v.translating) : speakButton(m.text, v)] : m.text);
function drawAdvisor(v) {
  advisorView = v;
  const keepFocus = document.activeElement && document.activeElement.id === "chatbox";
  if (location.hash === "#person") { personOpen = true; history.replaceState(null, "", "/advisor"); }
  const send = async (payload, shown) => {
    if (sending) return;
    sending = true; voiceNote = null;
    const log = document.getElementById("chatlog");
    if (shown && log) { log.append(h("li", { class: "msg user" }, shown), h("li", { class: "typing", id: "typing" }, v.typing)); log.lastChild.scrollIntoView({ block: "nearest" }); }
    const typed = draft;
    try { draft = ""; const nv = await api("/api/advisor/message", payload); sending = false; drawAdvisor(nv); focusLast(); }
    catch (err) { sending = false; draft = typed; document.getElementById("typing")?.remove(); document.querySelector("#chatlog .msg.user:last-child")?.remove(); showError(err); }
  };
  const input = h("input", { id: "chatbox", type: "text", value: draft, maxlength: "1000", autocomplete: "off", placeholder: v.placeholder, "aria-label": v.placeholder, oninput: (e) => { draft = e.target.value; document.getElementById("sendbtn").disabled = !draft.trim(); } });
  const c = v.callback;
  shell(v, h("h1", { class: "sr" }, v.title),
    // "Talk to a person" is a small button on the right; its form opens only when tapped.
    h("div", { class: "toolbar" },
      h("button", { type: "button", id: "personbtn", class: "person-pill" + (c.alert ? " alert" : ""), "aria-expanded": String(personOpen), "aria-controls": "personpanel",
        onclick: () => { personOpen = !personOpen; drawAdvisor(advisorView); if (personOpen) document.getElementById("personpanel")?.scrollIntoView({ block: "nearest" }); } }, icon("person"), h("span", null, c.title))),
    personOpen && drawCallback(c),
    h("ul", { class: "chat", id: "chatlog", "aria-live": "polite" }, v.chat.map(m => bubble(m, v))),
    v.kept && h("p", { class: "small muted" }, v.kept),
    v.chips.length ? h("div", { class: "chips" }, v.chips.map(x => h("button", { type: "button", class: "chip", onclick: () => send({ chip: x }, x) }, x))) : null,
    v.fallback && h("p", { class: "small muted" }, v.fallback),
    v.form && drawShortForm(v.form),
    h("div", { class: "grow" }),
    h("div", { class: "sticky" },
      v.has_plan && link("/quote", v.see_quote, "btn primary full"),
      voiceAsk && drawVoiceAsk(v.voice),
      h("div", { id: "voiceline" }, voiceNote && h("p", { class: "voice-line" }, voiceNote.text)),
      h("form", { class: "composer", onsubmit: (e) => { e.preventDefault(); if (draft.trim()) send({ text: draft }, draft); } },
        input,
        micButton(v.voice),
        h("button", { type: "submit", id: "sendbtn", class: "iconbtn", "aria-label": v.send, disabled: !draft.trim() }, icon("send"))),
      v.voice.ai_off ? h("p", { class: "small muted" }, v.voice.off_note) : null,
      h("p", { class: "tiny muted" }, v.ai_line, " ", h("a", { href: "/data", onclick: go("/data") }, v.nav.data))));
  if (keepFocus) { input.focus(); }
  if (location.hash === "#form") { openFolds.add("form"); const f = document.getElementById("shortform"); if (f) { f.open = true; f.scrollIntoView(); } history.replaceState(null, "", "/advisor"); }
}
// Reads a reply aloud with the phone's own voices, in the script it's written in. Nothing leaves the device.
const SPEECH = [[0x0900, 0x097f, "hi-IN"], [0x0b80, 0x0bff, "ta-IN"], [0x0c00, 0x0c7f, "te-IN"], [0x0c80, 0x0cff, "kn-IN"], [0x0d00, 0x0d7f, "ml-IN"], [0x0980, 0x09ff, "bn-IN"], [0x0a80, 0x0aff, "gu-IN"], [0x0a00, 0x0a7f, "pa-IN"]];
function speakButton(text, v) {
  if (!("speechSynthesis" in window)) return null;
  const plain = String(text).replace(/[*_#`>]/g, "").replace(/\n- /g, ". ").replace(/\n/g, ". ");
  const codes = [...plain].map(ch => ch.codePointAt(0));
  const lang = (SPEECH.find(([lo, hi]) => codes.some(c => c >= lo && c <= hi)) || [0, 0, "en-IN"])[2];
  return h("button", { type: "button", class: "speak", "aria-label": v.listen, title: v.listen, onclick: () => {
    const s = window.speechSynthesis;
    if (s.speaking) { s.cancel(); return; }
    const u = new SpeechSynthesisUtterance(plain); u.lang = lang;
    const voice = s.getVoices().find(x => x.lang === lang) || s.getVoices().find(x => x.lang.startsWith(lang.slice(0, 2)));
    if (voice) u.voice = voice;
    s.speak(u);
  } }, icon("speaker"));
}

function focusLast() { const log = document.getElementById("chatlog"); if (log && log.lastChild) log.lastChild.scrollIntoView({ block: "nearest" }); }

function drawShortForm(f) {
  const data = { kind: "kirana", city: "", tier: "0", staff: 1, sites: 1, gst: "unsure", needs: new Set(), fibre: false };
  const problem = h("div");
  const det = fold("form", f.title,
    h("form", { class: "stack", onsubmit: async (e) => {
      e.preventDefault();
      if (!data.city.trim()) { problem.replaceChildren(note("danger", f.city_missing)); return; }
      try { drawAdvisor(await api("/api/advisor/form", { ...data, needs: [...data.needs] })); focusLast(); } catch (err) { problem.replaceChildren(note("danger", err.message)); }
    } },
      field(f.kind, select(f.kinds, data.kind, e => data.kind = e.target.value)),
      field(f.city, h("input", { type: "text", maxlength: "80", oninput: e => data.city = e.target.value })),
      field(f.tier, select(f.tiers, data.tier, e => data.tier = e.target.value)),
      field(f.staff, h("input", { type: "number", min: "1", max: "100000", value: "1", oninput: e => data.staff = e.target.value })),
      field(f.sites, h("input", { type: "number", min: "1", max: "10000", value: "1", oninput: e => data.sites = e.target.value })),
      field(f.gst, select(f.gsts, data.gst, e => data.gst = e.target.value)),
      h("fieldset", { style: null, class: "stack bare" }, h("legend", { class: "small" }, f.need), Object.entries(f.needs).map(([k, l]) => check(l, false, e => e.target.checked ? data.needs.add(k) : data.needs.delete(k)))),
      check(f.fibre, false, e => data.fibre = e.target.checked),
      problem,
      h("button", { type: "submit", class: "btn primary full" }, f.submit)));
  det.id = "shortform";
  return det;
}

function drawCallback(c) {
  const close = h("button", { type: "button", class: "iconbtn small", "aria-label": c.close, title: c.close, onclick: () => { personOpen = false; drawAdvisor(advisorView); document.getElementById("personbtn")?.focus(); } }, icon("close"));
  const head = h("div", { class: "panel-head" }, h("h2", null, c.title), close);
  if (c.sent) return h("section", { class: "card", id: "personpanel" }, head, note("success", c.saved), button(c.delete, act("/api/advisor/callback", undefined, drawAdvisor, "DELETE"), "btn danger full"));
  if (c.prefill && !Object.keys(formState).length) formState = { ...c.prefill };  // from the contact step, still editable
  const data = formState;
  const problem = h("div");
  return h("section", { class: "card", id: "personpanel" }, head, h("p", { class: "small" }, c.intro),
    h("form", { class: "stack", onsubmit: async (e) => {
      e.preventDefault();
      try { const nv = await api("/api/advisor/callback", data); formState = {}; drawAdvisor(nv); } catch (err) { problem.replaceChildren(note("danger", err.message)); }
    } },
      field(c.name, h("input", { type: "text", autocomplete: "name", maxlength: "80", value: data.name || "", oninput: e => data.name = e.target.value })),
      field(c.phone, h("input", { type: "tel", autocomplete: "tel", maxlength: "16", value: data.phone || "", oninput: e => data.phone = e.target.value })),
      field(c.email, h("input", { type: "email", autocomplete: "email", maxlength: "120", value: data.email || "", oninput: e => data.email = e.target.value })),
      field(c.best, select(c.times, data.best || "Any time", e => data.best = e.target.value)),
      field(c.note, h("textarea", { maxlength: "200", rows: "2", value: data.note || "", oninput: e => data.note = e.target.value })),
      check(c.agree, !!data.agree, e => data.agree = e.target.checked),
      problem,
      h("button", { type: "submit", class: "btn secondary full" }, c.submit)));
}

// ---- Voice: records in the browser, sends 16 kHz mono WAV, and puts the words in the box. It never sends the message itself. ----
let rec = null, recTimer = null, recording = false, working = false;
const MAX_RECORD_MS = 45000;

function micButton(vc) {
  if (!vc.available) return null;
  return h("button", { type: "button", id: "micbtn", class: "iconbtn mic" + (recording ? " live" : ""), "aria-label": recording ? vc.stop : vc.mic, "aria-pressed": String(recording), disabled: working, onclick: () => recording ? stopRecording() : startVoice(vc) }, icon(recording ? "stop" : "mic"));
}
function drawVoiceAsk(vc) {
  let agreed = false;
  const on = h("button", { type: "button", class: "btn primary full", disabled: true, onclick: async () => {
    try { await api("/api/voice/consent", {}); advisorView.voice.consented = true; voiceAsk = false; drawAdvisor(advisorView); startVoice(advisorView.voice); } catch (err) { showError(err); }
  } }, vc.turn_on);
  return h("div", { class: "card pick" }, h("h2", null, vc.title), h("p", { class: "small" }, vc.notice),
    check(vc.agree, false, e => { agreed = e.target.checked; on.disabled = !agreed; }), on,
    button(vc.cancel, () => { voiceAsk = false; drawAdvisor(advisorView); }, "btn text"));
}
function setVoiceLine(text, live) {
  const box = document.getElementById("voiceline");
  if (box) box.replaceChildren(text ? h("p", { class: "voice-line" + (live ? " live" : ""), role: "status" }, text) : "");
}
function refreshMic(vc) { const b = document.getElementById("micbtn"); if (b) b.replaceWith(micButton(vc)); }

async function startVoice(vc) {
  if (!vc.consented) { voiceAsk = true; drawAdvisor(advisorView); return; }
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) { voiceNote = { text: vc.unsupported }; setVoiceLine(vc.unsupported); return; }
  let stream;
  try { stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } }); }
  catch { voiceNote = { text: vc.denied }; setVoiceLine(vc.denied); return; }
  const chunks = [];
  rec = new MediaRecorder(stream);
  rec.ondataavailable = e => { if (e.data.size) chunks.push(e.data); };
  rec.onstop = async () => {
    stream.getTracks().forEach(t => t.stop()); clearTimeout(recTimer);
    recording = false; working = true; refreshMic(vc); setVoiceLine(vc.working, true);
    try {
      const wav = await toWav(new Blob(chunks, { type: rec.mimeType }));
      const res = await fetch("/api/voice", { method: "POST", credentials: "same-origin", headers: { "X-Requested-With": "udyam", "Content-Type": "audio/wav" }, body: wav });
      const out = await res.json().catch(() => ({}));
      if (out.text) {
        draft = (draft.trim() ? draft.trim() + " " : "") + out.text;
        const box = document.getElementById("chatbox");
        if (box) { box.value = draft; box.focus(); }
        const send = document.getElementById("sendbtn"); if (send) send.disabled = false;
        voiceNote = { text: vc.check + (out.removed ? " " + vc.removed : "") };
      } else voiceNote = { text: vc.problems[out.problem] || vc.problems.unavailable };
    } catch { voiceNote = { text: vc.problems.bad_audio }; }
    working = false; refreshMic(vc); setVoiceLine(voiceNote.text);
  };
  rec.start(); recording = true; refreshMic(vc); setVoiceLine(vc.listening, true);
  recTimer = setTimeout(stopRecording, MAX_RECORD_MS);
}
function stopRecording() { if (rec && rec.state === "recording") rec.stop(); }

async function toWav(blob) {
  const AC = window.AudioContext || window.webkitAudioContext;
  const ctx = new AC();
  let decoded;
  try { decoded = await ctx.decodeAudioData(await blob.arrayBuffer()); } finally { ctx.close(); }
  const RATE = 16000, frames = Math.max(1, Math.ceil(decoded.duration * RATE));
  const off = new OfflineAudioContext(1, frames, RATE);
  const src = off.createBufferSource(); src.buffer = decoded; src.connect(off.destination); src.start();
  const pcm = (await off.startRendering()).getChannelData(0);
  const buf = new ArrayBuffer(44 + pcm.length * 2), d = new DataView(buf);
  const str = (at, s) => { for (let i = 0; i < s.length; i++) d.setUint8(at + i, s.charCodeAt(i)); };
  str(0, "RIFF"); d.setUint32(4, 36 + pcm.length * 2, true); str(8, "WAVEfmt "); d.setUint32(16, 16, true); d.setUint16(20, 1, true); d.setUint16(22, 1, true);
  d.setUint32(24, RATE, true); d.setUint32(28, RATE * 2, true); d.setUint16(32, 2, true); d.setUint16(34, 16, true); str(36, "data"); d.setUint32(40, pcm.length * 2, true);
  for (let i = 0; i < pcm.length; i++) d.setInt16(44 + i * 2, Math.max(-1, Math.min(1, pcm[i])) * 32767, true);
  return new Blob([buf], { type: "audio/wav" });
}

// ---- Quote -------------------------------------------------------------------------------------------------------
// The same conversation as the Advisor, so the owner can change the plan here. The quote is redrawn from the server after each reply.
let quoteDraft = "", quoteSending = false;
function quoteChat(c) {
  const log = h("ul", { class: "chat mini", id: "quotelog", "aria-live": "polite" }, c.messages.map(m => bubble(m, c)));
  const sendBtn = h("button", { type: "submit", class: "iconbtn", "aria-label": c.send, disabled: !quoteDraft.trim() }, icon("send"));
  const input = h("input", { id: "quotebox", type: "text", value: quoteDraft, maxlength: "1000", autocomplete: "off", placeholder: c.placeholder, "aria-label": c.placeholder, oninput: (e) => { quoteDraft = e.target.value; sendBtn.disabled = !quoteDraft.trim(); } });
  const form = h("form", { class: "composer", onsubmit: async (e) => {
    e.preventDefault();
    if (!quoteDraft.trim() || quoteSending) return;
    quoteSending = true;
    const typed = quoteDraft; quoteDraft = ""; input.value = ""; sendBtn.disabled = true;
    log.append(h("li", { class: "msg user" }, typed), h("li", { class: "typing", id: "qtyping" }, c.typing)); log.scrollTop = log.scrollHeight;
    try { await api("/api/advisor/message", { text: typed }); quoteSending = false; await route(); document.getElementById("quotebox")?.focus(); }
    catch (err) { quoteSending = false; quoteDraft = typed; document.getElementById("qtyping")?.remove(); log.lastElementChild?.remove(); input.value = typed; sendBtn.disabled = false; showError(err); }
  } }, input, sendBtn);
  setTimeout(() => { log.scrollTop = log.scrollHeight; }, 0);
  return h("section", { class: "card stack", id: "quotechat" }, h("h2", null, c.title), h("p", { class: "small muted" }, c.hint), log, c.kept && h("p", { class: "small muted" }, c.kept), form);
}
function drawQuote(v) {
  if (v.empty) { shell(v, h("h1", null, v.title), note("neutral", v.empty), quoteChat(v.chat), link("/advisor", v.advisor, "btn secondary full")); return; }
  const change = (payload) => act("/api/quote/change", payload, drawQuote);
  const money = (n) => "₹" + Number(n).toLocaleString("en-IN");
  const compareOut = h("div", { class: "stack small" });
  shell(v, h("h1", null, v.title),
    h("div", { class: "card pick" }, h("div", { class: "price", "data-testid": "price" }, money(v.monthly)), h("p", null, v.per_month), v.per_day && h("p", { class: "small muted" }, v.per_day),
      h("dl", { class: "facts" }, v.facts.map(f => h("div", { title: f.hint || null }, h("dt", null, f.label), h("dd", null, f.value))))),
    h("p", { class: "small muted" }, v.gst_note), h("p", { class: "small muted" }, v.install_note),
    quoteChat(v.chat),
    v.notes.map(n => note("neutral", n)),
    v.gap && h("p", { class: "small muted" }, v.gap),
    v.put_back && button(v.put_back, change({ action: "restore" })),
    v.alt && note(v.alt.on ? "warning" : "success", h("strong", null, v.alt.title), rich(v.alt.body), button(v.alt.button, change({ action: "alt", on: !v.alt.on }))),
    h("section", { class: "stack" }, h("h2", null, v.bundle), h("div", null, v.lines.map(l => h("div", { class: "line" },
      h("div", { class: "head" }, h("span", null, l.name + (l.qty > 1 ? ` × ${l.qty}` : "")), h("span", null, money(l.monthly))),
      h("p", { class: "small muted" }, l.description), l.why && h("p", { class: "small" }, l.why), l.peers && h("p", { class: "small muted" }, l.peers),
      l.qty_label && h("label", { class: "qty" }, l.qty_label, h("input", { type: "number", min: "1", max: String(l.max), value: String(l.qty), onchange: (e) => { const n = parseInt(e.target.value, 10); if (n >= 1) change({ action: "qty", product: l.id, value: n })(e); else e.target.value = l.qty; } })),
      l.remove && button(l.remove, change({ action: "remove", product: l.id }), "btn text"))))),
    fold("addons", v.addons_title, v.gstin_box && check(v.gstin_box.label, v.gstin_box.on, (e) => change({ action: "gstin", on: e.target.checked })(e)),
      v.addons.map(a => check(a.label + (a.reason ? ` (${a.reason})` : ""), a.on, (e) => change({ action: "addon", product: a.id, on: e.target.checked })(e), { disabled: !a.ok }))),
    fold("compare", v.compare.title, snapBill(v.compare, compareOut), field(v.compare.label, h("input", { type: "number", min: "0", step: "100", id: "billnow", onchange: (e) => compareBill(e.target.value, compareOut) })), compareOut),
    h("a", { class: "btn secondary full", href: "/api/quote/download", download: "accel_business_quote.txt" }, v.download),
    v.paid_note && h("p", { class: "small muted" }, v.paid_note),
    v.accepted && note("success", v.accepted),
    h("div", { class: "grow" }),
    h("div", { class: "sticky" },
      h("div", { class: "total-bar", "aria-live": "polite" }, h("b", null, money(v.monthly)), h("span", { class: "small muted" }, v.per_month)),
      v.has_order && v.already ? link("/consent", v.next, "btn primary full") : button(v.accept, act("/api/quote/accept", {}, drawQuote), "btn primary full")));
}

async function compareBill(now, out) {
  try { const r = await api("/api/quote/compare", { now }); out.replaceChildren(...(r.text ? [h("p", null, r.text), h("p", { class: "muted" }, r.note)] : [])); } catch (err) { showError(err); }
}
// The bill photo goes to our server, which reads the amount due and drops the photo. The owner sees the figure and can change it.
function snapBill(c, out) {
  const status = h("div");
  const input = h("input", { type: "file", id: "billsnap", class: "sr", accept: "image/png,image/jpeg", onchange: async (e) => {
    const f = e.target.files[0]; if (!f) return;
    status.replaceChildren(h("p", { class: "small muted", role: "status" }, c.reading));
    try {
      const res = await fetch("/api/quote/bill", { method: "POST", credentials: "same-origin", headers: { "X-Requested-With": "udyam", "Content-Type": "application/octet-stream" }, body: f });
      const r = await res.json().catch(() => ({}));
      if (r.amount) {
        status.replaceChildren(note("success", c.found.replace("{n}", Number(r.amount).toLocaleString("en-IN"))));
        const box = document.getElementById("billnow"); if (box) box.value = r.amount;
        compareBill(r.amount, out);
      } else status.replaceChildren(note("warning", c.not_found));
    } catch { status.replaceChildren(note("danger", nav.offline)); }
    e.target.value = "";
  } });
  return h("div", { class: "stack" }, input, h("label", { class: "btn secondary full", for: "billsnap" }, c.snap), h("p", { class: "small muted" }, c.snap_note), status);
}

// ---- Consent -----------------------------------------------------------------------------------------------------
function drawPanel(p) {
  return fold("panel", p.title, p.records.map(r => h("p", { class: "small muted" }, r)),
    h("div", { class: "stack small" }, h("strong", null, p.held_title), p.held.map(l => h("p", null, l))),
    p.receipt && h("a", { class: "btn secondary full", href: "/api/consent/receipt", download: "accel_business_consent_receipt.txt" }, p.receipt),
    p.receipt_json && h("a", { class: "btn secondary full", href: "/api/consent/receipt.json", download: "accel_business_consent_receipt.json" }, p.receipt_json),
    location.pathname !== "/data" && link("/data", p.rights, "btn text"),
    p.active.map(a => h("div", { class: "stack" }, a.effect && h("p", { class: "small muted" }, a.effect), button(a.label, act("/api/consent/withdraw", { purpose: a.purpose }), "btn danger full"))));
}
// Name and mobile for installation and updates, under their own consent box.
let contactEditing = false;
function drawContact(c) {
  if (c.saved && !contactEditing) return h("section", { class: "card stack", id: "contact" }, h("h2", null, c.title),
    note("success", `${c.saved_label}: ${c.saved.name} · ${c.saved.phone}`), button(c.edit, () => { contactEditing = true; route(); }, "btn text"));
  const d = { name: c.saved ? c.saved.name : "", phone: c.saved ? c.saved.phone : "", agree: !!c.saved }, problem = h("div");
  return h("section", { class: "card stack", id: "contact" }, h("h2", null, c.title), h("p", { class: "small" }, c.why),
    h("form", { class: "stack", onsubmit: async (e) => {
      e.preventDefault();
      try { const nv = await api("/api/contact", d); contactEditing = false; drawConsent(nv); document.getElementById("contact")?.scrollIntoView({ block: "nearest" }); } catch (err) { problem.replaceChildren(note("danger", err.message)); }
    } },
      field(c.name, h("input", { type: "text", autocomplete: "name", maxlength: "60", value: d.name, oninput: e => d.name = e.target.value })),
      field(c.phone, h("input", { type: "tel", autocomplete: "tel", inputmode: "numeric", maxlength: "16", value: d.phone, oninput: e => d.phone = e.target.value })),
      c.saved ? null : check(c.agree, false, e => d.agree = e.target.checked),
      h("p", { class: "small muted" }, c.if_no), problem,
      h("button", { type: "submit", class: "btn secondary full" }, c.save)));
}

function drawConsent(v) {
  let a = false, b = false;
  const save = h("button", { type: "button", class: "btn primary full", disabled: true, onclick: (e) => act("/api/consent", { kyc: a, updates: b }, drawConsent)(e) }, v.save);
  const tick = h("p", { class: "small muted" }, v.tick_first);
  const sync = () => { const ready = (v.kyc.given || a) && (a || b); save.disabled = !ready; tick.hidden = v.kyc.given || a; };
  shell(v, h("h1", null, v.title), h("div", { class: "card" }, rich(v.short)),
    fold("notice", v.read, rich(v.full)),
    h("section", { class: "stack" }, h("h2", null, v.keep_ready), h("ul", { class: "stack small" }, v.docs.map(d => h("li", null, h("strong", null, d.name), " ", d.why))), h("p", { class: "small muted" }, v.tip)),
    v.kyc.given ? note("success", v.kyc.given_text) : h("div", { class: "stack" }, check(v.kyc.label, false, e => { a = e.target.checked; sync(); }), h("p", { class: "small muted" }, v.kyc.if_no)),
    v.updates.given ? note("success", v.updates.given_text) : h("div", { class: "stack" }, check(v.updates.label, false, e => { b = e.target.checked; sync(); }), h("p", { class: "small muted" }, v.updates.if_no)),
    drawContact(v.contact),
    v.panel && drawPanel(v.panel),
    h("div", { class: "grow" }),
    h("div", { class: "sticky" },
      !(v.kyc.given && v.updates.given) && !v.kyc.given && tick,
      !(v.kyc.given && v.updates.given) && save,
      v.kyc.given && link("/kyc", v.next, "btn primary full")));
  sync();
  if (location.hash === "#contact") { document.getElementById("contact")?.scrollIntoView({ block: "start" }); history.replaceState(null, "", "/consent"); }
}

// ---- KYC ---------------------------------------------------------------------------------------------------------
function drawKyc(v) {
  clearTimeout(pollTimer);
  if (v.blocked) { shell(v, h("h1", null, v.title), note("warning", v.blocked), link("/consent", v.consent, "btn primary full")); return; }
  const l = v.lookup, entered = {};
  const job = v.job;
  const r = v.result;
  const files = h("input", { type: "file", id: "kycfiles", class: "sr", multiple: true, accept: "image/png,image/jpeg,application/pdf", onchange: async (e) => {
    kycProblems = [];
    const chosen = [...e.target.files];
    for (const f of chosen) {
      try {
        const res = await fetch("/api/kyc/upload", { method: "POST", credentials: "same-origin", headers: { "X-Requested-With": "udyam", "Content-Type": "application/octet-stream", "X-File-Name": encodeURIComponent(f.name) }, body: f });
        if (!res.ok) { const out = await res.json().catch(() => ({})); kycProblems.push(out.problem || nav.error); }
      } catch { kycProblems.push(nav.offline); }
    }
    route();
  } });
  const canVerify = !job.busy && (kycMode === "specimen" || v.pending > 0) && !kycProblems.length;
  const docKeys = ["gst", "udyam", "id", "bill"];
  const sdocs = v.specimen_docs[kycApplicant] || [];
  shell(v, h("h1", null, v.title),
    v.reviewed && note(v.reviewed.tone, v.reviewed.text),
    h("div", { class: "card" }, h("h2", null, l.title), h("p", { class: "small muted" }, l.intro),
      h("form", { class: "stack", onsubmit: (e) => { e.preventDefault(); act("/api/kyc/lookup", { gstin: entered.g || "", udyam: entered.u || "" }, drawKyc)(); } },
        field(l.gstin, h("input", { type: "text", maxlength: "20", placeholder: "27ABCDE1234F1Z5", autocomplete: "off", oninput: e => entered.g = e.target.value })),
        field(l.udyam, h("input", { type: "text", maxlength: "25", placeholder: "UDYAM-MH-00-1234567", autocomplete: "off", oninput: e => entered.u = e.target.value })),
        h("button", { type: "submit", class: "btn secondary full" }, l.check)),
      l.notices.map(n => note(n.tone, n.text, n.person ? link("/advisor#person", l.person, "btn text") : null))),
    h("section", { class: "stack" }, h("h2", null, v.docs_label),
      h("div", { class: "seg" }, Object.entries(v.modes).map(([k, label]) => h("button", { type: "button", "aria-pressed": String(kycMode === k), onclick: () => { kycMode = k; kycProblems = []; drawKyc(v); } }, label))),
      kycMode === "specimen" ? [
        field(v.applicant, select(Object.fromEntries(v.applicants.map(x => [x, x])), kycApplicant, e => { kycApplicant = e.target.value; drawKyc(v); })),
        check(v.show_docs, showDocs, e => { showDocs = e.target.checked; drawKyc(v); }),
        showDocs ? [sdocs.map(d => h("figure", { class: "stack" }, h("img", { class: "docimg", loading: "lazy", alt: d.name, src: `/api/kyc/specimen/${kycApplicant}/${d.key}` }), h("figcaption", { class: "small muted" }, d.name))),
          sdocs.length < docKeys.length ? h("p", { class: "small muted" }, v.only_these) : null] : null,
      ] : [
        h("p", { class: "small muted" }, v.upload_intro),
        v.no_gst && note("neutral", v.no_gst),
        v.no_gstin_label ? check(v.no_gstin_label, kycNoGstin, e => { kycNoGstin = e.target.checked; }) : null,
        files,
        h("label", { class: "btn secondary full", for: "kycfiles" }, v.choose),
        v.pending ? h("div", { class: "qty" }, h("span", null, v.pending_label), button(v.clear, async () => { await api("/api/kyc/upload", undefined, "DELETE").catch(showError); kycProblems = []; route(); }, "btn text")) : null,
        kycProblems.map(p => note("danger", p)),
      ]),
    job.error && note("danger", job.error),
    job.busy ? h("div", { class: "stack", role: "status" }, h("progress", { max: job.total || 1, value: job.done }), h("p", null, job.text), h("p", { class: "small muted" }, job.hint))
      : button(v.verify, (e) => act("/api/kyc/verify", kycMode === "specimen" ? { mode: "specimen", applicant: kycApplicant } : { mode: "upload", no_gstin: !!(v.no_gstin_label && kycNoGstin) }, (nv) => { showDocs = false; drawKyc(nv); })(e), "btn primary full", { disabled: !canVerify }),
    r && h("section", { class: "stack", id: "kycresult" }, h("h2", null, r.who),
      note({ verified: "success", needs_review: "warning", rejected: "danger" }[r.verdict], h("strong", null, r.verdict_label), r.reason),
      r.next && h("p", { class: "small" }, r.next),
      r.verdict !== "verified" && link("/advisor#person", v.person),
      r.docs.map((d, i) => { const id = `doc${i}`; if (d.issues.length) openFolds.add(id);
        return fold(id, h("span", null, h("span", { class: "tag " + d.state, "aria-hidden": "true" }, { ok: "✓", review: "!", reject: "✕", none: "–" }[d.state]), " ", d.name),
          d.issues.map(x => note(x.tone, x.text)), d.passed.map(p => h("p", { class: "small" }, "✓ " + p)),
          d.read.length ? h("div", { class: "stack small muted" }, h("strong", null, d.read_title), d.read.map(x => h("p", null, x))) : null); }),
      r.saved && h("p", { class: "small muted" }, r.saved), r.unused && h("p", { class: "small muted" }, r.unused), h("p", { class: "small muted" }, r.seconds), h("p", { class: "small muted" }, r.note)),
    v.accept_first && note("neutral", v.accept_first, link("/quote", v.quote, "btn text")),
    v.paid_notice && note("success", v.paid_notice),
    h("div", { class: "grow" }),
    h("div", { class: "sticky" },
      v.need_contact && note("warning", v.need_contact.text, link("/consent#contact", v.need_contact.link, "btn text")),
      v.pay && button(v.pay.label, act("/api/order/pay", { order: v.pay.order }, () => go("/tracker")()), "btn primary full"),
      link("/tracker", v.tracker)));
  if (job.busy) pollTimer = setTimeout(async () => { if (location.pathname === "/kyc") { try { const nv = await api("/api/view/kyc", undefined, "GET"); drawKyc(nv); if (!nv.job.busy) document.getElementById("kycresult")?.scrollIntoView({ block: "start" }); } catch { pollTimer = setTimeout(route, 4000); } } }, 1500);
}

// ---- Tracker -----------------------------------------------------------------------------------------------------
function drawTracker(v) {
  if (v.empty) { shell(v, h("h1", null, v.title), note("neutral", v.empty), link("/quote", v.quote, "btn primary full"), v.panel && drawPanel(v.panel)); return; }
  const order = v.order, demo = (action) => act("/api/order/demo", { order, action }, drawTracker);
  let newDate = v.reschedule && v.reschedule.value;
  const hold = v.hold, nx = v.next;
  shell(v, h("h1", null, v.title),
    v.orders && field(v.order_label, select(Object.fromEntries(v.orders.map(o => [o.id, o.label])), String(order), (e) => act("/api/tracker/select", { order: Number(e.target.value) }, drawTracker)())),
    h("div", { class: "card pick" }, h("h2", null, v.stage), h("progress", { max: "1", value: v.progress, "aria-label": v.stage }),
      nx && h("p", null, h("strong", null, `${nx.title}: `), `${nx.stage} · ${nx.who}`), nx && nx.estimate && h("p", { class: "small" }, nx.estimate), v.tech && h("p", { class: "small" }, v.tech)),
    v.activated && note("success", v.activated),
    hold && note("warning", hold.text, hold.detail, hold.paid, link(hold.to, hold.label, "btn text")),
    v.paid_notice && note("success", v.paid_notice),
    v.pay_failed && note("danger", v.pay_failed),
    v.need_contact && note("warning", v.need_contact.text, link("/consent#contact", v.need_contact.link, "btn text")),
    v.pay && button(v.pay, act("/api/order/pay", { order }), "btn primary full"),
    v.kyc_link && link("/kyc", v.kyc_link),
    v.delay && note("warning", h("strong", null, v.delay.title), v.delay.body, v.delay.air),
    h("ol", { class: "stepper" }, v.steps.map((s, i) => h("li", { class: s.state }, h("div", { class: "rail" }, h("span", { class: "node", "aria-hidden": "true" }, s.state === "done" ? "✓" : ""), i < v.steps.length - 1 ? h("span", { class: "wire" }) : null), h("div", { class: "body" }, h("div", { class: "label" }, s.label), s.when && h("div", { class: "small muted" }, s.when))))),
    h("p", { class: "small muted" }, v.today_note),
    v.past && h("p", { class: "small muted" }, v.past),
    v.moved.map(m => h("p", { class: "small muted" }, m)),
    v.reschedule && fold("resched", v.reschedule.title, field(v.reschedule.label, h("input", { type: "date", value: v.reschedule.value, min: v.reschedule.min, max: v.reschedule.max, onchange: e => newDate = e.target.value })), h("p", { class: "small muted" }, v.reschedule.hint), button(v.reschedule.button, (e) => act("/api/order/reschedule", { order, date: newDate }, drawTracker)(e))),
    fold("ordered", v.ordered.title, v.ordered.items.map(i => h("p", null, i.name, i.when && h("span", { class: "small muted" }, " · " + i.when))), h("p", null, h("strong", null, v.ordered.monthly)), h("p", { class: "small" }, v.ordered.setup), h("p", { class: "small" }, v.ordered.contract)),
    fold("updates", v.updates.title, v.updates.items.map(u => h("p", { class: "small" }, u)), h("p", { class: "small muted" }, v.updates.note)),
    link("/advisor#person", v.person),
    v.demo && fold("demo", v.demo.title, h("p", { class: "small muted" }, v.demo.note), v.demo.advance && button(v.demo.advance, demo("advance")), v.demo.fail && button(v.demo.fail, demo("fail")), v.demo.delay && button(v.demo.delay, demo("delay")), v.demo.blocked && h("p", { class: "small muted" }, v.demo.blocked)),
    drawPanel(v.panel));
}

function drawData(v) {
  openFolds.add("panel");
  let detail = "", sure = false;
  const sent = h("div"), erase = h("button", { type: "button", class: "btn danger full", disabled: true, onclick: async (e) => {
    e.currentTarget.disabled = true;
    try { await api("/api/data/erase", { sure: true }); draft = ""; formState = {}; openFolds = new Set(); erasedNotice = v.erased; route(); } catch (err) { showError(err); }
  } }, v.erase);
  shell(v, h("h1", null, v.title), h("p", { class: "small muted" }, v.intro),
    erasedNotice && note("success", erasedNotice),
    h("section", { class: "stack" }, h("h2", null, v.export_title), h("a", { class: "btn secondary full", href: "/api/data/export", download: "accel_business_my_data.json" }, v.export)),
    drawPanel(v.panel),
    h("section", { class: "card stack", id: "aisettings" }, h("h2", null, v.ai.title), h("p", { class: "small" }, v.ai.body),
      check(v.ai.toggle, v.ai.on, (e) => act("/api/advisor/ai", { on: e.target.checked })(e)), h("p", { class: "small muted" }, v.ai.help)),
    h("section", { class: "stack" }, h("h2", null, v.correct_title),
      field(v.correct_label, h("textarea", { rows: "3", maxlength: "500", oninput: e => detail = e.target.value })), sent,
      button(v.correct, async (e) => {
        if (!detail.trim()) { sent.replaceChildren(note("danger", v.correct_empty)); return; }
        try { await api("/api/data/correction", { detail }); sent.replaceChildren(note("success", v.correct_sent)); } catch (err) { showError(err); }
      })),
    h("section", { class: "stack" }, h("h2", null, v.erase_title), h("p", { class: "small muted" }, v.erase_note), check(v.erase_sure, false, e => { sure = e.target.checked; erase.disabled = !sure; }), erase));
  erasedNotice = null;
}
let erasedNotice = null;

// ---- Partner queue -----------------------------------------------------------------------------------------------
function table(headers, rows) {
  return h("div", { class: "scroll", tabindex: "0" }, h("table", null, h("thead", null, h("tr", null, headers.map(x => h("th", { scope: "col" }, x)))), h("tbody", null, rows.map(r => h("tr", null, r.map(c => h("td", null, c === null ? "" : String(c))))))));
}
// Staff only. Tabs are drawn here; every figure comes from the server.
let partnerTab = "dash";
const tblSection = (t) => h("section", { class: "stack" }, t.title && h("h2", null, t.title), t.note && h("p", { class: "small muted" }, t.note), t.rows.length ? table(t.headers, t.rows) : (t.empty ? note("neutral", t.empty) : null));
function drawPartner(v) {
  clearTimeout(pollTimer);
  const tabs = h("div", { class: "tabs", role: "tablist" }, v.tabs.map(t => h("button", { type: "button", role: "tab", "aria-selected": String(partnerTab === t.key), onclick: () => { partnerTab = t.key; drawPartner(v); } }, t.label)));
  const body = { dash: () => [h("p", { class: "small muted" }, v.dash.note), v.dash.tables.map(tblSection)], review: () => drawReview(v.review), leads: () => v.leads.tables.map(tblSection), money: () => drawMoney(v.money), logs: () => drawLogs(v.logs) }[partnerTab]();
  shell(v, h("h1", null, v.title), h("p", { class: "small muted" }, v.intro), tabs, h("div", { class: "stack", role: "tabpanel" }, body));
  const sc = v.review.selfcheck;
  if (sc.state === "running" && partnerTab === "review") pollTimer = setTimeout(() => { if (location.pathname === "/partner") route(); }, 2000);
}
function drawLogs(l) {
  if (!l.groups.length) return [h("p", { class: "small muted" }, l.note), note("neutral", l.empty)];
  return [h("p", { class: "small muted" }, l.note), h("div", { class: "stack" }, l.groups.map(g => h("details", { class: "fold logrow" },
    h("summary", null, h("span", { class: "logref" }, g.ref), g.who && h("span", { class: "logwho" }, g.who), h("span", { class: "muted small" }, `${g.count} ${l.count_label} · ${l.last_label}: ${g.last} · ${g.last_when}`)),
    h("div", { class: "inner" }, table(l.headers, g.steps.map(x => [x.when, x.action, x.detail]))))))];
}
function drawReview(r) {
  const sc = r.selfcheck, out = [h("p", { class: "small muted" }, r.note), tblSection(r.queue)];
  if (r.open_cases.length) {
    const d = { case: r.open_cases[0], decision: Object.keys(r.decisions)[0], note: "", maker: "" }, problem = h("div");
    out.push(h("form", { class: "card stack", onsubmit: async (e) => {
      e.preventDefault();
      try { await api("/api/partner/review/propose", d); route(); } catch (err) { problem.replaceChildren(note("danger", err.message)); }
    } }, h("h2", null, "Propose a decision"),
      field("Case", select(Object.fromEntries(r.open_cases.map(c => [c, String(c)])), String(d.case), e => d.case = Number(e.target.value))),
      field("Decision", select(r.decisions, d.decision, e => d.decision = e.target.value)),
      field("What you checked (shown to the owner; ID numbers are removed)", h("textarea", { rows: "2", maxlength: "300", oninput: e => d.note = e.target.value })),
      field("Your name", h("input", { type: "text", maxlength: "40", oninput: e => d.maker = e.target.value })), problem,
      h("button", { type: "submit", class: "btn primary full" }, "Propose")));
  }
  if (r.pending.length) out.push(h("h2", null, "Waiting for a second person"), r.pending.map(w => {
    let checker = ""; const problem = h("div");
    const go = (accept) => async () => { try { await api("/api/partner/review/confirm", { id: w.id, checker, accept }); route(); } catch (err) { problem.replaceChildren(note("danger", err.message)); } };
    return h("div", { class: "card stack" }, h("p", null, h("strong", null, w.text)), h("p", { class: "small" }, w.note),
      field("Your name (must differ)", h("input", { type: "text", maxlength: "40", oninput: e => checker = e.target.value })), problem,
      h("div", { class: "links" }, button("Confirm", go(true), "btn primary"), button("Send back", go(false), "btn secondary")));
  }));
  out.push(tblSection(r.rights));
  out.push(h("section", { class: "stack" }, h("h2", null, sc.title), h("p", { class: "small muted" }, sc.note),
    sc.state === "running" ? h("div", { class: "stack", role: "status" }, h("progress", { max: sc.total, value: sc.done }), h("p", null, `K${String(sc.done + 1).padStart(2, "0")}…`)) : button(sc.button, act("/api/partner/selfcheck", {}, () => route())),
    sc.summary && note(sc.ok ? "success" : "danger", sc.summary), sc.state === "error" && note("danger", nav.error), sc.rows.length ? table(sc.headers, sc.rows) : null));
  return out;
}
const moneyState = { segment: null, share: 0, price: 0, churn: 0 };
function drawMoney(m) {
  if (!moneyState.segment) moneyState.segment = m.default;
  const shown = h("div", { class: "stack" });
  const paint = (r) => shown.replaceChildren(h("div", { class: "facts" }, r.metrics.map(x => h("div", null, h("dt", null, x.label), h("dd", { class: "big" }, x.value),
    x.delta && h("span", { class: "tag " + ((x.delta.startsWith("-") === x.good_down) ? "ok" : "reject") }, x.delta)))), h("p", { class: "small muted" }, r.note));
  const refresh = async () => { try { paint(await api(`/api/partner/whatif?${new URLSearchParams({ segment: moneyState.segment, share: moneyState.share / 100, price: moneyState.price / 100, churn: moneyState.churn / 100 })}`, undefined, "GET")); } catch (err) { showError(err); } };
  const slider = (label, key, min, max, step, unit) => {
    const out = h("output", null, `${moneyState[key]}${unit}`);
    return h("label", { class: "field" }, h("span", null, label, " ", out), h("input", { type: "range", min, max, step, value: moneyState[key], oninput: (e) => { moneyState[key] = Number(e.target.value); out.textContent = `${e.target.value}${unit}`; }, onchange: refresh }));
  };
  paint(m);
  if (moneyState.segment !== m.default || moneyState.share || moneyState.price || moneyState.churn) refresh();
  return [field("Segment", select(Object.fromEntries(m.segments.map(x => [x, x])), moneyState.segment, e => { moneyState.segment = e.target.value; refresh(); })),
    slider("Sales moved to phone and app", "share", 0, 100, 10, "%"), slider("Price change", "price", -20, 20, 5, "%"), slider("Churn change (points)", "churn", -15, 10, 1, ""), shown];
}

// ---- Router ------------------------------------------------------------------------------------------------------
// Shown only when the server has a staff passcode set (PARTNER_PASSCODE).
function drawStaffLogin(message) {
  const d = { code: "" }, problem = h("div");
  root.replaceChildren(h("div", { class: "shell" }, h("main", null, h("section", { class: "card stack" }, h("h1", null, "Partner queue"), h("p", { class: "small" }, message),
    h("form", { class: "stack", onsubmit: async (e) => {
      e.preventDefault();
      try { await api("/api/staff/login", d); route(); } catch (err) { problem.replaceChildren(note("danger", err.message)); }
    } },
      field("Staff passcode", h("input", { type: "password", autocomplete: "current-password", maxlength: "64", oninput: e => d.code = e.target.value })),
      problem, h("button", { type: "submit", class: "btn primary full" }, "Open"))))));
  root.querySelector("input")?.focus();
}

const ROUTES = { "/": ["home", drawHome], "/advisor": ["advisor", drawAdvisor], "/quote": ["quote", drawQuote], "/consent": ["consent", drawConsent], "/kyc": ["kyc", drawKyc], "/tracker": ["tracker", drawTracker], "/data": ["data", drawData], "/partner": ["partner", drawPartner] };
let lastPath = null, translating = false;
async function route() {
  clearTimeout(pollTimer);
  const [name, draw] = ROUTES[location.pathname] || ROUTES["/"];
  const token = ++renderToken, moved = lastPath !== location.pathname;
  lastPath = location.pathname;
  try {
    const v = await api(`/api/view/${name}`, undefined, "GET");
    if (token !== renderToken) return;
    draw(v);
    // After a language switch, earlier replies are translated on the server, then the page redraws once.
    if ((v.translate || (v.chat && v.chat.translate)) && !translating) {
      translating = true;
      api("/api/advisor/translate", {}).catch(() => {}).finally(() => { translating = false; if (location.pathname === lastPath) route(); });
    }
    if (moved) { window.scrollTo(0, 0); if (name === "advisor") focusLast(); }
  } catch (err) {
    if (token === renderToken && err.status === 401 && name === "partner") { drawStaffLogin(err.message); return; }
    if (token === renderToken) root.replaceChildren(h("div", { class: "shell" }, h("main", null, note("danger", err.message), button(location.pathname === "/" ? "Try again / दोबारा कोशिश करें" : "Try again / दोबारा कोशिश करें", route, "btn primary full"))));
  }
}
window.addEventListener("popstate", route);
route();
