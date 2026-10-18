/* Matrix web app. Plain JavaScript, no build step. */

// ------------------------------------------------------------------ small helpers
const $ = (id) => document.getElementById(id);
const store = {
  get(k, session = false) { try { return (session ? sessionStorage : localStorage).getItem(k); } catch { return null; } },
  set(k, v, session = false) {
    try { const s = session ? sessionStorage : localStorage; v == null ? s.removeItem(k) : s.setItem(k, v); } catch { /* unavailable */ }
  },
};

function el(tag, attrs = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") n.className = v;
    else if (k === "text") n.textContent = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat(Infinity)) if (kid != null && kid !== false) n.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return n;
}
const svg = (path, label) => {
  const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  s.setAttribute("viewBox", "0 0 24 24");
  if (label) s.setAttribute("aria-label", label); else s.setAttribute("aria-hidden", "true");
  const p = document.createElementNS("http://www.w3.org/2000/svg", "path");
  p.setAttribute("d", path); s.append(p); return s;
};
const ICON = {
  mic: "M12 15a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-2.08A7 7 0 0 0 19 12z",
  stop: "M7 7h10v10H7z",
  pin: "M12 2a7 7 0 0 0-7 7c0 5.25 7 13 7 13s7-7.75 7-13a7 7 0 0 0-7-7zm0 9.5A2.5 2.5 0 1 1 12 6.5a2.5 2.5 0 0 1 0 5z",
  nav: "M21 3 3 10.5l7 2.5 2.5 7z",
  back: "M15.4 7.4 14 6l-6 6 6 6 1.4-1.4L10.8 12z",
  down: "M5 20h14v-2H5zM19 9h-4V3H9v6H5l7 7z",
  speaker: "M3 9v6h4l5 5V4L7 9H3zm13.5 3A4.5 4.5 0 0 0 14 8v8a4.5 4.5 0 0 0 2.5-4zM14 3.23v2.06a7 7 0 0 1 0 13.42v2.06A9 9 0 0 0 14 3.23z",
  mail: "M20 4H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2zm0 4-8 5-8-5V6l8 5 8-5z",
  phone: "M6.6 10.8a15.1 15.1 0 0 0 6.6 6.6l2.2-2.2a1 1 0 0 1 1-.25 11.4 11.4 0 0 0 3.6.57 1 1 0 0 1 1 1V20a1 1 0 0 1-1 1A17 17 0 0 1 3 4a1 1 0 0 1 1-1h3.5a1 1 0 0 1 1 1c0 1.25.2 2.45.57 3.57a1 1 0 0 1-.25 1z",
};

function fill(node, parts) { node.replaceChildren(...parts.flat(Infinity).filter((x) => x != null && x !== false)); }

function toast(msg, ms = 4000) {
  const n = $("toast"); n.textContent = msg; n.hidden = false;
  clearTimeout(toast.t); toast.t = setTimeout(() => (n.hidden = true), ms);
}
const srOnly = (text) => el("span", { class: "sr-only", text });
const newTab = () => srOnly(` ${t("newTab")}`);

// Report by email is hidden until an email service is connected (set to true to show the "Email me" button).
const SHOW_EMAIL = false;

// ------------------------------------------------------------------ state
const S = {
  cfg: null,
  lang: store.get("ss_lang") || "ne",
  user: null,            // {name, email}
  getToken: async () => null,
  place: loadPlace(),    // {district} or {lat,lng}
  report: null,          // the report on screen (in S.lang)
  reports: loadReports(), // {id, ne, en}: the same report in both languages
  flow: { step: "idle", text: "", alarm: null },
};
const t = (k, ...a) => { const v = (window.I18N[S.lang] || window.I18N.ne)[k]; return typeof v === "function" ? v(...a) : v; };
const deptLabel = (d) => (S.cfg && S.cfg.departments[d] ? S.cfg.departments[d][S.lang] : d);
const hName = (h) => (S.lang === "ne" && h.name_ne ? h.name_ne : h.name);

function loadPlace() {
  try { return JSON.parse(store.get("ss_place_gps", true) || "null") || (store.get("ss_district") ? { district: store.get("ss_district") } : null); }
  catch { return null; }
}
function loadReports() { try { return JSON.parse(store.get("ss_reports", true) || "null"); } catch { return null; } }
function saveReports(R) { S.reports = R; store.set("ss_reports", R ? JSON.stringify(R) : null, true); }
function placeParams() {
  if (!S.place) return {};
  return S.place.lat != null ? { lat: S.place.lat, lng: S.place.lng } : { district: S.place.district };
}
function placeLabel() {
  if (!S.place) return t("choosePlace");
  return S.place.lat != null ? t("myLocation") : S.place.district;
}

// ------------------------------------------------------------------ api
// AI calls (voice, report, audio, PDF) are slow; everything else should answer within seconds.
const SLOW = 90000;

async function api(path, { method = "GET", body, form, params, auth = false, raw = false, timeout = 20000 } = {}) {
  const url = new URL(path, location.origin);
  for (const [k, v] of Object.entries(params || {})) if (v != null && v !== "") url.searchParams.set(k, v);
  const headers = {};
  if (auth) { const tok = await S.getToken(); if (tok) headers.Authorization = `Bearer ${tok}`; }
  let payload;
  if (form) payload = form;
  else if (body !== undefined) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
  let res;
  for (let attempt = 0; ; attempt += 1) {
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), timeout);
    try { res = await fetch(url, { method, headers, body: payload, signal: ctl.signal }); break; }
    catch (err) {
      // reads retry once on a dropped connection; timeouts and failed writes are reported
      if (method === "GET" && attempt === 0 && err.name !== "AbortError") continue;
      throw new Error(err.name === "AbortError" ? t("slowNet") : t("netError"));
    } finally { clearTimeout(timer); }
  }
  if (raw && res.ok) return res;
  let data = null; try { data = await res.json(); } catch { /* not JSON */ }
  if (!res.ok) {
    const msg = data && (typeof data.detail === "string" ? data.detail : null);
    const e = new Error(msg || t("netError")); e.status = res.status; e.data = data; throw e;
  }
  return data;
}

// ------------------------------------------------------------------ login
let firebaseAuth = null;
let afterLogin = null;

async function initAuth() {
  if (S.cfg.auth_mode === "firebase" && S.cfg.firebase && S.cfg.firebase.apiKey) {
    const V = "10.12.2";
    const appMod = await import(`https://www.gstatic.com/firebasejs/${V}/firebase-app.js`);
    const authMod = await import(`https://www.gstatic.com/firebasejs/${V}/firebase-auth.js`);
    const fbApp = appMod.initializeApp(S.cfg.firebase);
    const auth = authMod.getAuth(fbApp);
    firebaseAuth = { auth, ...authMod };
    S.getToken = async () => (auth.currentUser ? auth.currentUser.getIdToken() : null);
    await new Promise((resolve) => {
      authMod.onAuthStateChanged(auth, async (u) => {
        S.user = u ? { name: u.displayName || (u.email || "").split("@")[0], email: u.email || "" } : null;
        renderHeader(); resolve();
        if (u) syncLogin().catch((err) => console.error("Saving the account failed", err));
        if (u && afterLogin) { const f = afterLogin; afterLogin = null; f(); }
      });
    });
    authMod.getRedirectResult(auth).then((r) => { if (r && r.user) celebrateLogin(r.user.displayName || r.user.email || ""); }).catch(() => {});
  } else {
    const name = store.get("ss_dev_name");
    S.user = name ? { name, email: "" } : null;
    S.getToken = async () => (S.user ? `dev:${S.user.name}` : null);
    if (S.user) api("/api/me", { auth: true }).then((p) => { if (S.user) S.user.email = p.email; }).catch(() => {});
  }
}

