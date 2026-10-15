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
  share: "M18 16a3 3 0 0 0-2.4 1.2l-6.7-3.4a3 3 0 0 0 0-1.6l6.7-3.4A3 3 0 1 0 15 7l-6.7 3.4a3 3 0 1 0 0 3.2L15 17a3 3 0 1 0 3-1z",
};

function fill(node, parts) { node.replaceChildren(...parts.flat(Infinity).filter((x) => x != null && x !== false)); }

function toast(msg) {
  const n = $("toast"); n.textContent = msg; n.hidden = false;
  clearTimeout(toast.t); toast.t = setTimeout(() => (n.hidden = true), 2600);
}

// ------------------------------------------------------------------ state
const S = {
  cfg: null,
  lang: store.get("ss_lang") || "ne",
  user: null,            // {name}
  getToken: async () => null,
  place: loadPlace(),    // {district} or {lat,lng}
  report: loadReport(),
  flow: { step: "idle", text: "", alarm: null },
};
const t = (k, ...a) => { const v = (window.I18N[S.lang] || window.I18N.ne)[k]; return typeof v === "function" ? v(...a) : v; };
const deptLabel = (d) => (S.cfg && S.cfg.departments[d] ? S.cfg.departments[d][S.lang] : d);
const hName = (h) => (S.lang === "ne" && h.name_ne ? h.name_ne : h.name);

function loadPlace() {
  try { return JSON.parse(store.get("ss_place_gps", true) || "null") || (store.get("ss_district") ? { district: store.get("ss_district") } : null); }
  catch { return null; }
}
function loadReport() { try { return JSON.parse(store.get("ss_report", true) || "null"); } catch { return null; } }
function placeParams() {
  if (!S.place) return {};
  return S.place.lat != null ? { lat: S.place.lat, lng: S.place.lng } : { district: S.place.district };
}
function placeLabel() {
  if (!S.place) return t("choosePlace");
  return S.place.lat != null ? t("myLocation") : S.place.district;
}

// ------------------------------------------------------------------ api
async function api(path, { method = "GET", body, form, params, auth = false, raw = false } = {}) {
  const url = new URL(path, location.origin);
  for (const [k, v] of Object.entries(params || {})) if (v != null && v !== "") url.searchParams.set(k, v);
  const headers = {};
  if (auth) { const tok = await S.getToken(); if (tok) headers.Authorization = `Bearer ${tok}`; }
  let payload;
  if (form) payload = form;
  else if (body !== undefined) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
  const res = await fetch(url, { method, headers, body: payload });
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
      authMod.onAuthStateChanged(auth, (u) => {
        S.user = u ? { name: u.displayName || (u.email || "").split("@")[0] } : null;
        renderHeader(); resolve();
        if (u && afterLogin) { const f = afterLogin; afterLogin = null; f(); }
      });
    });
    authMod.getRedirectResult(auth).catch(() => {});
  } else {
    const name = store.get("ss_dev_name");
    S.user = name ? { name } : null;
    S.getToken = async () => (S.user ? `dev:${S.user.name}` : null);
  }
}

function openLogin(reason) {
  $("loginTitle").textContent = t("loginTitle");
  $("loginWhy").textContent = reason || t("loginWhy");
  $("loginError").hidden = true;
  const fb = S.cfg.auth_mode === "firebase";
  $("googleBtn").hidden = !fb; $("devLogin").hidden = fb;
  $("googleLabel").textContent = t("google");
  $("devNameLabel").textContent = t("devName"); $("devGo").textContent = t("devGo"); $("devNote").textContent = t("devNote");
  $("loginCancel").textContent = t("cancel");
  $("loginSheet").showModal();
  if (!fb) $("devName").focus();
}

function requireLogin(reason, then) {
  if (S.user) { then(); return; }
  afterLogin = then; openLogin(reason);
}

