/**
 * auth.js — Universal auth layer for Flarixo AI
 *
 * What it does on every page that includes it:
 *  1. Reads the stored token + user profile from localStorage
 *  2. Populates existing navbar elements (index.html / tools.html)
 *     OR injects a user-chip + dropdown into .header-actions / nav
 *  3. Exposes window.getToken() and window.authFetch() for API calls
 *  4. Exposes window.signOut() for logout
 */
(function () {
  "use strict";

  /* ─── Storage keys ──────────────────────────────────────────────────────── */
  var TOKEN_KEY   = "access_token";
  var FALLBACK    = "token";
  var USER_KEY    = "auth_user";
  var CLEAR_KEYS  = [TOKEN_KEY, FALLBACK, USER_KEY, "user", "username"];

  /* ─── Helpers ────────────────────────────────────────────────────────────── */

  function getToken() {
    return localStorage.getItem(TOKEN_KEY) || localStorage.getItem(FALLBACK) || "";
  }
  window.getToken = getToken;

  function getUser() {
    try { return JSON.parse(localStorage.getItem(USER_KEY)) || {}; }
    catch (_) { return {}; }
  }

  /** Drop-in fetch() wrapper that attaches the Bearer token automatically */
  window.authFetch = function (url, options) {
    options = options || {};
    options.credentials = options.credentials || "include";
    var token = getToken();
    if (token) {
      options.headers = Object.assign({}, options.headers, {
        Authorization: "Bearer " + token
      });
    }
    return fetch(url, options);
  };

  /* ─── Sign-out ──────────────────────────────────────────────────────────── */

  function signOut() {
    var token = getToken();
    fetch("/logout", {
      method: "POST",
      credentials: "include",
      headers: token ? { Authorization: "Bearer " + token } : {}
    }).catch(function () {});
    CLEAR_KEYS.forEach(function (k) { localStorage.removeItem(k); });
    window.location.href = "/loginSystem";
  }
  window.signOut = signOut;

  /* ─── Dropdown styles (injected once) ──────────────────────────────────── */

  function injectStyles() {
    if (document.getElementById("_flarixo-auth-css")) return;
    var s = document.createElement("style");
    s.id = "_flarixo-auth-css";
    s.textContent = [
      /* chip wrapper */
      ".fx-chip-wrap{position:relative;display:inline-flex;align-items:center;}",

      /* the clickable pill */
      ".fx-chip{display:inline-flex;align-items:center;gap:8px;",
        "background:var(--surface,#1f1f2a);",
        "border:1px solid var(--border,rgba(255,255,255,0.08));",
        "border-radius:50px;padding:5px 12px 5px 5px;",
        "font-size:.82rem;font-weight:500;color:var(--text2,#a0a0b8);",
        "cursor:pointer;transition:border-color .2s;user-select:none;}",
      ".fx-chip:hover{border-color:rgba(124,58,237,.45);}",

      /* avatar circle */
      ".fx-avatar{width:28px;height:28px;border-radius:50%;flex-shrink:0;",
        "background:linear-gradient(135deg,#7c3aed,#06b6d4);",
        "display:flex;align-items:center;justify-content:center;",
        "font-size:.76rem;font-weight:700;color:#fff;text-transform:uppercase;}",

      ".fx-chip-name{max-width:90px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}",

      /* caret */
      ".fx-caret{margin-left:2px;opacity:.55;transition:transform .2s;flex-shrink:0;}",
      ".fx-chip-wrap.open .fx-caret{transform:rotate(180deg);}",

      /* dropdown panel */
      ".fx-dropdown{",
        "position:absolute;top:calc(100% + 10px);right:0;",
        "min-width:195px;",
        "background:var(--surface,#1f1f2a);",
        "border:1px solid var(--border,rgba(255,255,255,0.1));",
        "border-radius:14px;padding:6px;",
        "box-shadow:0 12px 40px rgba(0,0,0,.45);",
        "opacity:0;visibility:hidden;transform:translateY(-8px);",
        "transition:opacity .18s,transform .18s,visibility .18s;",
        "z-index:9999;}",
      ".fx-chip-wrap.open .fx-dropdown{opacity:1;visibility:visible;transform:translateY(0);}",

      /* header inside dropdown */
      ".fx-dd-head{padding:10px 12px 9px;",
        "border-bottom:1px solid var(--border,rgba(255,255,255,0.08));",
        "margin-bottom:4px;}",
      ".fx-dd-name{font-size:.87rem;font-weight:600;color:var(--text,#f0f0f8);}",
      ".fx-dd-email{font-size:.73rem;color:var(--text3,#6b6b84);margin-top:2px;word-break:break-all;}",

      /* menu rows */
      ".fx-dd-item{display:flex;align-items:center;gap:10px;",
        "padding:9px 12px;border-radius:9px;",
        "font-size:.83rem;font-weight:500;color:var(--text2,#a0a0b8);",
        "cursor:pointer;text-decoration:none;",
        "transition:background .14s,color .14s;",
        "border:none;background:none;width:100%;text-align:left;font-family:inherit;}",
      ".fx-dd-item:hover{background:rgba(255,255,255,0.05);color:var(--text,#f0f0f8);}",
      ".fx-dd-item.danger:hover{background:rgba(248,113,113,.09);color:#f87171;}",
      ".fx-sep{height:1px;background:var(--border,rgba(255,255,255,0.08));margin:4px 0;}"
    ].join("");
    document.head.appendChild(s);
  }

  /* ─── Build the chip + dropdown DOM ────────────────────────────────────── */

  function buildChip(user) {
    var name    = (user.username || user.name || "User").trim();
    var email   = user.email || "";
    var initial = name.charAt(0).toUpperCase();
    var first   = name.split(" ")[0];

    var wrap = document.createElement("div");
    wrap.className = "fx-chip-wrap";
    wrap.id = "fxChipWrap";

    wrap.innerHTML =
      '<div class="fx-chip" id="fxChipBtn" role="button" tabindex="0"' +
        ' aria-haspopup="true" aria-expanded="false">' +
        '<div class="fx-avatar">' + initial + '</div>' +
        '<span class="fx-chip-name">' + first + '</span>' +
        '<svg class="fx-caret" width="12" height="12" fill="none" stroke="currentColor"' +
          ' stroke-width="2.5" viewBox="0 0 24 24"><path d="M6 9l6 6 6-6"/></svg>' +
      '</div>' +
      '<div class="fx-dropdown" role="menu">' +
        '<div class="fx-dd-head">' +
          '<div class="fx-dd-name">' + name + '</div>' +
          (email ? '<div class="fx-dd-email">' + email + '</div>' : '') +
        '</div>' +
        '<a href="/tools" class="fx-dd-item" role="menuitem">' +
          '<svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"' +
            ' viewBox="0 0 24 24"><rect x="2" y="3" width="6" height="6" rx="1"/>' +
            '<rect x="9" y="3" width="6" height="6" rx="1"/><rect x="16" y="3" width="6"' +
            ' height="6" rx="1"/><rect x="2" y="10" width="6" height="6" rx="1"/>' +
            '<rect x="9" y="10" width="6" height="6" rx="1"/>' +
            '<rect x="16" y="10" width="6" height="6" rx="1"/></svg>' +
          'All Tools' +
        '</a>' +
        '<div class="fx-sep"></div>' +
        '<button class="fx-dd-item danger" role="menuitem" id="fxLogoutBtn">' +
          '<svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"' +
            ' viewBox="0 0 24 24"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>' +
            '<polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>' +
          'Sign out' +
        '</button>' +
      '</div>';

    /* toggle dropdown */
    var chipBtn = wrap.querySelector("#fxChipBtn");
    chipBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      var open = wrap.classList.toggle("open");
      chipBtn.setAttribute("aria-expanded", open);
    });
    chipBtn.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); chipBtn.click(); }
      if (e.key === "Escape") { wrap.classList.remove("open"); }
    });
    document.addEventListener("click", function () {
      wrap.classList.remove("open");
      chipBtn.setAttribute("aria-expanded", "false");
    });

    wrap.querySelector("#fxLogoutBtn").addEventListener("click", signOut);
    return wrap;
  }

  /* ─── Attach a dropdown to an existing chip element ──────────────────────── */

  function attachDropdownToChip(chipEl, user) {
    /* Already done? */
    if (chipEl.parentElement && chipEl.parentElement.classList.contains("fx-chip-wrap")) return;
    if (document.getElementById("fxChipWrap")) return;

    var name  = (user.username || user.name || "User").trim();
    var email = user.email || "";
    var first = name.split(" ")[0];

    /* Wrap the existing chip element */
    var wrap = document.createElement("div");
    wrap.className = "fx-chip-wrap";
    wrap.id = "fxChipWrap";
    wrap.style.cssText = "position:relative;display:inline-flex;align-items:center;cursor:pointer;";

    chipEl.parentNode.insertBefore(wrap, chipEl);
    wrap.appendChild(chipEl);
    chipEl.style.cursor = "pointer";

    /* Inject dropdown */
    var dd = document.createElement("div");
    dd.className = "fx-dropdown";
    dd.setAttribute("role", "menu");
    dd.innerHTML =
      '<div class="fx-dd-head">' +
        '<div class="fx-dd-name">' + name + '</div>' +
        (email ? '<div class="fx-dd-email">' + email + '</div>' : '') +
      '</div>' +
      '<a href="/tools" class="fx-dd-item" role="menuitem">' +
        '<svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"' +
          ' viewBox="0 0 24 24"><rect x="2" y="3" width="6" height="6" rx="1"/>' +
          '<rect x="9" y="3" width="6" height="6" rx="1"/>' +
          '<rect x="2" y="10" width="6" height="6" rx="1"/>' +
          '<rect x="9" y="10" width="6" height="6" rx="1"/></svg>' +
        'All Tools' +
      '</a>' +
      '<div class="fx-sep"></div>' +
      '<button class="fx-dd-item danger" id="fxLogoutBtn">' +
        '<svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"' +
          ' viewBox="0 0 24 24"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>' +
          '<polyline points="16 17 21 12 16 7"/>' +
          '<line x1="21" y1="12" x2="9" y2="12"/></svg>' +
        'Sign out' +
      '</button>';
    wrap.appendChild(dd);

    dd.querySelector("#fxLogoutBtn").addEventListener("click", signOut);

    chipEl.addEventListener("click", function (e) {
      e.stopPropagation();
      wrap.classList.toggle("open");
    });
    document.addEventListener("click", function () { wrap.classList.remove("open"); });
  }

  /* ─── Main init ─────────────────────────────────────────────────────────── */

  function init() {
    var token = getToken();
    if (!token) return;           /* not logged in — nothing to do */

    injectStyles();
    var user  = getUser();
    var name  = (user.username || user.name || "User").trim();
    var first = name.split(" ")[0];
    var initial = name.charAt(0).toUpperCase();

    /* ── Hide sign-in button, show user elements ─────────────────────────── */
    var headerSignIn = document.getElementById("headerSignIn");
    if (headerSignIn) {
      headerSignIn.style.display = "none";
      var mobileSignIn = document.querySelector(".mobile-nav .btn-login");
      if (mobileSignIn) mobileSignIn.style.display = "none";
    }

    /* ── Wire existing logout buttons ───────────────────────────────────────*/
    document.querySelectorAll(".btn-logout, [onclick=\"logout()\"]").forEach(function (el) {
      el.removeAttribute("onclick");
      el.addEventListener("click", function (e) { e.preventDefault(); signOut(); });
    });
    var btnSignOut = document.getElementById("btnSignOut");
    if (btnSignOut) { btnSignOut.onclick = signOut; }

    /* ── Handle existing #userChip (index.html / tools.html) ─────────────── */
    var userChip = document.getElementById("userChip");
    if (userChip) {
      /* Populate avatar & name */
      var userAvatar   = document.getElementById("userAvatar");
      var userChipName = document.getElementById("userChipName");
      if (userAvatar)   userAvatar.textContent   = initial;
      if (userChipName) userChipName.textContent = first;

      /* Make it visible */
      userChip.classList.add("visible");
      userChip.style.display = "";

      /* Hide the standalone sign-out button — dropdown handles that now */
      if (btnSignOut) { btnSignOut.style.display = "none"; btnSignOut.classList.remove("visible"); }

      /* Attach dropdown to the chip */
      attachDropdownToChip(userChip, user);

      /* Hero badge */
      var heroBadge = document.getElementById("heroBadgeText");
      if (heroBadge) heroBadge.textContent = "Welcome back, " + first;

      return; /* existing chip handled — done */
    }

    /* ── No existing chip → inject our full chip into .header-actions ────── */
    if (!document.getElementById("fxChipWrap")) {
      var headerActions = document.querySelector(".header-actions");
      if (headerActions) {
        headerActions.insertBefore(buildChip(user), headerActions.firstChild);
      } else {
        var nav = document.querySelector("header nav, nav");
        if (nav) nav.appendChild(buildChip(user));
      }
    }
  }

  /* ─── Page-level auth guard ─────────────────────────────────────────────── */
  /* Runs immediately (before DOM ready) so the page doesn't flash content.   */
  /* Pages that are publicly accessible — everything else needs a token.      */

  var PUBLIC_PATHS = ["/", "/loginSystem", "/forget", "/pricing", "/contact",
                      "/reset-password", "/register"];

  (function guardPage() {
    var path = window.location.pathname.replace(/\/$/, "") || "/";
    var isPublic = PUBLIC_PATHS.some(function (p) { return p === path; }) ||
                   path.indexOf("/api/") === 0 ||
                   path.indexOf("/assets/") === 0;
    if (isPublic) return;

    var token = localStorage.getItem(TOKEN_KEY) || localStorage.getItem(FALLBACK) || "";
    if (!token) {
      var dest = encodeURIComponent(window.location.pathname + window.location.search);
      window.location.replace("/loginSystem?next=" + dest);
    }
  })();

  /* ─── Run when DOM is ready ─────────────────────────────────────────────── */
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

})();