// Save the account (and email) in the database after each sign-in.
async function syncLogin(email = "") {
  const p = await api("/api/login", { method: "POST", auth: true, body: { email } });
  if (S.user) S.user.email = p.email;
  return p;
}

function openLogin(reason) {
  $("loginTitle").textContent = t("loginTitle");
  $("loginWhy").textContent = reason || t("loginWhy");
  $("loginError").hidden = true;
  const fb = S.cfg.auth_mode === "firebase";
  $("googleBtn").hidden = !fb; $("devLogin").hidden = fb;
  $("googleLabel").textContent = t("google");
  $("devNameLabel").textContent = t("devName"); $("devGo").textContent = t("devGo"); $("devNote").textContent = t("devNote");
  $("devEmailLabel").textContent = t("devEmail");
  $("loginCancel").textContent = t("cancel");
  showSheet("loginSheet");
  if (!fb) $("devName").focus();
}

// Dialogs hand focus back to whatever opened them (see the "close" listeners in start()).
function showSheet(id) { const d = $(id); d.opener = document.activeElement; d.showModal(); }

function requireLogin(reason, then) {
  if (S.user) { then(); return; }
  afterLogin = then; openLogin(reason);
}

async function googleLogin() {
  const { auth, GoogleAuthProvider, signInWithPopup, signInWithRedirect } = firebaseAuth;
  const provider = new GoogleAuthProvider();
  try {
    const cred = await signInWithPopup(auth, provider);
    $("loginSheet").close(); celebrateLogin(cred.user.displayName || cred.user.email || "");
  }
  catch (e) {
    if (e && (e.code === "auth/popup-blocked" || e.code === "auth/operation-not-supported-in-this-environment")) {
      await signInWithRedirect(auth, provider);
    } else if (!(e && e.code === "auth/popup-closed-by-user")) {
      console.error("Google sign-in failed", e);  // the Firebase code (e.g. auth/unauthorized-domain) is in the console
      $("loginError").textContent = t("loginFailed"); $("loginError").hidden = false;
    }
  }
}

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$/;

async function devLogin() {
  const name = $("devName").value.trim();
  const email = $("devEmail").value.trim();
  if (!name) { $("devName").focus(); return; }
  if (!EMAIL_RE.test(email)) { $("loginError").textContent = t("emailNeeded"); $("loginError").hidden = false; $("devEmail").focus(); return; }
  S.user = { name, email };
  try { await syncLogin(email); }
  catch (e) { S.user = null; $("loginError").textContent = e.message; $("loginError").hidden = false; return; }
  store.set("ss_dev_name", name);
  $("loginSheet").close(); renderHeader(); celebrateLogin(name);
  if (afterLogin) { const f = afterLogin; afterLogin = null; f(); }
}

// Green tick after an explicit sign-in (not when a saved session is restored on page load).
function celebrateLogin(name) {
  document.querySelectorAll(".login-ok").forEach((n) => n.remove());
  const tick = el("span", { class: "login-ok-tick", "aria-hidden": "true" });
  tick.innerHTML = '<svg viewBox="0 0 52 52"><circle cx="26" cy="26" r="24"/><path d="M15 27l7 7 15-15"/></svg>';
  const box = el("div", { class: "login-ok", role: "status" }, tick,
    el("b", { text: t("loggedIn") }), name ? el("span", { class: "login-ok-name", text: name }) : null);
  document.body.append(box);
  setTimeout(() => box.remove(), 2000);
}

function openAccount(note) {
  $("accountName").textContent = S.user.name;
  $("accountEmailLabel").textContent = t("emailLabel"); $("accountEmail").value = S.user.email || "";
  $("accountEmail").placeholder = t("emailPh"); $("accountSave").textContent = t("emailSave");
  $("accountNote").textContent = note || t("emailWhy");
  $("logoutBtn").textContent = t("logout"); $("accountClose").textContent = t("close");
  $("accountEmail").removeAttribute("aria-invalid");
  showSheet("accountSheet");
  if (note) $("accountEmail").focus();
}

async function saveEmail() {
  const email = $("accountEmail").value.trim();
  if (!EMAIL_RE.test(email)) {
    $("accountNote").textContent = t("emailNeeded"); $("accountEmail").setAttribute("aria-invalid", "true");
    $("accountEmail").focus(); return;
  }
  try {
    const p = await api("/api/me", { method: "PUT", auth: true, body: { email } });
    S.user.email = p.email; toast(t("emailSaved")); $("accountSheet").close();
    if (saveEmail.then) { const f = saveEmail.then; saveEmail.then = null; f(); }
  } catch (e) { toast(e.message); }
}

async function logout() {
  if (firebaseAuth) await firebaseAuth.signOut(firebaseAuth.auth);
  store.set("ss_dev_name", null);
  S.user = null; S.report = null; saveReports(null);
  $("accountSheet").close(); renderHeader(); route();
}

function renderHeader() {
  document.documentElement.lang = S.lang;
  $("brandName").textContent = t("brand");
  $("langBtn").textContent = t("other");
  $("loginBtn").textContent = t("login");  $("loginBtn").hidden = Boolean(S.user);
  $("avatarBtn").hidden = !S.user;
  if (S.user) { $("avatarBtn").textContent = (S.user.name || "?").trim().charAt(0).toUpperCase(); $("avatarBtn").setAttribute("aria-label", S.user.name); }
}

// ------------------------------------------------------------------ place
function openPlace(onDone) {
  $("placeTitle").textContent = t("placeTitle"); $("gpsBtn").textContent = t("useGps");
  $("districtLabel").textContent = t("orDistrict"); $("placeCancel").textContent = t("cancel"); $("placeSave").textContent = t("save");
  const sel = $("districtSel"); sel.replaceChildren(el("option", { value: "", text: "—" }));
  for (const d of S.cfg.districts) sel.append(el("option", { value: d, text: d, selected: S.place && S.place.district === d }));
  openPlace.done = onDone; showSheet("placeSheet");
}
function setPlace(p) {
  S.place = p;
  if (p && p.lat != null) { store.set("ss_place_gps", JSON.stringify(p), true); }
  else { store.set("ss_place_gps", null, true); store.set("ss_district", p ? p.district : null); }
  if (openPlace.done) { const f = openPlace.done; openPlace.done = null; f(); }
}
function getGps() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) return reject();
    navigator.geolocation.getCurrentPosition((pos) => {
      const { latitude: lat, longitude: lng } = pos.coords;
      if (lat < 26 || lat > 31 || lng < 79.5 || lng > 88.5) return reject();
      resolve({ lat: +lat.toFixed(4), lng: +lng.toFixed(4) });
    }, reject, { timeout: 10000, maximumAge: 600000 });
  });
}

