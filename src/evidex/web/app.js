"use strict";
const $ = (s, root = document) => root.querySelector(s);
const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const labels = {
  en: {
    workspace: "Workspace",
    projects: "My projects",
    guide: "Research principles",
    signout: "Sign out",
    eyebrow: "YOUR RESEARCH, CONNECTED",
    welcome: "A little clarity. A lot of progress.",
    subtitle: "From a research question to a draft you can trace.",
    new: "New project",
    hero: "Good writing starts with better evidence.",
    heroText:
      "Plan your research, review your sources, and build your argument. One considered step at a time — with you in control.",
    heroLabel: "THE EVIDEX APPROACH",
    all: "All projects",
    waiting: "Needs your review",
    completed: "Completed",
    total: "Total projects",
    active: "In progress",
    search: "Search your projects…",
    empty: "Your next idea starts here.",
    emptyText:
      "Create a project to turn a research question into a structured, source-backed draft.",
    noMatches: "No matching projects.",
    demo: "Synthetic demo",
    demoText:
      "This workspace uses fixture content, not real scholarly evidence. Exports are clearly labeled as demos and must not be submitted or cited.",
    live: "Live integrations",
    unconfigured:
      "Live mode is not configured. Set EVIDEX_LLM_API_KEY on the server to begin.",
    footer: "Built on evidence. Guided by you.",
    footerRight: "Plan → Sources → Outline → Draft → Review",
    authTitle: "A clearer path from question to knowledge.",
    authText:
      "A thoughtful workspace for academic writing. Real sources, visible reasoning, and your approval at every important step.",
    authHeading: "Welcome to Evidex",
    authSub: "Make room for your next research idea.",
    signin: "Sign in",
    signup: "Create account",
    email: "Email address",
    password: "Password",
    passwordHint: "Use 12–128 characters.",
    authNote:
      "Your projects are private to your account. AI assists with the process; you remain the author and final reviewer.",
    createTitle: "Start a research project",
    topic: "Research topic",
    topicPlaceholder: "What question would you like to explore?",
    field: "Field of study",
    fieldPlaceholder: "e.g. Social sciences",
    document: "Document type",
    proposal: "Proposal",
    article: "Article",
    thesis: "Thesis",
    degree: "Degree level",
    bsc: "Bachelor’s",
    msc: "Master’s",
    language: "Document language",
    words: "Target word count",
    method: "Methodology",
    methodPlaceholder: "e.g. Scoping literature review",
    data: "Data situation",
    no_data: "No data — literature-based",
    will_collect: "I plan to collect data",
    has_data: "I have data (not uploaded)",
    dataNote:
      "No dataset upload is available yet. Results that require your data remain placeholders.",
    citation: "Citation style",
    format: "Article structure",
    imrad: "IMRaD",
    review: "Literature review",
    cancel: "Cancel",
    create: "Create project",
    back: "Back to projects",
    wordsUnit: "words",
    created: "Created",
    approval: "Your review makes the difference.",
    approvalText:
      "Read the artifact below before approving. Check scope, relevance, and evidence. The pipeline will not move on without you.",
    approve: "Approve & continue",
    reject: "Request changes",
    feedback: "What should change?",
    retry: "Retry with feedback",
    run: "Start / resume pipeline",
    working: "Working through the pipeline…",
    workingText:
      "You can leave this page. Progress is saved; we’ll pause at the next approval checkpoint.",
    needsHuman: "This stage needs your attention.",
    needsText:
      "The checks could not pass. Review the feedback, then request another attempt. Nothing has been silently accepted.",
    ready: "Your reviewed draft is ready.",
    readyText:
      "Download your files and evidence audit. Verify all claims and formatting before any academic use.",
    artifacts: "Research artifacts",
    noArtifacts:
      "No artifacts yet. Start the pipeline to generate the research plan.",
    history: "Activity & audit trail",
    raw: "Structured artifact",
    attempts: "Attempt details",
    sourceWarning:
      "DOI lookup verifies metadata, not claim entailment. Search relevance and abstract-only evidence need your review; retraction coverage is incomplete.",
    references: "sources",
    plan: "Plan",
    intake: "Intake",
    sources: "Sources",
    outline: "Outline",
    write: "Writing",
    output: "Export",
    status_PENDING: "Ready to start",
    status_RUNNING: "In progress",
    status_GATE_PASSED: "Checks passed",
    status_GATE_FAILED: "Retrying",
    status_AWAITING_APPROVAL: "Needs your review",
    status_NEEDS_HUMAN: "Needs attention",
    status_COMPLETED: "Completed",
    status_CANCELLED: "Cancelled",
    status_FAILED: "Failed",
    saved: "Project created",
    error: "Something went wrong. Please try again.",
    feedbackRequired: "Add feedback before continuing.",
    principlesTitle: "Research you can stand behind.",
    principlesIntro:
      "Evidex is an assistant, not an authority. These boundaries are part of the workflow, not optional settings.",
    principle1: "Evidence before assertions",
    principle1Text:
      "Live retrieval uses Crossref DOI metadata and publisher-deposited abstracts. A verified DOI is not proof that a claim is correct. Read the original source and verify relevance. Sources without usable evidence cannot be quietly fabricated or substituted.",
    principle2: "You hold the checkpoints",
    principle2Text:
      "You approve the plan, source registry, and outline. Rejected or failed artifacts stay in the audit trail. Nothing moves forward just because a model says it should.",
    principle3: "No invented results",
    principle3Text:
      "Evidex does not create datasets, interviews, findings, or survey responses. Student-data placeholders stay explicit. Document references are metadata drafts and still need style and institutional review.",
    principle4: "Disclose AI assistance",
    principle4Text:
      "Exports include an AI-use disclosure and a citation audit. Follow your institution’s rules and take responsibility for your final work.",
    close: "Close",
    reviewStage: "Review",
    outputStage: "Export",
    auditDownload: "Citation audit",
    viewSource: "DOI record",
  },
  fa: {
    workspace: "فضای پژوهش",
    projects: "پروژه‌های من",
    guide: "اصول پژوهش",
    signout: "خروج",
    eyebrow: "پژوهش شما، پیوسته و روشن",
    welcome: "شفافیت بیشتر. پیشرفت ماندگار.",
    subtitle: "از پرسش پژوهش تا پیش‌نویسی با شواهد قابل پیگیری.",
    new: "پروژه جدید",
    hero: "نوشتن خوب، از شواهد بهتر آغاز می‌شود.",
    heroText:
      "پژوهش را برنامه‌ریزی کنید، منابع را بررسی کنید و استدلال بسازید. گام‌به‌گام، با تصمیم شما.",
    heroLabel: "رویکرد اویدکس",
    all: "همه پروژه‌ها",
    waiting: "منتظر تأیید شما",
    completed: "تکمیل‌شده",
    total: "کل پروژه‌ها",
    active: "در حال انجام",
    search: "جست‌وجوی پروژه‌ها…",
    empty: "ایده بعدی شما از اینجا شروع می‌شود.",
    emptyText:
      "پروژه‌ای بسازید و پرسش خود را به پیش‌نویسی ساختارمند و مبتنی بر منابع تبدیل کنید.",
    noMatches: "پروژه‌ای پیدا نشد.",
    demo: "نمایش آزمایشی ساختگی",
    demoText:
      "این فضا از محتوای ساختگی استفاده می‌کند، نه شواهد علمی واقعی. فایل‌های آزمایشی نباید ارائه یا استناد شوند.",
    live: "اتصال به خدمات واقعی",
    unconfigured:
      "حالت واقعی تنظیم نشده است. کلید EVIDEX_LLM_API_KEY را در سرور تنظیم کنید.",
    footer: "بر پایه شواهد. با راهبری شما.",
    footerRight: "طرح ← منابع ← ساختار ← نگارش ← بازبینی",
    authTitle: "مسیری روشن‌تر از پرسش به دانش.",
    authText:
      "فضایی دقیق برای نگارش دانشگاهی؛ منابع واقعی، شواهد قابل پیگیری و تأیید شما در هر گام مهم.",
    authHeading: "به اویدکس خوش آمدید",
    authSub: "برای ایده پژوهشی بعدی خود آماده شوید.",
    signin: "ورود",
    signup: "ساخت حساب",
    email: "نشانی ایمیل",
    password: "گذرواژه",
    passwordHint: "بین ۱۲ تا ۱۲۸ نویسه.",
    authNote:
      "پروژه‌ها فقط برای حساب شما قابل دسترسی‌اند. هوش مصنوعی کمک می‌کند؛ نویسنده و بازبین نهایی شما هستید.",
    createTitle: "شروع یک پروژه پژوهشی",
    topic: "موضوع پژوهش",
    topicPlaceholder: "می‌خواهید چه پرسشی را بررسی کنید؟",
    field: "رشته تحصیلی",
    fieldPlaceholder: "برای نمونه: علوم اجتماعی",
    document: "نوع سند",
    proposal: "پروپوزال",
    article: "مقاله",
    thesis: "پایان‌نامه",
    degree: "مقطع تحصیلی",
    bsc: "کارشناسی",
    msc: "کارشناسی ارشد",
    language: "زبان سند",
    words: "تعداد واژه هدف",
    method: "روش پژوهش",
    methodPlaceholder: "برای نمونه: مرور دامنه‌ای منابع",
    data: "وضعیت داده‌ها",
    no_data: "بدون داده — مبتنی بر منابع",
    will_collect: "داده جمع‌آوری خواهم کرد",
    has_data: "داده دارم (بارگذاری نشده)",
    dataNote:
      "بارگذاری مجموعه داده هنوز فراهم نیست. بخش‌های نیازمند داده با جای‌نگهدار مشخص می‌شوند.",
    citation: "شیوه استناد",
    format: "ساختار مقاله",
    imrad: "ساختار IMRaD",
    review: "مرور منابع",
    cancel: "لغو",
    create: "ساخت پروژه",
    back: "بازگشت به پروژه‌ها",
    wordsUnit: "واژه",
    created: "ساخته‌شده",
    approval: "بازبینی شما تفاوت ایجاد می‌کند.",
    approvalText:
      "پیش از تأیید، محتوای زیر را بخوانید. دامنه، ارتباط منابع و شواهد را بررسی کنید. فرایند بدون تأیید شما ادامه نمی‌یابد.",
    approve: "تأیید و ادامه",
    reject: "درخواست تغییر",
    feedback: "چه چیزی باید تغییر کند؟",
    retry: "تلاش مجدد با بازخورد",
    run: "شروع / ادامه فرایند",
    working: "فرایند در حال اجراست…",
    workingText:
      "می‌توانید صفحه را ببندید. پیشرفت ذخیره می‌شود و در نقطه تأیید بعدی توقف می‌کنیم.",
    needsHuman: "این مرحله به توجه شما نیاز دارد.",
    needsText:
      "بررسی‌ها موفق نبودند. بازخورد را بخوانید و دوباره تلاش کنید. هیچ موردی بی‌صدا پذیرفته نشده است.",
    ready: "پیش‌نویس بازبینی‌شده آماده است.",
    readyText:
      "فایل‌ها و ممیزی شواهد را دریافت کنید. پیش از استفاده دانشگاهی، ادعاها و قالب را بررسی کنید.",
    artifacts: "دستاوردهای پژوهش",
    noArtifacts: "هنوز محتوایی وجود ندارد. فرایند را برای ساخت طرح آغاز کنید.",
    history: "رویدادها و ممیزی",
    raw: "داده ساختارمند",
    attempts: "جزئیات تلاش‌ها",
    sourceWarning:
      "بررسی DOI فقط فراداده را تأیید می‌کند، نه درستی ادعا را. ارتباط منابع و شواهد چکیده نیازمند بررسی شماست؛ پوشش مقالات پس‌گرفته‌شده کامل نیست.",
    references: "منبع",
    plan: "طرح",
    intake: "دریافت",
    sources: "منابع",
    outline: "ساختار",
    write: "نگارش",
    output: "خروجی",
    status_PENDING: "آماده شروع",
    status_RUNNING: "در حال انجام",
    status_GATE_PASSED: "بررسی موفق",
    status_GATE_FAILED: "تلاش مجدد",
    status_AWAITING_APPROVAL: "منتظر تأیید شما",
    status_NEEDS_HUMAN: "نیازمند توجه",
    status_COMPLETED: "تکمیل‌شده",
    status_CANCELLED: "لغوشده",
    status_FAILED: "ناموفق",
    saved: "پروژه ساخته شد",
    error: "خطایی رخ داد. دوباره تلاش کنید.",
    feedbackRequired: "ابتدا بازخورد خود را بنویسید.",
    principlesTitle: "پژوهشی که بتوان از آن دفاع کرد.",
    principlesIntro:
      "اویدکس دستیار است، نه مرجع نهایی. این مرزها بخشی از فرایند هستند.",
    principle1: "شواهد پیش از ادعا",
    principle1Text:
      "بازیابی واقعی از فراداده DOI و چکیده ناشر در Crossref استفاده می‌کند. DOI تأییدشده اثبات درستی ادعا نیست. منبع اصلی را بخوانید و ارتباط آن را بررسی کنید. منابع بدون شواهد قابل استفاده جعل یا جایگزین نمی‌شوند.",
    principle2: "نقاط تأیید در اختیار شماست",
    principle2Text:
      "شما طرح، منابع و ساختار را تأیید می‌کنید. موارد ردشده در سابقه ممیزی می‌مانند. تصمیم مدل به‌تنهایی فرایند را جلو نمی‌برد.",
    principle3: "بدون نتایج ساختگی",
    principle3Text:
      "اویدکس داده، مصاحبه، یافته یا پاسخ پرسش‌نامه تولید نمی‌کند. جای‌نگهدار داده دانشجو مشخص می‌ماند. منابع خروجی پیش‌نویس فراداده هستند و باید با شیوه‌نامه دانشگاه تطبیق داده شوند.",
    principle4: "شفافیت درباره کمک هوش مصنوعی",
    principle4Text:
      "خروجی‌ها شامل افشای استفاده از هوش مصنوعی و ممیزی استناد هستند. قوانین مؤسسه خود را رعایت کنید و مسئولیت اثر نهایی را بپذیرید.",
    close: "بستن",
    reviewStage: "بازبینی",
    outputStage: "خروجی",
    auditDownload: "ممیزی استناد",
    viewSource: "رکورد DOI",
  },
};
let lang = localStorage.getItem("evidex-language") === "fa" ? "fa" : "en";
let currentUser = null,
  config = {},
  projects = [],
  selected = null,
  page = "projects",
  filter = "all",
  query = "",
  authMode = "login",
  poll = null;