async function googleLogin() {
  const { auth, GoogleAuthProvider, signInWithPopup, signInWithRedirect } = firebaseAuth;
  const provider = new GoogleAuthProvider();
  try { await signInWithPopup(auth, provider); $("loginSheet").close(); }
  catch (e) {
    if (e && (e.code === "auth/popup-blocked" || e.code === "auth/operation-not-supported-in-this-environment")) {
      await signInWithRedirect(auth, provider);
    } else if (!(e && e.code === "auth/popup-closed-by-user")) {
      $("loginError").textContent = t("loginFailed"); $("loginError").hidden = false;
    }
  }
}

function devLogin() {
  const name = $("devName").value.trim();
  if (!name) { $("devName").focus(); return; }
  store.set("ss_dev_name", name);
  S.user = { name };
  $("loginSheet").close(); renderHeader();
  if (afterLogin) { const f = afterLogin; afterLogin = null; f(); }
}

async function logout() {
  if (firebaseAuth) await firebaseAuth.signOut(firebaseAuth.auth);
  store.set("ss_dev_name", null);
  S.user = null; S.report = null; store.set("ss_report", null, true);
  $("accountSheet").close(); renderHeader(); route();
}

function renderHeader() {
  document.documentElement.lang = S.lang;
  $("brandName").textContent = t("brand");
  $("langBtn").textContent = t("other");
  $("loginBtn").textContent = t("login");
  $("loginBtn").hidden = Boolean(S.user);
  $("avatarBtn").hidden = !S.user;
  if (S.user) { $("avatarBtn").textContent = (S.user.name || "?").trim().charAt(0).toUpperCase(); $("avatarBtn").setAttribute("aria-label", S.user.name); }
}