// ------------------------------------------------------------------ shared bits
function starsText(r) { return r && r.count ? `★ ${r.avg}` : ""; }
// "★ 4.5" is read out as "4.5 out of 5 stars"
const starsBadge = (avg) => {
  const a = Number(avg).toFixed(1);  // JSON turns 5.0 into 5; always show one decimal
  return el("span", { class: "stars", role: "img", "aria-label": t("outOf5", a) }, `★ ${a}`);
};
function ratingLine(r) {
  return r && r.count ? el("span", { class: "rating-line" }, starsBadge(r.avg), el("span", { class: "muted", text: ` (${t("reviews", r.count)})` }))
    : el("span", { class: "muted", text: t("noReviews") });
}
function mapFrame(src, name) {
  return el("iframe", { src, title: t("mapOf", name), loading: "lazy", referrerpolicy: "no-referrer-when-downgrade", allowfullscreen: true });
}
function stepsList(items) { return el("ol", { class: "steps" }, items.map((s) => el("li", { text: s }))); }
function plainList(items) { return el("ul", { class: "plain" }, items.map((s) => el("li", { text: s }))); }
function block(title, ...content) { return el("section", { class: "block" }, el("h2", { text: title }), ...content); }

// ------------------------------------------------------------------ home: QS-style ranking
const PAGE = 24;  // cards rendered at a time; "show more" adds the next page
let rankState = { q: "", province: "", type: "", erOnly: false, sort: "rank", data: null, lang: null, shown: PAGE };

function scoreBar(v) {
  return el("span", { class: "rk-score" }, el("span", { class: "rk-bar", "aria-hidden": "true" }, el("i", { style: `width:${v}%` })), el("b", { text: Math.round(v) }));
}

// Patient rating on a card: the real stars people gave (the score behind it is a Bayesian average, see ranking.py).
function ratingValue(h) {
  if (!h.rating || !h.rating.count) return el("span", { class: "muted", text: t("noReviews") });
  return el("span", { class: "rk-rate" }, starsBadge(h.rating.avg), el("span", { class: "muted", text: ` (${h.rating.count})` }));
}

function startHelp(recordNow) {
  requireLogin(t("loginWhyHelp"), () => {
    S.flow = recordNow ? { step: "idle", text: "" } : { step: "confirm", typed: true, text: "" };
    startRecordingSoon = recordNow;
    if (location.hash === "#/help") viewHelp(); else location.hash = "#/help";
  });
}

function viewHome() {
  const v = $("view");
  // The main job first: describe the problem and get pointed to the right hospital.
  const help = el("section", { class: "help home-help" },
    el("h1", { text: t("helpTitle") }),
    el("p", { text: `${t("ctaSub")} ${t("animalsToo")}` }),
    el("button", { class: "mic", type: "button", "aria-label": t("startSpeaking"), onclick: () => startHelp(true) }, svg(ICON.mic)),
    el("div", { class: "mic-label", text: t("startSpeaking") }),
    el("p", { class: "note privacy", text: t("voicePrivacy") }),
    el("button", { class: "text-btn", type: "button", onclick: () => startHelp(false) }, t("typeInstead")));

  const stats = el("div", { class: "rk-stats", id: "rkStats" });
  const refilter = () => { rankState.shown = PAGE; renderRanking(); };
  const sel = (key, label, opts) => el("select", { class: "input", "aria-label": label, onchange: (e) => { rankState[key] = e.target.value; refilter(); } },
    opts.map(([val, text]) => el("option", { value: val, text, selected: rankState[key] === val })));
  const q = el("input", { class: "input rk-search", type: "search", value: rankState.q, placeholder: t("searchPh"), "aria-label": t("searchPh"),
    oninput: (e) => { rankState.q = e.target.value; refilter(); } });
  const provinces = ["Koshi", "Madhesh", "Bagmati", "Gandaki", "Lumbini", "Karnali", "Sudurpashchim"];
  const er = el("label", { class: "rk-check" }, el("input", { type: "checkbox", checked: rankState.erOnly,
    onchange: (e) => { rankState.erOnly = e.target.checked; refilter(); } }), t("erOnly"));
  const controls = el("div", { class: "rk-controls" }, q,
    sel("province", t("filterProvince"), [["", t("allProvinces")], ...provinces.map((p) => [p, p])]),
    sel("type", t("filterType"), [["", t("allTypes")], ["government", t("typeGovernment")], ["private", t("typePrivate")], ["community", t("typeCommunity")], ["teaching", t("typeTeaching")]]),
    sel("sort", t("sortBy"), [["rank", t("sortRank")], ["az", t("sortAZ")], ["rating", t("sortRating")], ["specialties", t("sortSpecialties")]]),
    er);

  fill(v, [
    help,
    el("section", { class: "rk-hero" },
      el("p", { class: "rk-eyebrow", text: t("rkEyebrow") }),
      el("h2", { text: t("rkTitle") }),
      el("p", { class: "rk-sub", text: t("rkSub") }),
      el("p", { class: "rk-caveat", text: t("rkCaveatShort") }), stats),
    el("section", { class: "rk-board" }, controls,
      el("p", { class: "rk-count", id: "rkCount", "aria-live": "polite" }),
      el("ol", { class: "rk-cards", id: "rkBody" }, el("li", { class: "empty", text: "…" })),
      el("div", { class: "center", id: "rkMore" })),
    el("section", { class: "rk-method", id: "rkMethod" }),
    el("p", { class: "disclaimer", text: t("disclaimer") }),
    S.cfg.osm_attribution ? el("p", { class: "disclaimer" }, t("osmPre"), el("a", { href: "https://www.openstreetmap.org/copyright", target: "_blank", rel: "noopener" }, "OpenStreetMap", newTab()), t("osmPost")) : null]);
  loadRanking();
}

async function loadRanking() {
  if (!rankState.data || rankState.lang !== S.lang) {
    try { rankState.data = await api("/api/ranking", { params: { lang: S.lang } }); rankState.lang = S.lang; }
    catch (e) {
      if ($("rkBody")) {
        $("rkStats").hidden = true;
        $("rkBody").replaceChildren(el("li", { class: "empty" }, el("p", { text: e.message }),
          el("button", { class: "secondary-btn", type: "button", onclick: () => { $("rkStats").hidden = false; loadRanking(); } }, t("retry"))));
      }
      return;
    }
  }
  if (!$("rkBody")) return;
  const d = rankState.data;
  $("rkStats").replaceChildren(...[[d.stats.hospitals, t("stHospitals")], [d.stats.provinces, t("stProvinces")],
    [d.stats.emergency_24h, t("stEmergency")], [d.indicators.length, t("stIndicators")]].map(([n, label]) =>
    el("div", { class: "rk-stat" }, el("b", { text: n }), el("span", { text: label }))));
  $("rkMethod").replaceChildren(el("h2", { text: t("methodTitle") }), el("p", { text: t("methodIntro") }),
    el("ul", { class: "rk-weights" }, d.indicators.map((i) => el("li", {},
      el("span", { class: "rk-w", text: `${i.weight}%` }), el("div", {}, el("b", { text: t(`ind_${i.key}`) }), el("p", { text: t(`desc_${i.key}`, d.prior_reviews) }))))),
    el("p", { class: "note", text: t("methodCaveat") }));
  renderRanking();
}