const t = (key) => labels[lang][key] || labels.en[key] || key;
const stageLabel = (s) => (s === "review" ? t("reviewStage") : t(s));
const stages = [
  "intake",
  "plan",
  "sources",
  "outline",
  "write",
  "review",
  "output",
];
const date = (value) =>
  new Date(value).toLocaleDateString(lang === "fa" ? "fa-IR" : "en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
function toast(message) {
  const n = $("#notice");
  n.textContent = message;
  n.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (n.hidden = true), 6500);
}
async function api(path, options = {}) {
  const response = await fetch("/api" + path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-Evidex-Request": "1",
      ...options.headers,
    },
  });
  const body = response.status === 204 ? null : await response.json();
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith("/auth/")) {
      currentUser = null;
      renderAuth();
    }
    let detail = body?.detail;
    if (Array.isArray(detail))
      detail = detail
        .map((e) => `${e.loc?.slice(1).join(".")}: ${e.msg}`)
        .join("; ");
    throw new Error(detail || t("error"));
  }
  return body;
}
function brand() {
  return '<div class="brand"><span class="brand-mark" aria-hidden="true">e</span>Evidex<span class="small muted"> / </span></div>';
}
function modeBadge() {
  return `<span class="pill"><span class="dot"></span>${t(config.demo ? "demo" : "live")}</span>`;
}
function banner(demo = config.demo) {
  return demo
    ? `<div class="banner"><strong>◈ ${t("demo")}</strong><span>${t("demoText")}</span></div>`
    : !config.configured
      ? `<div class="banner">${t("unconfigured")}</div>`
      : "";
}
function languageButton() {
  return `<button data-language class="text-btn" aria-label="Change language">${lang === "en" ? "فارسی" : "English"}</button>`;
}
function applyLanguage() {
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === "fa" ? "rtl" : "ltr";
}
function wireLanguage() {
  document.querySelectorAll("[data-language]").forEach(
    (b) =>
      (b.onclick = () => {
        lang = lang === "fa" ? "en" : "fa";
        localStorage.setItem("evidex-language", lang);
        applyLanguage();
        if (!currentUser) renderAuth();
        else if (page === "detail" && selected) renderDetail(selected);
        else if (page === "guide") renderGuide();
        else renderDashboard();
      }),
  );
}
function renderAuth() {
  clearTimeout(poll);
  page = "auth";
  $("#app").innerHTML =
    `<main class="auth-page"><section class="auth-story">${brand()}<div><p class="eyebrow">${t("heroLabel")}</p><h1>${t("authTitle")}</h1><p>${t("authText")}</p><div class="auth-steps"><span>01 / ${t("plan")}</span><span>02 / ${t("sources")}</span><span>03 / ${t("write")}</span></div></div><p class="small">${t("footer")}</p></section><section class="auth-form-side"><div class="auth-form">${languageButton()}<h2>${t("authHeading")}</h2><p class="muted">${t("authSub")}</p>${banner()}<div class="auth-tabs"><button data-mode="login" class="${authMode === "login" ? "active" : ""}">${t("signin")}</button>${config.registration ? `<button data-mode="register" class="${authMode === "register" ? "active" : ""}">${t("signup")}</button>` : ""}</div><form id="auth-form"><div class="field"><label for="email">${t("email")}</label><input id="email" type="email" name="email" autocomplete="email" required maxlength="254" placeholder="you@university.edu" dir="ltr"></div><div class="field"><label for="password">${t("password")}</label><input id="password" name="password" type="password" autocomplete="${authMode === "login" ? "current-password" : "new-password"}" minlength="12" maxlength="128" required><small>${t("passwordHint")}</small></div><p id="auth-error" class="error" role="alert"></p><button class="btn primary" type="submit">${t(authMode === "login" ? "signin" : "signup")} <span aria-hidden="true">↗</span></button></form><p class="auth-note">${t("authNote")}</p></div></section></main>`;
  wireLanguage();
  document.querySelectorAll("[data-mode]").forEach(
    (b) =>
      (b.onclick = () => {
        authMode = b.dataset.mode;
        renderAuth();
      }),
  );
  $("#auth-form").onsubmit = async (e) => {
    e.preventDefault();
    const button = $("button[type=submit]", e.target);
    button.disabled = true;
    try {
      currentUser = await api("/auth/" + authMode, {
        method: "POST",
        body: JSON.stringify(Object.fromEntries(new FormData(e.target))),
      });
      await loadDashboard();
    } catch (err) {
      $("#auth-error").textContent = err.message;
      button.disabled = false;
    }
  };
}
function shell(content) {
  $("#app").innerHTML =
    `<div class="shell"><aside class="sidebar">${brand()}<div><p class="eyebrow">${t("workspace")}</p><nav class="nav" aria-label="${t("workspace")}"><button data-nav="projects" class="${page !== "guide" ? "active" : ""}"><span class="nav-icon">▤</span>${t("projects")}<span class="number">${projects.length}</span></button><button data-nav="guide" class="${page === "guide" ? "active" : ""}"><span class="nav-icon">◈</span>${t("guide")}</button></nav></div><div class="sidebar-bottom"><p class="side-note">${t("footer")}<br>${t("authNote")}</p><div class="account"><div class="avatar">${esc(currentUser.email[0].toUpperCase())}</div><span title="${esc(currentUser.email)}">${esc(currentUser.email)}</span></div><button id="signout-side" class="text-btn">${t("signout")}</button></div></aside><div class="workspace"><header class="topbar"><span class="crumb">${t("workspace")} &nbsp; / &nbsp; ${t(page === "guide" ? "guide" : "projects")}</span><div class="top-actions">${modeBadge()}${languageButton()}<button id="signout" class="text-btn">${t("signout")}</button></div></header><main class="content">${content}</main></div></div>`;
  wireLanguage();
  document.querySelectorAll("[data-nav]").forEach(
    (b) =>
      (b.onclick = () => {
        clearTimeout(poll);
        if (b.dataset.nav === "guide") renderGuide();
        else loadDashboard().catch((e) => toast(e.message));
      }),
  );
  const logout = async () => {
    try {
      await api("/auth/logout", { method: "POST" });
      currentUser = null;
      selected = null;
      projects = [];
      renderAuth();
    } catch (e) {
      toast(e.message);
    }
  };
  $("#signout").onclick = logout;
  $("#signout-side").onclick = logout;
}
async function loadDashboard() {
  projects = await api("/projects");
  selected = null;
  renderDashboard();
}
function renderDashboard() {
  clearTimeout(poll);
  page = "projects";
  const count = (status) =>
    projects.filter((p) => p.job.status === status).length;
  shell(
    `<section class="welcome"><div><p class="eyebrow">${t("eyebrow")}</p><h1>${t("welcome")}</h1><p class="muted">${t("subtitle")}</p></div><button class="btn primary" id="new-project">+ ${t("new")}</button></section>${banner()}<section class="hero-card"><div><span class="eyebrow">${t("heroLabel")}</span><h2>${t("hero")}</h2><p>${t("heroText")}</p></div><div class="orbit" aria-hidden="true"><span>e</span></div></section><section class="stats" aria-label="Project statistics"><div class="stat"><span class="stat-label">${t("total")}</span><strong>${projects.length}<small>${t("projects")}</small></strong></div><div class="stat"><span class="stat-label">${t("waiting")}</span><strong>${count("AWAITING_APPROVAL")}<small>${t("waiting")}</small></strong></div><div class="stat"><span class="stat-label">${t("completed")}</span><strong>${count("COMPLETED")}<small>${t("completed")}</small></strong></div></section><section><div class="section-top"><h2>${t("projects")}</h2><input id="search" class="search" type="search" placeholder="${t("search")}" aria-label="${t("search")}" value="${esc(query)}"></div><div class="filters">${["all", "waiting", "completed"].map((f) => `<button data-filter="${f}" class="${filter === f ? "active" : ""}">${t(f)}</button>`).join("")}</div><div id="project-list" class="projects"></div></section><div class="footer-note"><span>◈ &nbsp; ${t("footer")}</span><span>${t("footerRight")}</span></div>`,
  );
  $("#new-project").onclick = createDialog;
  $("#search").oninput = (e) => {
    query = e.target.value;
    renderProjects();
  };
  document.querySelectorAll("[data-filter]").forEach(
    (b) =>
      (b.onclick = () => {
        filter = b.dataset.filter;
        document
          .querySelectorAll("[data-filter]")
          .forEach((x) => x.classList.toggle("active", x === b));
        renderProjects();
      }),
  );
  renderProjects();
}
function tag(status) {
  return `<span class="tag ${status === "AWAITING_APPROVAL" ? "waiting" : status === "NEEDS_HUMAN" || status === "FAILED" ? "failed" : ""}">${t("status_" + status)}</span>`;
}
function renderProjects() {
  const visible = projects.filter(
    (p) =>
      p.brief.topic.toLocaleLowerCase().includes(query.toLocaleLowerCase()) &&
      (filter === "all" ||
        p.job.status ===
          (filter === "waiting" ? "AWAITING_APPROVAL" : "COMPLETED")),
  );
  $("#project-list").innerHTML = visible.length
    ? visible
        .map(
          (p) =>
            `<button class="project-card" data-project="${esc(p.job.job_id)}"><span class="doc-icon" aria-hidden="true">≡</span><div><h3 dir="auto">${esc(p.brief.topic)}</h3><p>${t(p.brief.document_type)} &nbsp;·&nbsp; ${t(p.brief.degree_level)} &nbsp;·&nbsp; ${p.brief.target_words.toLocaleString()} ${t("wordsUnit")} &nbsp;·&nbsp; ${p.brief.language === "fa" ? "فارسی" : "English"}</p></div><div class="project-meta">${tag(p.job.status)}<span class="small muted">${date(p.job.created_at)} ↗</span></div></button>`,
        )
        .join("")
    : `<div class="empty"><div class="eyebrow">01 / ${t("plan")}</div><h3>${t(projects.length ? "noMatches" : "empty")}</h3>${projects.length ? "" : `<p>${t("emptyText")}</p><button class="btn" id="empty-create">+ ${t("new")}</button>`}</div>`;
  document
    .querySelectorAll("[data-project]")
    .forEach(
      (b) =>
        (b.onclick = () =>
          openProject(b.dataset.project).catch((e) => toast(e.message))),
    );
  if ($("#empty-create")) $("#empty-create").onclick = createDialog;
}
function selectField(name, label, values) {
  return `<div class="field"><label for="f-${name}">${t(label)}</label><select id="f-${name}" name="${name}">${values.map(([v, l]) => `<option value="${v}">${l}</option>`).join("")}</select></div>`;
}
function createDialog() {
  const dialog = $("#create-dialog");
  dialog.innerHTML = `<div class="dialog-header"><h2>${t("createTitle")}</h2><button id="close-dialog" aria-label="${t("close")}">✕</button></div><form id="create-form"><div class="form-grid"><div class="field full"><label for="f-topic">${t("topic")}</label><textarea id="f-topic" name="topic" maxlength="1000" placeholder="${t("topicPlaceholder")}" required dir="auto"></textarea></div><div class="field full"><label for="f-field">${t("field")}</label><input id="f-field" name="field" maxlength="200" placeholder="${t("fieldPlaceholder")}" required></div>${selectField(
    "document_type",
    "document",
    ["proposal", "article", "thesis"].map((v) => [v, t(v)]),
  )}${selectField(
    "degree_level",
    "degree",
    ["bsc", "msc"].map((v) => [v, t(v)]),
  )}${selectField(
    "language",
    "language",
    lang === "fa"
      ? [
          ["fa", "فارسی"],
          ["en", "English"],
        ]
      : [
          ["en", "English"],
          ["fa", "فارسی"],
        ],
  )}<div class="field"><label for="f-words">${t("words")}</label><input id="f-words" name="target_words" type="number" min="2000" max="50000" value="3000" required></div>${selectField(
    "citation_style",
    "citation",
    [
      ["apa7", "APA 7 (draft)"],
      ["ieee", "IEEE (draft)"],
      ["vancouver", "Vancouver (draft)"],
    ],
  )}${selectField(
    "article_format",
    "format",
    ["imrad", "review"].map((v) => [v, t(v)]),
  )}<div class="field full"><label for="f-method">${t("method")}</label><input id="f-method" name="methodology" maxlength="1000" placeholder="${t("methodPlaceholder")}" required></div><div class="full">${selectField(
    "data_situation",
    "data",
    ["no_data", "will_collect", "has_data"].map((v) => [v, t(v)]),
  )}<p class="small muted">${t("dataNote")}</p></div></div><p id="create-error" class="error" role="alert"></p><div class="form-actions"><button type="button" id="cancel-dialog" class="btn">${t("cancel")}</button><button class="btn primary" type="submit">${t("create")} ↗</button></div></form>`;
  $("#close-dialog").onclick = $("#cancel-dialog").onclick = () =>
    dialog.close();
  $("#f-document_type").onchange = (e) => {
    $("#f-words").value = { proposal: 3000, article: 6000, thesis: 10000 }[
      e.target.value
    ];
  };
  $("#create-form").onsubmit = async (e) => {
    e.preventDefault();
    const button = $("button[type=submit]", e.target);
    button.disabled = true;
    const brief = Object.fromEntries(new FormData(e.target));
    brief.target_words = Number(brief.target_words);
    try {
      const job = await api("/projects", {
        method: "POST",
        body: JSON.stringify(brief),
      });
      dialog.close();
      projects = await api("/projects");
      toast(t("saved"));
      await openProject(job.job_id);
    } catch (err) {
      $("#create-error").textContent = err.message;
      button.disabled = false;
    }
  };
  dialog.showModal();
}
async function openProject(id) {
  clearTimeout(poll);
  const detail = await api("/projects/" + encodeURIComponent(id));
  selected = detail;
  renderDetail(detail);
  if (detail.busy)
    poll = setTimeout(() => {
      if (page === "detail" && selected?.job.job_id === id)
        openProject(id).catch((e) => toast(e.message));
    }, 2500);
}
function pretty(value) {
  return `<pre class="artifact-data" dir="auto">${esc(JSON.stringify(value, null, 2))}</pre>`;
}
function artifactView(a) {
  const c = a.content;
  if (a.stage === "sources" && Array.isArray(c.sources))
    return `<p class="small muted">${t("sourceWarning")}</p>${c.sources.map((s) => `<article class="source"><h3 dir="auto">${esc(s.title)}</h3><p class="muted" dir="auto">${esc((s.authors || []).join(", "))} · ${esc(s.year)} · ${esc(s.venue || "")}</p><span class="tag">${esc(s.verification?.status)}</span> <span class="small muted">${esc(s.source_id)}</span>${s.doi ? ` <a class="small" href="https://doi.org/${encodeURIComponent(s.doi)}" target="_blank" rel="noopener noreferrer">${t("viewSource")} ↗</a>` : ""}<blockquote dir="auto">${esc(s.abstract || s.notes?.[0]?.paraphrase || "")}</blockquote><p class="small muted">${esc(s.verification?.method || "")}</p></article>`).join("")}<details><summary>${t("raw")}</summary>${pretty(c)}</details>`;
  if (a.stage === "outline" && Array.isArray(c.nodes))
    return (
      c.nodes
        .map(
          (n) =>
            `<div class="outline-row"><div><strong dir="auto">${esc(n.title)}</strong><p class="muted small">${esc(n.purpose)}</p></div><span class="muted small">${esc(n.word_budget)} ${t("wordsUnit")}</span></div>`,
        )
        .join("") +
      `<details><summary>${t("raw")}</summary>${pretty(c)}</details>`
    );
  if (a.stage === "write" && c.body)
    return `<h3 dir="auto">${esc(c.title)}</h3><div class="artifact-text" dir="auto">${esc(c.body)}</div><details><summary>${t("raw")}</summary>${pretty(c)}</details>`;
  if (a.stage === "plan" && c.problem_statement)
    return `<div class="artifact-text" dir="auto">${esc(c.problem_statement)}</div><ul>${(c.research_questions || []).map((q) => `<li><p dir="auto">${esc(q.text)}</p></li>`).join("")}</ul>${pretty(c)}`;
  return pretty(c);
}
function renderDetail(d) {
  page = "detail";
  const s = d.job;
  const stageIndex =
    s.status === "COMPLETED" ? 7 : stages.indexOf(s.current_stage);
  const latest = new Map();
  d.artifacts.forEach((a) =>
    latest.set(a.stage + ":" + a.task_key.split("#")[0], a),
  );
  let controls = "";
  if (d.busy)
    controls = `<div class="checkpoint"><h3><span class="spinner"></span> ${t("working")}</h3><p>${t("workingText")}</p></div>`;
  else if (s.status === "AWAITING_APPROVAL")
    controls = `<div class="checkpoint"><h3>${t("approval")} / ${stageLabel(s.pending_approval)}</h3><p>${t("approvalText")}</p><div class="field"><label for="feedback">${t("feedback")}</label><textarea id="feedback" maxlength="4000"></textarea></div><div class="action-row"><button class="btn primary" data-action="approve">✓ ${t("approve")}</button><button class="btn" data-action="reject">${t("reject")}</button><button class="btn danger" data-action="cancel">${t("cancel")}</button></div></div>`;
  else if (s.status === "NEEDS_HUMAN")
    controls = `<div class="checkpoint"><h3>${t("needsHuman")}</h3><p>${t("needsText")}</p><pre class="artifact-data">${esc(s.feedback_for_retry)}</pre><div class="field"><label for="feedback">${t("feedback")}</label><textarea id="feedback" maxlength="4000"></textarea></div><div class="action-row"><button class="btn primary" data-action="retry">${t("retry")}</button><button class="btn danger" data-action="cancel">${t("cancel")}</button></div></div>`;
  else if (s.status === "COMPLETED")
    controls = `<div class="checkpoint"><h3>${t("ready")}</h3><p>${t("readyText")}</p><div class="action-row">${d.downloads.map((f) => `<a class="btn ${f === "docx" ? "primary" : ""}" href="/api/projects/${encodeURIComponent(s.job_id)}/downloads/${f}">↓ ${f === "json" ? t("auditDownload") : f.toUpperCase()}</a>`).join("")}</div></div>`;
  else if (!["FAILED", "CANCELLED"].includes(s.status))
    controls = `<div class="action-row panel"><button class="btn primary" data-action="run">${t("run")} ↗</button><button class="btn danger" data-action="cancel">${t("cancel")}</button></div>`;
  shell(
    `<button id="back" class="back">← ${t("back")}</button><div class="detail-heading"><div><p class="eyebrow">${t(d.brief.document_type)} / ${t(d.brief.degree_level)}</p><h1 dir="auto">${esc(d.brief.topic)}</h1><p>${esc(d.brief.field)} · ${d.brief.target_words.toLocaleString()} ${t("wordsUnit")} · ${date(s.created_at)}</p></div><div>${tag(s.status)}</div></div>${banner(d.demo)}<div class="stage-track" aria-label="Pipeline progress">${stages.map((v, i) => `<div class="stage ${i < stageIndex ? "done" : i === stageIndex ? "current" : ""}"><b>${i < stageIndex ? "✓" : i + 1}</b>${stageLabel(v)}</div>`).join("")}</div>${controls}<section class="panel"><h2>${t("artifacts")}</h2>${latest.size ? [...latest.values()].map((a) => `<details ${a.stage === s.pending_approval || a.stage === s.current_stage ? "open" : ""}><summary>${stageLabel(a.stage)} / ${esc(a.task_key)} · v${a.version}</summary>${artifactView(a)}</details>`).join("") : `<p class="muted">${t("noArtifacts")}</p>`}</section><section class="panel"><h2>${t("history")}</h2><ul class="events">${d.events
      .slice(-15)
      .reverse()
      .map(
        (e) =>
          `<li><span>${esc(e.event_type.replaceAll("_", " "))}</span><time>${date(e.occurred_at)}</time></li>`,
      )
      .join(
        "",
      )}</ul><details><summary>${t("attempts")}</summary>${pretty(d.attempts.map((a) => ({ stage: a.stage, attempt: a.attempt, status: a.status, error: a.error })))}</details><details><summary>${t("raw")}</summary>${pretty(d.events)}</details></section>`,
  );
  $("#back").onclick = () => loadDashboard().catch((e) => toast(e.message));
  document.querySelectorAll("[data-action]").forEach(
    (b) =>
      (b.onclick = async () => {
        const action = b.dataset.action,
          feedback = $("#feedback")?.value || "";
        if (["retry", "reject"].includes(action) && !feedback.trim()) {
          toast(t("feedbackRequired"));
          return;
        }
        document
          .querySelectorAll("[data-action]")
          .forEach((x) => (x.disabled = true));
        try {
          await api(`/projects/${s.job_id}/actions`, {
            method: "POST",
            body: JSON.stringify({
              action,
              stage: s.pending_approval,
              feedback,
            }),
          });
          if (["approve", "retry"].includes(action))
            await api(`/projects/${s.job_id}/actions`, {
              method: "POST",
              body: JSON.stringify({ action: "run" }),
            });
          await openProject(s.job_id);
        } catch (e) {
          toast(e.message);
          await openProject(s.job_id).catch(() => {});
        }
      }),
  );
}
function renderGuide() {
  page = "guide";
  clearTimeout(poll);
  shell(
    `<article class="policy"><p class="eyebrow">${t("guide")}</p><h1>${t("principlesTitle")}</h1><p>${t("principlesIntro")}</p>${[1, 2, 3, 4].map((i) => `<section class="panel"><span class="eyebrow">0${i}</span><h2>${t("principle" + i)}</h2><p>${t("principle" + i + "Text")}</p></section>`).join("")}</article>`,
  );
}
(async () => {
  applyLanguage();
  try {
    config = await api("/config");
    try {
      currentUser = await api("/auth/me");
    } catch (e) {
      if (!e.message.includes("Sign in")) throw e;
    }
    if (currentUser) await loadDashboard();
    else renderAuth();
  } catch (e) {
    $("#app").innerHTML =
      `<main class="loading"><h1>Evidex</h1><p>${esc(e.message)}</p><button class="btn" id="reload">Retry / تلاش مجدد</button></main>`;
    $("#reload").onclick = () => location.reload();
  }
})();