// ------------------------------------------------------------------ place
function openPlace(onDone) {
  $("placeTitle").textContent = t("placeTitle"); $("gpsBtn").textContent = t("useGps");
  $("districtLabel").textContent = t("orDistrict"); $("placeCancel").textContent = t("cancel"); $("placeSave").textContent = t("save");
  const sel = $("districtSel"); sel.replaceChildren(el("option", { value: "", text: "—" }));
  for (const d of S.cfg.districts) sel.append(el("option", { value: d, text: d, selected: S.place && S.place.district === d }));
  openPlace.done = onDone; $("placeSheet").showModal();
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
function ratingLine(r) {
  return r && r.count ? el("span", { class: "stars" }, `★ ${r.avg}`, el("span", { class: "muted", text: ` (${t("reviews", r.count)})` }))
    : el("span", { class: "muted", text: t("noReviews") });
}
function mapFrame(src, title) {
  return el("iframe", { src, title, loading: "lazy", referrerpolicy: "no-referrer-when-downgrade", allowfullscreen: true });
}
function stepsList(items) { return el("ol", { class: "steps" }, items.map((s) => el("li", { text: s }))); }
function plainList(items) { return el("ul", { class: "plain" }, items.map((s) => el("li", { text: s }))); }
function block(title, ...content) { return el("section", { class: "block" }, el("h2", { text: title }), ...content); }

// ------------------------------------------------------------------ home
let dirState = { q: "", district: "", seq: 0 };

function viewHome() {
  const v = $("view");
  const mic = el("button", { class: "mic", type: "button", "aria-label": t("startSpeaking"),
    onclick: () => requireLogin(t("loginWhyHelp"), () => { location.hash = "#/help"; startRecordingSoon = true; }) }, svg(ICON.mic));
  const help = el("section", { class: "help" },
    el("h1", { text: t("helpTitle") }), el("p", { text: t("helpSub") }), mic,
    el("div", { class: "mic-label", text: t("startSpeaking") }));

  const q = el("input", { class: "input", type: "search", value: dirState.q, placeholder: t("searchPh"), "aria-label": t("searchPh"),
    oninput: (e) => { dirState.q = e.target.value; clearTimeout(viewHome.tm); viewHome.tm = setTimeout(loadList, 250); } });
  const gpsOn = Boolean(S.place && S.place.lat != null);
  const near = el("button", { class: `near-btn${gpsOn ? " on" : ""}`, type: "button", "aria-pressed": String(gpsOn),
    onclick: async () => {
      try { setPlace(await getGps()); near.classList.add("on"); near.setAttribute("aria-pressed", "true"); loadList(); }
      catch { toast(t("gpsFail")); }
    } }, svg(ICON.pin), t("nearMe"));
  const dsel = el("select", { class: "input", "aria-label": t("allDistricts"),
    onchange: (e) => { dirState.district = e.target.value; loadList(); } },
    el("option", { value: "", text: t("allDistricts") }),
    S.cfg.districts.map((d) => el("option", { value: d, text: d, selected: d === dirState.district })));
  const count = el("span", { class: "count", id: "dirCount" });
  const list = el("ul", { class: "cards", id: "dirList", "aria-live": "polite" });
  fill(v, [help, el("section", { class: "dir" }, q,
    el("div", { class: "filters" }, near, dsel, count), list), el("p", { class: "disclaimer", text: t("disclaimer") }),
    S.cfg.osm_attribution ? el("p", { class: "disclaimer" }, "Hospital data includes © ", el("a", { href: "https://www.openstreetmap.org/copyright", target: "_blank", rel: "noopener" }, "OpenStreetMap"), " contributors") : null]);
  loadList();
}

async function loadList() {
  const seq = ++dirState.seq;
  const params = { q: dirState.q, district: dirState.district, lang: S.lang };
  if (S.place && S.place.lat != null) Object.assign(params, { lat: S.place.lat, lng: S.place.lng });
  else if (S.place && S.place.district) params.near = S.place.district;
  let data;
  try { data = await api("/api/hospitals", { params }); } catch (e) { if (seq === dirState.seq) $("dirList").replaceChildren(el("li", { class: "empty", text: e.message })); return; }
  if (seq !== dirState.seq || !$("dirList")) return;
  $("dirCount").textContent = t("hospitalsCount", data.count);
  if (!data.count) { $("dirList").replaceChildren(el("li", { class: "empty", text: t("noResults") })); return; }
  $("dirList").replaceChildren(...data.hospitals.map((h) => el("li", { class: "card" },
    el("a", { class: "card-link", href: `#/h/${encodeURIComponent(h.id)}` },
      el("span", { class: "card-head" },
        el("span", { class: "row-name", text: hName(h) }),
        h.distance_km != null ? el("span", { class: "card-km", text: `${h.distance_km} ${t("km")}` }) : null),
      el("span", { class: "card-place" }, svg(ICON.pin), `${h.city}, ${h.district}`),
      el("span", { class: "card-tags" },
        el("span", { class: "chip", text: h.type_label }),
        h.emergency_24h ? el("span", { class: "chip ok", text: t("er24") }) : null,
        h.health_insurance ? el("span", { class: "chip ok", text: t("insurance") }) : null),
      el("span", { class: "card-foot" }, ratingLine(h.rating), el("span", { class: "card-go", "aria-hidden": "true", text: "→" }))))));
}

// ------------------------------------------------------------------ hospital page
async function viewHospital(id) {
  const v = $("view");
  v.replaceChildren(el("p", { class: "empty", text: "…" }));
  let h;
  try { h = await api(`/api/hospitals/${encodeURIComponent(id)}`, { params: { lang: S.lang, ...(S.place && S.place.lat != null ? { lat: S.place.lat, lng: S.place.lng } : {}) } }); }
  catch (e) { v.replaceChildren(el("a", { class: "back", href: "#/" }, svg(ICON.back), t("back")), el("p", { class: "empty", text: e.message })); return; }

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
      el("a", { class: "primary-btn", href: h.directions_url, target: "_blank", rel: "noopener" }, svg(ICON.nav), t("directions")),
      h.phone ? el("a", { class: "secondary-btn", href: `tel:${h.phone}` }, t("call"))
        : el("a", { class: "secondary-btn", href: h.google_maps_url, target: "_blank", rel: "noopener" }, t("googleMaps"))),
    el("div", { class: "map-box" }, el("div", { class: "seg" }, segBtn(t("mapRoad"), h.map_embed_url, true), segBtn(t("mapCampus"), h.inside.satellite_embed_url, false)), frame),
    h.department_labels.length ? block(t("departments"), el("div", { class: "chips" }, h.department_labels.map((d) => el("span", { class: "chip", text: d.label })))) : null,
    block(t("billing"), stepsList(h.billing.steps),
      h.billing.insurance_steps.length ? [el("h3", { text: t("withInsurance") }), stepsList(h.billing.insurance_steps)] : null,
      h.billing.hospital_notes ? el("p", { text: h.billing.hospital_notes }) : null,
      el("p", { class: "note", text: h.billing.help }), el("p", { class: "note", text: t("generalNote") })),
    block(t("inside"), h.inside.campus_map_url ? el("img", { src: h.inside.campus_map_url, alt: t("inside"), style: "max-width:100%;border-radius:12px" }) : null,
      stepsList(h.inside.steps)),
    el("section", { class: "block" }, el("h2", { text: t("reviewsTitle") }), reviewsBox),
  ]);
  renderReviews(h, reviewsBox);
}