function renderRanking() {
  const d = rankState.data;
  if (!d || !$("rkBody")) return;
  const q = rankState.q.trim().toLowerCase();
  let rows = d.hospitals.filter((h) =>
    (!rankState.province || h.province === rankState.province) &&
    (!rankState.type || h.type_group === rankState.type) &&
    (!rankState.erOnly || h.emergency_24h) &&
    (!q || [h.name, h.name_ne, h.city, h.district, h.province].join(" ").toLowerCase().includes(q)));
  // the Bayesian score, so one 5-star review can't jump a hospital to the top of "sort by rating"
  const byRating = (h) => h.scores.rating + (h.rating ? h.rating.count : 0) / 1e6;
  if (rankState.sort === "az") rows = [...rows].sort((a, b) => hName(a).localeCompare(hName(b)));
  else if (rankState.sort === "rating") rows = [...rows].sort((a, b) => byRating(b) - byRating(a) || a.rank - b.rank);
  else if (rankState.sort === "specialties") rows = [...rows].sort((a, b) => b.departments - a.departments || a.rank - b.rank);
  $("rkCount").textContent = t("showing", rows.length, d.hospitals.length);
  $("rkMore").replaceChildren();
  if (!rows.length) { $("rkBody").replaceChildren(el("li", { class: "empty", text: t("noResults") })); return; }
  // Only the hospital name is a link (short, clear name for screen readers); CSS stretches it over the whole card.
  $("rkBody").replaceChildren(...rows.slice(0, rankState.shown).map((h) => el("li", { class: "rk-card" },
    el("div", { class: "rk-card-head" },
      el("span", { class: "rk-rank" }, srOnly(`${t("colRank")} `), el("small", { "aria-hidden": "true", text: "#" }), `${h.tied ? "=" : ""}${h.rank}`),
      el("span", { class: "rk-overall" }, el("b", { text: h.overall.toFixed(1) }), el("small", { text: t("colOverall") }))),
    el("a", { class: "rk-name", href: `#/h/${encodeURIComponent(h.id)}` }, hName(h)),
    el("span", { class: "rk-place" }, svg(ICON.pin), `${h.city}, ${h.province}`),
    el("span", { class: "rk-tags" }, el("span", { class: "chip", text: h.type_label }),
      h.emergency_24h ? el("span", { class: "chip ok", text: t("er24") }) : null,
      h.health_insurance ? el("span", { class: "chip", text: t("insurance") }) : null),
    el("div", { class: "rk-inds" }, ["specialties", "emergency", "insurance", "teaching"].map((k) =>
      el("div", { class: "rk-ind" }, el("span", { class: "rk-ind-label", text: t(`ind_${k}`) }), scoreBar(h.scores[k]))),
      el("div", { class: "rk-ind" }, el("span", { class: "rk-ind-label", text: t("ind_rating") }), ratingValue(h))),
    el("span", { class: "rk-go", "aria-hidden": "true", text: "→" }))));
  const left = rows.length - rankState.shown;
  if (left > 0) {
    $("rkMore").append(el("button", { class: "secondary-btn", type: "button", onclick: () => { rankState.shown += PAGE; renderRanking(); } },
      t("showMore", Math.min(left, PAGE))));
  }
}

// ------------------------------------------------------------------ hospital page
async function viewHospital(id) {
  const v = $("view");
  v.replaceChildren(el("p", { class: "empty", text: "…" }));
  let h;
  try { h = await api(`/api/hospitals/${encodeURIComponent(id)}`, { params: { lang: S.lang, ...(S.place && S.place.lat != null ? { lat: S.place.lat, lng: S.place.lng } : {}) } }); }
  catch (e) {
    v.replaceChildren(el("a", { class: "back", href: "#/" }, svg(ICON.back), t("back")),
      el("div", { class: "empty" }, el("p", { text: e.message }),
        e.status === 404 ? null : el("button", { class: "secondary-btn", type: "button", onclick: () => viewHospital(id) }, t("retry"))));
    return;
  }

  const frame = mapFrame(h.map_embed_url, h.name);
  const segBtn = (label, src, on) => el("button", { type: "button", "aria-pressed": String(on), onclick: (e) => {
    frame.src = src; e.currentTarget.parentNode.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b === e.currentTarget)));
  } }, label);

  const reviewsBox = el("div", { id: "reviewsBox" });
  fill(v, [
    el("a", { class: "back", href: "#/" }, svg(ICON.back), t("back")),
    el("h1", { class: "h-title", text: hName(h) }),
    el("p", { class: "h-sub" }, S.lang === "ne" && h.name_ne ? el("span", {}, h.name, el("br")) : null,
      `${h.city}, ${h.district} · ${h.type_label}${h.distance_km != null ? ` · ${h.distance_km} ${t("km")}` : ""}`),
    el("div", { class: "row-meta" }, ratingLine(h.rating),
      h.emergency_24h ? el("span", { class: "tag", text: t("er24") }) : null,
      h.health_insurance ? el("span", { class: "tag", text: t("insurance") }) : null,
      !h.verified ? el("span", { class: "tag grey", text: t("unverified") }) : null),
    el("div", { class: "actions" },
      el("a", { class: "primary-btn", href: h.directions_url, target: "_blank", rel: "noopener" }, svg(ICON.nav), t("directions"), newTab()),
      h.phone ? el("a", { class: "secondary-btn", href: `tel:${h.phone}` }, t("call"))
        : el("a", { class: "secondary-btn", href: h.google_maps_url, target: "_blank", rel: "noopener" }, t("googleMaps"), newTab())),
    el("p", { class: "note call-first", text: t("callFirst") }),
    el("div", { class: "map-box" }, el("div", { class: "seg" }, segBtn(t("mapRoad"), h.map_embed_url, true), segBtn(t("mapCampus"), h.inside.satellite_embed_url, false)), frame),
    h.department_labels.length ? block(t("departments"), el("div", { class: "chips" }, h.department_labels.map((d) => el("span", { class: "chip", text: d.label })))) : null,
    block(t("billing"), stepsList(h.billing.steps),
      h.billing.insurance_steps.length ? [el("h3", { text: t("withInsurance") }), stepsList(h.billing.insurance_steps)] : null,
      h.billing.hospital_notes ? el("p", { text: h.billing.hospital_notes }) : null,
      el("p", { class: "note", text: h.billing.help }), el("p", { class: "note", text: t("generalNote") })),
    block(t("inside"), h.inside.campus_map_url ? el("img", { class: "campus-map", src: h.inside.campus_map_url, alt: t("campusAlt", hName(h)) }) : null,
      stepsList(h.inside.steps)),
    el("section", { class: "block" }, el("h2", { text: t("reviewsTitle") }), reviewsBox),
  ]);
  renderReviews(h, reviewsBox);
}

async function renderReviews(h, box) {
  const head = h.rating && h.rating.count
    ? el("div", { class: "rating-big" }, el("b", { "aria-hidden": "true", text: h.rating.avg }),
      el("span", { class: "stars", role: "img", "aria-label": t("outOf5", h.rating.avg), text: "★".repeat(Math.round(h.rating.avg)) }),
      el("span", { class: "muted", text: t("reviews", h.rating.count) }))
    : el("p", { class: "muted", text: t("noReviews") });
  const formSlot = el("div");
  const list = h.reviews.map((r) => el("div", { class: "review" },
    el("div", { class: "review-head" }, el("span", { class: "stars", role: "img", "aria-label": t("outOf5", r.rating), text: "★".repeat(r.rating) + "☆".repeat(5 - r.rating) }),
      el("span", { class: "muted", text: `${r.author} · ${new Date(r.updated_at * 1000).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}` })),
    r.comment ? el("p", { text: r.comment }) : null));
  box.replaceChildren(head, formSlot, ...list);

  if (!S.user) {
    formSlot.append(el("button", { class: "secondary-btn wide", type: "button", onclick: () => requireLogin(t("loginWhyReview"), () => viewHospital(h.id)) }, t("loginToReview")));
    return;
  }
  let mine = null;
  try { mine = (await api(`/api/hospitals/${encodeURIComponent(h.id)}/my-review`, { auth: true })).review; } catch { /* ignore */ }
  let rating = mine ? mine.rating : 0;
  // Star picker is a radio group: one tab stop, arrow keys change the rating.
  const pick = (n) => { rating = Math.min(5, Math.max(1, n)); paint(); starBtns[rating - 1].focus(); };
  const starBtns = [1, 2, 3, 4, 5].map((n) => el("button", { type: "button", role: "radio", "aria-label": t("stars", n),
    onclick: () => pick(n),
    onkeydown: (e) => {
      const step = { ArrowRight: 1, ArrowUp: 1, ArrowLeft: -1, ArrowDown: -1 }[e.key];
      if (step) { e.preventDefault(); pick((rating || n) + step); }
    } }, "★"));
  const paint = () => starBtns.forEach((b, i) => {
    b.classList.toggle("on", i < rating); b.setAttribute("aria-checked", String(i + 1 === rating));
    b.tabIndex = i + 1 === (rating || 1) ? 0 : -1;
  });
  paint();
  const ta = el("textarea", { class: "input", id: "reviewText", maxlength: "600", placeholder: t("commentPh") });
  ta.value = mine ? mine.comment : "";
  const form = el("form", { class: "review-form", onsubmit: async (e) => {
    e.preventDefault();
    if (!rating) { toast(t("pickStars")); return; }
    try {
      await api(`/api/hospitals/${encodeURIComponent(h.id)}/reviews`, { method: "POST", auth: true, body: { rating, comment: ta.value } });
      rankState.data = null;  // home cards reload with the new rating
      toast(t("reviewSaved")); viewHospital(h.id);
    } catch (err) { toast(err.message); }
  } },
    el("h3", { class: "field-label", text: mine ? t("editReview") : t("writeReview") }),
    el("div", { class: "star-pick", role: "radiogroup", "aria-label": t("yourRating") }, starBtns),
    el("label", { class: "sr-only", for: "reviewText", text: t("commentPh") }), ta,
    el("p", { class: "note", text: t("reviewNote") }),
    el("div", { class: "row-end" },
      mine ? el("button", { class: "text-btn", type: "button", onclick: async () => {
        if (!confirm(t("confirmDelete"))) return;
        try {
          await api(`/api/hospitals/${encodeURIComponent(h.id)}/reviews/mine`, { method: "DELETE", auth: true });
          rankState.data = null; viewHospital(h.id);
        } catch (err) { toast(err.message); }
      } }, t("deleteReview")) : null,
      el("button", { class: "primary-btn", type: "submit" }, t("postReview"))));
  formSlot.append(form);
}

// ------------------------------------------------------------------ help flow (voice → transcript → report)
let startRecordingSoon = false;
const Rec = { media: null, chunks: [], stream: null, started: 0, tick: null };

function viewHelp() {
  if (!S.user) { location.hash = "#/"; requireLogin(t("loginWhyHelp"), () => { location.hash = "#/help"; }); return; }
  const v = $("view");
  const f = S.flow;
  const placeChip = el("button", { class: `place-chip${S.place ? " set" : ""}`, type: "button", onclick: () => openPlace(() => viewHelp()) },
    svg(ICON.pin), S.place ? `${t("place")}: ${placeLabel()}` : t("choosePlace"));
  const alarm = f.alarm ? alarmBox(f.alarm, f.alarmAnimal) : null;
  const parts = [el("a", { class: "back", href: "#/" }, svg(ICON.back), t("back")), el("div", { class: "center" }, placeChip), alarm];

  if (f.step === "idle" || f.step === "recording") {
    const rec = f.step === "recording";
    parts.push(el("section", { class: "help flat" },
      el("h1", { text: t("helpTitle") }), el("p", { text: rec ? t("tapStop") : t("helpSub") }),
      el("button", { class: `mic${rec ? " rec" : ""}`, type: "button", "aria-label": rec ? t("stopSpeaking") : t("startSpeaking"), onclick: toggleRecording },
        svg(rec ? ICON.stop : ICON.mic)),
      el("div", { class: "mic-label" }, rec ? t("listening") : t("startSpeaking"), " ", el("span", { class: "timer", id: "timer", "aria-hidden": "true" })),
      el("p", { class: "note privacy", text: t("voicePrivacy") }),
      rec ? null : el("button", { class: "text-btn", type: "button", onclick: () => { S.flow = { ...f, step: "confirm", typed: true }; viewHelp(); } }, t("typeInstead"))));
  } else if (f.step === "transcribing") {
    parts.push(el("ul", { class: "progress", "aria-live": "polite" }, el("li", { class: "now", text: t("understanding") })));
  } else if (f.step === "confirm") {
    const ta = el("textarea", { class: "input", id: "transcript", rows: "5", maxlength: "3000", placeholder: t("writeHere"), "aria-label": t("writeHere") });
    ta.value = f.text || "";
    parts.push(el("section", { class: "flow" },
      f.typed ? null : el("p", { class: "field-label", text: t("checkText") }), ta,
      el("button", { class: "primary-btn wide mt", type: "button", onclick: () => {
        const text = ta.value.trim();
        if (text.length < 3) { toast(t("tooShort")); return; }
        makeReport(text);
      } }, t("makeReport")),
      el("div", { class: "center" }, el("button", { class: "text-btn", type: "button", onclick: () => { S.flow = { step: "idle", text: "", alarm: f.alarm }; viewHelp(); } }, t("speakAgain")))));
    setTimeout(() => ta.focus(), 50);
  } else if (f.step === "working") {
    parts.push(el("ul", { class: "progress", id: "progress", "aria-live": "polite" }, t("working").map((s, i) => el("li", { class: i === 0 ? "now" : "", text: s }))),
      el("p", { class: "note center", text: t("mayTake") }));
  }
  fill(v, parts);
  if (startRecordingSoon && f.step === "idle") { startRecordingSoon = false; toggleRecording(); }
}

function alarmBox(flags, animal = false, vetSearchUrl = null) {
  const f = flags[0] || {};
  const label = S.lang === "ne" ? (f.label_ne || f.label || "") : (f.label_en || f.label || "");
  if (animal) {  // animal danger signs: go to a vet (102 is the human ambulance)
    const action = S.lang === "ne" ? (f.action_ne || f.action || "") : (f.action_en || f.action || "");
    return el("div", { class: "alarm", role: "alert" }, el("div", {}, el("strong", { text: t("vetAlarmTitle") }), el("span", { text: label }), action ? el("span", { text: action }) : null),
      vetSearchUrl ? el("a", { href: vetSearchUrl, target: "_blank", rel: "noopener" }, t("findVets"), newTab()) : null);
  }
  return el("div", { class: "alarm", role: "alert" },
    el("div", {}, el("strong", { text: t("emergencyTitle") }), el("span", { text: label })),
    el("a", { href: "tel:102" }, svg(ICON.phone), t("call102")));
}