async function renderReviews(h, box) {
  const head = h.rating && h.rating.count
    ? el("div", { class: "rating-big" }, el("b", { text: h.rating.avg }), el("span", { class: "stars", text: "★".repeat(Math.round(h.rating.avg)) }), el("span", { class: "muted", text: t("reviews", h.rating.count) }))
    : el("p", { class: "muted", text: t("noReviews") });
  const formSlot = el("div");
  const list = h.reviews.map((r) => el("div", { class: "review" },
    el("div", { class: "review-head" }, el("span", { class: "stars", text: "★".repeat(r.rating) + "☆".repeat(5 - r.rating), "aria-label": t("stars", r.rating) }),
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
  const starBtns = [1, 2, 3, 4, 5].map((n) => el("button", { type: "button", "aria-label": t("stars", n), "aria-pressed": "false",
    onclick: () => { rating = n; paint(); } }, "★"));
  const paint = () => starBtns.forEach((b, i) => { b.classList.toggle("on", i < rating); b.setAttribute("aria-pressed", String(i + 1 === rating)); });
  paint();
  const ta = el("textarea", { class: "input", maxlength: "600", placeholder: t("commentPh"), "aria-label": t("commentPh") });
  ta.value = mine ? mine.comment : "";
  const form = el("form", { class: "review-form", onsubmit: async (e) => {
    e.preventDefault();
    if (!rating) { toast(t("pickStars")); return; }
    try {
      await api(`/api/hospitals/${encodeURIComponent(h.id)}/reviews`, { method: "POST", auth: true, body: { rating, comment: ta.value } });
      toast(t("reviewSaved")); viewHospital(h.id);
    } catch (err) { toast(err.message); }
  } },
    el("div", { class: "field-label", text: mine ? t("editReview") : t("writeReview") }),
    el("div", { class: "star-pick", role: "group", "aria-label": t("yourRating") }, starBtns), ta,
    el("p", { class: "note", text: t("reviewNote") }),
    el("div", { class: "row-end" },
      mine ? el("button", { class: "text-btn", type: "button", onclick: async () => {
        await api(`/api/hospitals/${encodeURIComponent(h.id)}/reviews/mine`, { method: "DELETE", auth: true }); viewHospital(h.id);
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
  const alarm = f.alarm ? alarmBox(f.alarm) : null;
  const parts = [el("a", { class: "back", href: "#/" }, svg(ICON.back), t("back")), el("div", { class: "center" }, placeChip), alarm];

  if (f.step === "idle" || f.step === "recording") {
    const rec = f.step === "recording";
    parts.push(el("section", { class: "help", style: "border:none" },
      el("h1", { text: t("helpTitle") }), el("p", { text: rec ? t("tapStop") : t("helpSub") }),
      el("button", { class: `mic${rec ? " rec" : ""}`, type: "button", "aria-label": rec ? t("stopSpeaking") : t("startSpeaking"), onclick: toggleRecording },
        svg(rec ? ICON.stop : ICON.mic)),
      el("div", { class: "mic-label" }, rec ? t("listening") : t("startSpeaking"), " ", el("span", { class: "timer", id: "timer" })),
      rec ? null : el("button", { class: "text-btn", type: "button", onclick: () => { S.flow = { ...f, step: "confirm", typed: true }; viewHelp(); } }, t("typeInstead"))));
  } else if (f.step === "transcribing") {
    parts.push(el("ul", { class: "progress" }, el("li", { class: "now", text: t("understanding") })));
  } else if (f.step === "confirm") {
    const ta = el("textarea", { class: "input", id: "transcript", rows: "5", maxlength: "3000", placeholder: t("writeHere"), "aria-label": t("writeHere") });
    ta.value = f.text || "";
    parts.push(el("section", { class: "flow" },
      f.typed ? null : el("p", { class: "field-label", text: t("checkText") }), ta,
      el("button", { class: "primary-btn wide", type: "button", style: "margin-top:12px", onclick: () => {
        const text = ta.value.trim();
        if (text.length < 3) { toast(t("tooShort")); return; }
        makeReport(text);
      } }, t("makeReport")),
      el("div", { class: "center" }, el("button", { class: "text-btn", type: "button", onclick: () => { S.flow = { step: "idle", text: "", alarm: f.alarm }; viewHelp(); } }, t("speakAgain")))));
    setTimeout(() => ta.focus(), 50);
  } else if (f.step === "working") {
    parts.push(el("ul", { class: "progress", id: "progress" }, t("working").map((s, i) => el("li", { class: i === 0 ? "now" : "", text: s }))));
  }
  fill(v, parts);
  if (startRecordingSoon && f.step === "idle") { startRecordingSoon = false; toggleRecording(); }
}

function alarmBox(flags) {
  const f = flags[0] || {};
  return el("div", { class: "alarm", role: "alert" },
    el("div", {}, el("strong", { text: t("emergencyTitle") }), el("span", { text: S.lang === "ne" ? (f.label_ne || f.label || "") : (f.label_en || f.label || "") })),
    el("a", { href: "tel:102" }, t("call102")));
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
    if (s >= 120 && Rec.media.state === "recording") Rec.media.stop();
  }, 500);
}

async function onRecorded() {
  clearInterval(Rec.tick);
  Rec.stream.getTracks().forEach((tr) => tr.stop());
  const type = Rec.media.mimeType || "audio/webm";
  const blob = new Blob(Rec.chunks, { type });
  if (blob.size < 1500) { S.flow = { step: "idle", text: "" }; viewHelp(); return; }
  S.flow = { ...S.flow, step: "transcribing" }; viewHelp();
  try {
    const fd = new FormData();
    fd.append("audio", blob, `voice.${type.includes("mp4") ? "m4a" : type.includes("ogg") ? "ogg" : "webm"}`);
    const r = await api("/api/transcribe", { method: "POST", form: fd, auth: true });
    S.flow = { step: "confirm", text: r.text, alarm: r.safety && r.safety.is_emergency ? r.safety.flags : S.flow.alarm };
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
  try {
    const r = await api("/api/report", { method: "POST", auth: true, body: { text, lang: S.lang, ...placeParams() } });
    clearInterval(adv);
    S.report = r; store.set("ss_report", JSON.stringify(r), true);
    S.flow = { step: "idle", text: "" };
    location.hash = "#/report";
  } catch (e) {
    clearInterval(adv);
    const alarm = e.data && e.data.safety && e.data.safety.is_emergency ? e.data.safety.flags : S.flow.alarm;
    S.flow = { step: "confirm", text, alarm };
    viewHelp(); toast(e.message);
  }
}

// ------------------------------------------------------------------ report
function viewReport() {
  const r = S.report;
  if (!r) { location.hash = "#/help"; return; }
  const top = r.hospitals[0];
  const v = $("view");
  const parts = [
    el("a", { class: "back", href: "#/" }, svg(ICON.back), t("back")),
    r.urgency === "emergency" ? alarmBox(r.safety_flags.length ? r.safety_flags : [{ label: r.urgency_text }]) : null,
    el("h1", { class: "r-title", text: r.title }),
    el("div", { class: `r-urgency u-${r.urgency}` }, el("b", { text: r.urgency_text }), r.urgency_reason),
    el("p", { text: r.summary }),
    block(t("doNow"), stepsList(r.do_now)),
    el("section", { class: "block" }, el("h2", { text: t("dept") }),
      el("div", { class: "dept-box" }, el("b", { text: r.department_label }), el("p", { text: r.department_reason || r.department_about }))),
  ];
  if (top) {
    parts.push(el("section", { class: "block" }, el("h2", { text: t("goTo") }),
      el("div", { class: "pick" },
        el("div", { class: "map-box", style: "border:none;border-radius:0" }, mapFrame(top.map_embed_url, top.name)),
        el("div", { class: "pick-body" },
          el("div", { class: "pick-name", text: hName(top) }),
          el("div", { class: "row-sub", text: `${top.city}, ${top.district} · ${top.type_label}${top.distance_km != null ? ` · ${top.distance_km} ${t("km")}` : ""}` }),
          el("div", { class: "row-meta" }, ratingLine(top.rating), top.emergency_24h ? el("span", { class: "tag", text: t("er24") }) : null,
            top.health_insurance ? el("span", { class: "tag", text: t("insurance") }) : null),
          top.why ? el("p", { text: top.why }) : null,
          el("div", { class: "actions" },
            el("a", { class: "primary-btn", href: top.directions_url, target: "_blank", rel: "noopener" }, svg(ICON.nav), t("directions")),
            el("a", { class: "secondary-btn", href: `#/h/${encodeURIComponent(top.id)}` }, t("hospitalPage")))))));
    parts.push(block(t("inside"), top.inside.specific ? el("p", { text: top.inside.specific }) : null, stepsList(top.inside.steps)));
    parts.push(block(t("billing"), stepsList(top.billing.steps),
      top.billing.insurance_steps.length ? [el("h3", { text: t("withInsurance") }), stepsList(top.billing.insurance_steps)] : null,
      el("p", { class: "note", text: top.billing.help }), el("p", { class: "note", text: t("generalNote") })));
  }
  if (r.hospitals.length > 1) {
    parts.push(block(t("otherOptions"), r.hospitals.slice(1).map((h) => el("div", { class: "other" },
      el("div", { class: "other-head" }, el("a", { href: `#/h/${encodeURIComponent(h.id)}`, class: "row-name", text: hName(h) }),
        h.distance_km != null ? el("b", { text: `${h.distance_km} ${t("km")}` }) : null),
      h.why ? el("p", { style: "margin:2px 0", text: h.why }) : null,
      el("a", { href: h.directions_url, target: "_blank", rel: "noopener" }, t("directions"))))));
  }
  if (r.travel_tip) parts.push(el("p", { class: "note", style: "font-size:17px;color:var(--ink)", text: r.travel_tip }));
  parts.push(block(t("bring"), plainList(r.what_to_bring)), block(t("ask"), plainList(r.questions_for_doctor)), block(t("warning"), plainList(r.warning_signs)));
  if (r.schemes && r.schemes.length) parts.push(block(t("schemes"), r.schemes.map((s) => el("p", {}, el("b", { text: `${s.name}. ` }), s.summary, el("br"), el("span", { class: "note", text: s.how })))));
  parts.push(block(t("youSaid"), el("blockquote", { class: "said", text: r.transcript })));
  parts.push(el("p", { class: "disclaimer", text: r.disclaimer }));
  parts.push(el("div", { class: "sticky-actions" },
    el("button", { class: "primary-btn", type: "button", onclick: downloadPdf }, svg(ICON.down), " ", t("downloadPdf")),
    el("button", { class: "secondary-btn", type: "button", onclick: shareReport }, t("share"))));
  parts.push(el("div", { class: "center" }, el("a", { class: "text-btn", href: "#/help", onclick: () => { S.flow = { step: "idle", text: "" }; } }, t("newReport"))));
  fill(v, parts);
}

async function downloadPdf() {
  toast(t("downloading"));
  try {
    const res = await api("/api/report/pdf", { method: "POST", auth: true, body: S.report, raw: true });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = el("a", { href: url, download: `hospital-guide-${S.report.generated_at.slice(0, 10)}.pdf` });
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
  } catch (e) { toast(e.message); }
}

async function shareReport() {
  const r = S.report; const h = r.hospitals[0];
  const text = [r.title, r.urgency_text, `${t("dept")}: ${r.department_label}`, h ? `${t("goTo")}: ${hName(h)} — ${h.directions_url}` : "", r.disclaimer].filter(Boolean).join("\n");
  if (navigator.share) { try { await navigator.share({ title: r.title, text }); return; } catch { /* cancelled */ } }
  try { await navigator.clipboard.writeText(text); toast("✓"); } catch { toast(text.slice(0, 120)); }
}

// ------------------------------------------------------------------ router
function route() {
  const hash = location.hash || "#/";
  const m = hash.match(/^#\/h\/(.+)$/);
  window.scrollTo(0, 0);
  if (m) viewHospital(decodeURIComponent(m[1]));
  else if (hash.startsWith("#/help")) viewHelp();
  else if (hash.startsWith("#/report")) { if (!S.user) { location.hash = "#/"; return; } viewReport(); }
  else viewHome();
}

// ------------------------------------------------------------------ start
async function start() {
  renderHeader();
  try { S.cfg = await api("/api/config"); }
  catch { $("view").replaceChildren(el("p", { class: "empty", text: t("netError") })); return; }
  try { await initAuth(); } catch { /* Firebase not reachable: app still works without login */ }
  renderHeader();

  $("langBtn").addEventListener("click", () => { S.lang = S.lang === "ne" ? "en" : "ne"; store.set("ss_lang", S.lang); renderHeader(); route(); });
  $("loginBtn").addEventListener("click", () => openLogin());
  $("avatarBtn").addEventListener("click", () => {
    $("accountName").textContent = S.user.name; $("logoutBtn").textContent = t("logout"); $("accountClose").textContent = t("close");
    $("accountSheet").showModal();
  });
  $("logoutBtn").addEventListener("click", logout);
  $("googleBtn").addEventListener("click", googleLogin);
  $("devGo").addEventListener("click", devLogin);
  $("devName").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); devLogin(); } });
  $("loginSheet").addEventListener("close", () => { if (!S.user) afterLogin = null; });
  $("gpsBtn").addEventListener("click", async () => {
    try { setPlace(await getGps()); $("placeSheet").close(); } catch { toast(t("gpsFail")); }
  });
  $("placeSave").addEventListener("click", () => { const d = $("districtSel").value; if (d) setPlace({ district: d }); $("placeSheet").close(); });
  $("placeSheet").addEventListener("close", () => { openPlace.done = null; });
  window.addEventListener("hashchange", route);
  route();
}
start();