async function toggleRecording() {
  if (Rec.media && Rec.media.state === "recording") { Rec.media.stop(); return; }
  if (!navigator.mediaDevices || !window.MediaRecorder) { toast(t("micDenied")); S.flow = { step: "confirm", typed: true, text: "" }; viewHelp(); return; }
  try { Rec.stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
  catch { toast(t("micDenied")); S.flow = { step: "confirm", typed: true, text: "" }; viewHelp(); return; }
  const mime = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg"].find((m) => MediaRecorder.isTypeSupported(m)) || "";
  Rec.media = new MediaRecorder(Rec.stream, mime ? { mimeType: mime } : undefined);
  Rec.chunks = [];
  Rec.media.ondataavailable = (e) => e.data.size && Rec.chunks.push(e.data);
  Rec.media.onstop = onRecorded;
  Rec.media.start(); Rec.started = Date.now();
  S.flow = { ...S.flow, step: "recording" }; viewHelp();
  Rec.tick = setInterval(() => {
    const s = Math.floor((Date.now() - Rec.started) / 1000);
    const n = $("timer"); if (n) n.textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
    if (s >= 120 && Rec.media.state === "recording") { toast(t("autoStopped")); Rec.media.stop(); }
  }, 500);
}

async function onRecorded() {
  clearInterval(Rec.tick);
  Rec.stream.getTracks().forEach((tr) => tr.stop());
  const type = Rec.media.mimeType || "audio/webm";
  const blob = new Blob(Rec.chunks, { type });
  if (blob.size < 1500) { toast(t("tooShortVoice")); S.flow = { step: "idle", text: "" }; viewHelp(); return; }
  S.flow = { ...S.flow, step: "transcribing" }; viewHelp();
  try {
    const fd = new FormData();
    fd.append("audio", blob, `voice.${type.includes("mp4") ? "m4a" : type.includes("ogg") ? "ogg" : "webm"}`);
    const r = await api("/api/transcribe", { method: "POST", form: fd, auth: true, timeout: SLOW });
    const hit = r.safety && r.safety.is_emergency;
    S.flow = { step: "confirm", text: r.text, alarm: hit ? r.safety.flags : S.flow.alarm,
      alarmAnimal: hit ? r.safety.subject === "animal" : S.flow.alarmAnimal };
  } catch (e) {
    toast(e.message); S.flow = { step: "confirm", typed: true, text: "", alarm: S.flow.alarm };
  }
  viewHelp();
}

async function makeReport(text) {
  if (!S.place) { S.flow = { ...S.flow, text }; openPlace(() => makeReport(text)); toast(t("placeTitle")); return; }
  S.flow = { ...S.flow, step: "working", text };
  viewHelp();
  const items = () => [...document.querySelectorAll("#progress li")];
  let i = 0;
  const adv = setInterval(() => { const li = items(); if (i < li.length - 1) { li[i].className = "done"; i += 1; li[i].className = "now"; } }, 2500);
  // Nepali words (spoken Nepali is transcribed in Devanagari) get a Nepali report, even if the app is in English.
  const lang = /[\u0900-\u097F]/.test(text) ? "ne" : S.lang;
  try {
    const r = await api("/api/report", { method: "POST", auth: true, body: { text, lang, ...placeParams() }, timeout: SLOW });
    if (r.lang !== S.lang) { S.lang = r.lang; store.set("ss_lang", S.lang); renderHeader(); }  // headings match the report
    clearInterval(adv);
    saveReports({ id: r.id, [r.lang]: r });
    translationFor(r.lang === "ne" ? "en" : "ne").catch(() => {});  // prepare the other language in the background
    S.flow = { step: "idle", text: "" };
    location.hash = "#/report";  // no autoplay: the "Read the report aloud" button is at the top of the report
  } catch (e) {
    clearInterval(adv);
    const hit = e.data && e.data.safety && e.data.safety.is_emergency;
    S.flow = { step: "confirm", text, alarm: hit ? e.data.safety.flags : S.flow.alarm,
      alarmAnimal: hit ? e.data.safety.subject === "animal" : S.flow.alarmAnimal };
    viewHelp(); toast(e.message);
  }
}

// ------------------------------------------------------------------ read aloud
// Gemini voice from the server (natural Nepali on every device). If that fails, the browser's own voice is used.
const SPEECH_OK = "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;
const Voice = { playing: false, loading: false, audio: null, run: 0, cache: {} };  // cache: "<id>:<lang>" -> audio URL

// Browser fallback: Nepali voice first; Hindi voices read Devanagari closely enough when no Nepali voice is installed.
function pickVoice(lang) {
  const voices = speechSynthesis.getVoices();
  for (const prefix of lang === "ne" ? ["ne", "hi"] : ["en"]) {
    const v = voices.find((x) => x.lang.toLowerCase().startsWith(prefix));
    if (v) return v;
  }
  return null;
}

function reportSpeech(r) {
  const top = r.hospitals[0];
  const steps = r.do_now.map((s, i) => `${i + 1}. ${s}`).join(" ");
  if (r.kind === "animal") {
    return [r.urgency_text, r.summary, `${t("doNow")}: ${steps}`, top ? `${t("goToVet")}: ${hName(top)}` : ""].filter(Boolean).join(" ");
  }
  return [r.urgency_text, r.summary, `${t("doNow")}: ${steps}`, `${t("dept")}: ${r.department_label}`, top ? `${t("goTo")}: ${hName(top)}` : ""]
    .filter(Boolean).join(" ");
}

function stopSpeaking() {
  Voice.run += 1;  // cancels audio that is still being prepared
  if (Voice.audio) { Voice.audio.pause(); Voice.audio = null; }
  if (SPEECH_OK) speechSynthesis.cancel();
  Voice.playing = false; Voice.loading = false;
}

function browserSpeak(text, lang) {
  if (!SPEECH_OK || !text) return false;
  const voice = pickVoice(lang);
  const u = new SpeechSynthesisUtterance(text);
  u.lang = voice ? voice.lang : (lang === "ne" ? "ne-NP" : "en-US");
  if (voice) u.voice = voice;
  u.rate = 0.9;
  u.onend = u.onerror = () => { Voice.playing = false; syncListen(); };
  Voice.playing = true;
  speechSynthesis.speak(u);
  return true;
}

function listenButton() {
  const b = el("button", { class: "secondary-btn listen", id: "listenBtn", type: "button", onclick: toggleListen });
  paintListen(b);
  return b;
}

function paintListen(b) {
  if (Voice.loading) b.replaceChildren(el("span", { class: "spinner", "aria-hidden": "true" }), t("preparingAudio"));
  else b.replaceChildren(svg(Voice.playing ? ICON.stop : ICON.speaker), Voice.playing ? t("stopSpeaking") : t("listen"));
}

function syncListen() { const b = $("listenBtn"); if (b) paintListen(b); }

async function toggleListen() {
  if (Voice.playing || Voice.loading) { stopSpeaking(); syncListen(); return; }
  const r = S.report;
  if (!r) return;
  const run = ++Voice.run;
  const key = `${r.id}:${r.lang}`;
  Voice.loading = true; syncListen();
  let url = Voice.cache[key];
  try {
    if (!url) {
      const res = await api("/api/report/speech", { method: "POST", auth: true, body: r, raw: true, timeout: SLOW });
      url = Voice.cache[key] = URL.createObjectURL(await res.blob());
    }
  } catch {
    if (run !== Voice.run) return;
    Voice.loading = false;
    if (!browserSpeak(reportSpeech(r), r.lang)) toast(t("voiceFail"));
    syncListen();
    return;
  }
  if (run !== Voice.run) return;  // stopped, or the page changed, while the audio was being prepared
  const audio = new Audio(url);
  Voice.audio = audio; Voice.loading = false; Voice.playing = true; syncListen();
  audio.onended = audio.onerror = () => { if (Voice.audio === audio) { Voice.audio = null; Voice.playing = false; syncListen(); } };
  try { await audio.play(); }
  catch { if (Voice.audio === audio) { Voice.audio = null; Voice.playing = false; syncListen(); } }  // autoplay blocked: tap Listen
}

// ------------------------------------------------------------------ report
// ------------------------------------------------------------------ report in both languages
// Every report is translated to the other language right after it is made; the header's language button
// shows the report in the chosen language.
const pendingTranslation = {};

function translationFor(lang) {
  const R = S.reports;
  if (!R) return Promise.reject(new Error(t("netError")));
  if (R[lang]) return Promise.resolve(R[lang]);
  const key = `${R.id}:${lang}`;
  if (!pendingTranslation[key]) {
    pendingTranslation[key] = api("/api/report/translate", { method: "POST", auth: true, body: { report: R.ne || R.en, target: lang }, timeout: SLOW })
      .then((tr) => { if (S.reports && S.reports.id === R.id) saveReports({ ...S.reports, [lang]: tr }); return tr; })
      .finally(() => { delete pendingTranslation[key]; });
  }
  return pendingTranslation[key];
}

function reportTools() {
  return el("div", { class: "listen-row" }, listenButton());
}

function reportActions() {
  return [el("div", { class: "sticky-actions" },
    el("button", { class: "primary-btn", type: "button", onclick: downloadPdf }, svg(ICON.down), " ", t("downloadPdf")),
    SHOW_EMAIL ? el("button", { class: "secondary-btn", type: "button", onclick: emailReport }, svg(ICON.mail), " ", t("emailMe")) : null),
  el("div", { class: "center" }, el("a", { class: "text-btn", href: "#/help", onclick: () => { S.flow = { step: "idle", text: "" }; } }, t("newReport")))];
}

function viewAnimalReport(r) {
  const top = r.hospitals[0];
  const parts = [
    el("a", { class: "back", href: "#/" }, svg(ICON.back), t("back")),
    r.urgency === "emergency" && r.safety_flags.length ? alarmBox(r.safety_flags, true, r.vet_search_url) : null,
    el("h1", { class: "r-title", text: r.title }),
    el("div", { class: `r-urgency u-${r.urgency}` }, el("b", { text: r.urgency_text }), r.urgency_reason),
    el("p", { class: "ai-note", text: t("aiNote") }),
    el("p", { text: r.summary }),
    reportTools(),
    block(t("doNow"), stepsList(r.do_now)),
    el("section", { class: "block" }, el("h2", { text: t("goToVet") }),
      top ? el("div", { class: "pick" },
        el("div", { class: "map-box flush" }, mapFrame(top.map_embed_url, top.name)),
        el("div", { class: "pick-body" },
          el("div", { class: "pick-name", text: hName(top) }),
          el("div", { class: "row-sub", text: `${top.city} · ${top.type_label}${top.distance_km != null ? ` · ${top.distance_km} ${t("km")}` : ""}` }),
          !top.verified ? el("div", { class: "row-meta" }, el("span", { class: "tag grey", text: t("unverified") })) : null,
          top.why ? el("p", { text: top.why }) : null,
          el("div", { class: "actions" },
            el("a", { class: "primary-btn", href: top.directions_url, target: "_blank", rel: "noopener" }, svg(ICON.nav), t("directions"), newTab()),
            top.phone ? el("a", { class: "secondary-btn", href: `tel:${top.phone}` }, t("call")) : null),
          el("p", { class: "note call-first", text: t("callFirst") }))) : null,
      r.hospitals.slice(1).map((h) => el("div", { class: "other" },
        el("div", { class: "other-head" }, el("b", { text: hName(h) }), h.distance_km != null ? el("b", { text: `${h.distance_km} ${t("km")}` }) : null),
        h.why ? el("p", { class: "tight", text: h.why }) : null,
        el("a", { href: h.directions_url, target: "_blank", rel: "noopener" }, t("directions"), newTab()))),
      r.district_office ? el("div", { class: "dept-box mt" }, el("b", { text: t("vetOffice") }), el("p", { text: r.district_office.name }),
        el("a", { href: r.district_office.search_url, target: "_blank", rel: "noopener" }, t("googleMaps"), newTab())) : null,
      el("a", { class: "secondary-btn wide mt", href: r.vet_search_url, target: "_blank", rel: "noopener" }, svg(ICON.pin), t("findVets"), newTab())),
  ];
  if (r.travel_tip) parts.push(el("p", { class: "tip", text: r.travel_tip }));
  parts.push(block(t("careAtHome"), plainList(r.care_at_home)));
  if (r.food_tips.length) parts.push(block(t("foodTips"), plainList(r.food_tips)));
  parts.push(block(t("tellVet"), plainList(r.tell_the_vet)), block(t("vetWarning"), plainList(r.warning_signs)));
  parts.push(block(t("youSaid"), el("blockquote", { class: "said", text: r.transcript })));
  parts.push(el("p", { class: "disclaimer", text: r.disclaimer }), reportActions());
  fill($("view"), parts);
}

function viewReport() {
  const R = S.reports;
  if (!R || !(R.ne || R.en)) { location.hash = "#/help"; return; }
  const r = R[S.lang];
  if (!r) {  // translation still on its way
    fill($("view"), [el("a", { class: "back", href: "#/" }, svg(ICON.back), t("back")),
      el("ul", { class: "progress" }, el("li", { class: "now", text: t("translating") }))]);
    translationFor(S.lang)
      .then(() => { if ((location.hash || "").startsWith("#/report")) viewReport(); })
      .catch((e) => {  // show the original language rather than nothing
        toast(e.message);
        const orig = R.ne || R.en;
        S.lang = orig.lang; store.set("ss_lang", S.lang); renderHeader(); viewReport();
      });
    return;
  }
  S.report = r;
  if (r.kind === "animal") { viewAnimalReport(r); return; }
  viewPersonReport(r);
}

function viewPersonReport(r) {
  const top = r.hospitals[0];
  const v = $("view");
  const parts = [
    el("a", { class: "back", href: "#/" }, svg(ICON.back), t("back")),
    r.urgency === "emergency" ? alarmBox(r.safety_flags.length ? r.safety_flags : [{ label: r.urgency_text }]) : null,
    el("h1", { class: "r-title", text: r.title }),
    el("div", { class: `r-urgency u-${r.urgency}` }, el("b", { text: r.urgency_text }), r.urgency_reason),
    el("p", { class: "ai-note", text: t("aiNote") }),
    el("p", { text: r.summary }),
    reportTools(),
    block(t("doNow"), stepsList(r.do_now)),
    el("section", { class: "block" }, el("h2", { text: t("dept") }),
      el("div", { class: "dept-box" }, el("b", { text: r.department_label }), el("p", { text: r.department_reason || r.department_about }))),
  ];
  if (top) {
    parts.push(el("section", { class: "block" }, el("h2", { text: t("goTo") }),
      el("div", { class: "pick" },
        el("div", { class: "map-box flush" }, mapFrame(top.map_embed_url, top.name)),
        el("div", { class: "pick-body" },
          el("div", { class: "pick-name", text: hName(top) }),
          el("div", { class: "row-sub", text: `${top.city}, ${top.district} · ${top.type_label}${top.distance_km != null ? ` · ${top.distance_km} ${t("km")}` : ""}` }),
          el("div", { class: "row-meta" }, ratingLine(top.rating), top.emergency_24h ? el("span", { class: "tag", text: t("er24") }) : null,
            top.health_insurance ? el("span", { class: "tag", text: t("insurance") }) : null,
            !top.verified ? el("span", { class: "tag grey", text: t("unverified") }) : null),
          top.why ? el("p", { text: top.why }) : null,
          el("div", { class: "actions" },
            el("a", { class: "primary-btn", href: top.directions_url, target: "_blank", rel: "noopener" }, svg(ICON.nav), t("directions"), newTab()),
            top.phone ? el("a", { class: "secondary-btn", href: `tel:${top.phone}` }, t("call"))
              : el("a", { class: "secondary-btn", href: `#/h/${encodeURIComponent(top.id)}` }, t("hospitalPage"))),
          el("p", { class: "note call-first", text: t("callFirst") }),
          top.phone ? el("a", { class: "text-btn", href: `#/h/${encodeURIComponent(top.id)}` }, t("hospitalPage")) : null))));
    parts.push(block(t("inside"), top.inside.specific ? el("p", { text: top.inside.specific }) : null, stepsList(top.inside.steps)));
    parts.push(block(t("billing"), stepsList(top.billing.steps),
      top.billing.insurance_steps.length ? [el("h3", { text: t("withInsurance") }), stepsList(top.billing.insurance_steps)] : null,
      el("p", { class: "note", text: top.billing.help }), el("p", { class: "note", text: t("generalNote") })));
  }
  if (r.hospitals.length > 1) {
    parts.push(block(t("otherOptions"), r.hospitals.slice(1).map((h) => el("div", { class: "other" },
      el("div", { class: "other-head" }, el("a", { href: `#/h/${encodeURIComponent(h.id)}`, class: "row-name", text: hName(h) }),
        h.distance_km != null ? el("b", { text: `${h.distance_km} ${t("km")}` }) : null),
      h.why ? el("p", { class: "tight", text: h.why }) : null,
      el("a", { href: h.directions_url, target: "_blank", rel: "noopener" }, t("directions"), newTab())))));
  }
  if (r.travel_tip) parts.push(el("p", { class: "tip", text: r.travel_tip }));
  parts.push(block(t("bring"), plainList(r.what_to_bring)), block(t("ask"), plainList(r.questions_for_doctor)), block(t("warning"), plainList(r.warning_signs)));
  if (r.schemes && r.schemes.length) parts.push(block(t("schemes"), r.schemes.map((s) => el("p", {}, el("b", { text: `${s.name}. ` }), s.summary, el("br"), el("span", { class: "note", text: s.how })))));
  parts.push(block(t("youSaid"), el("blockquote", { class: "said", text: r.transcript })));
  parts.push(el("p", { class: "disclaimer", text: r.disclaimer }));
  parts.push(reportActions());
  fill(v, parts);
}

async function downloadPdf() {
  toast(t("downloading"));
  try {
    const res = await api("/api/report/pdf", { method: "POST", auth: true, body: S.report, raw: true, timeout: SLOW });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = el("a", { href: url, download: `hospital-guide-${S.report.generated_at.slice(0, 10)}.pdf` });
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
  } catch (e) { toast(e.message); }
}

async function emailReport() {
  if (!S.cfg.email_enabled) { toast(t("emailOff")); return; }
  if (!S.user.email) { saveEmail.then = emailReport; openAccount(t("addEmailFirst")); return; }
  toast(t("emailing"));
  try {
    const r = await api("/api/report/email", { method: "POST", auth: true, body: S.report, timeout: SLOW });
    toast(r.delivered ? t("emailSent", r.sent_to) : t("emailSavedOnly"));
  } catch (e) { toast(e.message); }
}

// ------------------------------------------------------------------ router
function route() {
  const hash = location.hash || "#/";
  const m = hash.match(/^#\/h\/(.+)$/);
  stopSpeaking(); // leaving or re-rendering a page stops the spoken report
  window.scrollTo(0, 0);
  const home = !m && !hash.startsWith("#/help") && !hash.startsWith("#/report");
  $("view").classList.toggle("wide", home);
  if (m) viewHospital(decodeURIComponent(m[1]));
  else if (hash.startsWith("#/help")) viewHelp();
  else if (hash.startsWith("#/report")) { if (!S.user) { toast(t("loginNeededReport")); location.hash = "#/"; return; } viewReport(); }
  else viewHome();
  // screen readers and keyboards start at the new page, not wherever focus was on the old one
  if (!document.querySelector("dialog[open]")) $("view").focus({ preventScroll: true });
}

// ------------------------------------------------------------------ start
async function start() {
  renderHeader();
  try { S.cfg = await api("/api/config"); }
  catch (e) {
    $("view").replaceChildren(el("div", { class: "empty" }, el("p", { text: e.message }),
      el("button", { class: "secondary-btn", type: "button", onclick: () => location.reload() }, t("retry"))));
    return;
  }
  try { await initAuth(); } catch { /* Firebase not reachable: app still works without login */ }
  renderHeader();

  $("langBtn").addEventListener("click", () => { S.lang = S.lang === "ne" ? "en" : "ne"; store.set("ss_lang", S.lang); renderHeader(); route(); });
  $("loginBtn").addEventListener("click", () => openLogin());
  $("avatarBtn").addEventListener("click", () => openAccount());
  $("accountSave").addEventListener("click", saveEmail);
  $("accountEmail").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); saveEmail(); } });
  $("accountSheet").addEventListener("close", () => { saveEmail.then = null; });
  $("logoutBtn").addEventListener("click", logout);
  $("googleBtn").addEventListener("click", googleLogin);
  $("devGo").addEventListener("click", devLogin);
  $("devName").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); $("devEmail").focus(); } });
  $("devEmail").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); devLogin(); } });
  $("loginSheet").addEventListener("close", () => { if (!S.user) afterLogin = null; });
  $("gpsBtn").addEventListener("click", async () => {
    try { setPlace(await getGps()); $("placeSheet").close(); } catch { toast(t("gpsFail")); }
  });
  $("placeSave").addEventListener("click", () => { const d = $("districtSel").value; if (d) setPlace({ district: d }); $("placeSheet").close(); });
  $("placeSheet").addEventListener("close", () => { openPlace.done = null; });
  for (const id of ["loginSheet", "accountSheet", "placeSheet"]) {
    $(id).addEventListener("close", () => { const o = $(id).opener; if (o && o.isConnected) o.focus(); });
  }
  window.addEventListener("hashchange", route);
  route();
}
start();
