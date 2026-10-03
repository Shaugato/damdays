/* sheet.js (WP-A)
 * One sheet for every second level (UI_SPEC 2.3, 5.13): the dam, the glossary,
 * setup, the text, the Proof pictures, install. A bottom sheet on phones, a
 * 560 px side panel on desktop. Sheets never stack: opening one while another
 * is open swaps the content (160 ms cross-fade).
 *
 *   DamDays.sheet.open({ title, head, body, short, onClose, swap, split, label })
 *       title    text in the header ("Dam 2 of 5"); the dialog's name
 *       head     optional: { prev: {href, label} | {onClick, label}, next: {...} } for the
 *                pager (previous / next wrap round; href pagers REPLACE the history entry),
 *                or a full HTML string for the header row (a close button is added if it has none)
 *       body     HTML string or a DOM node
 *       short    true: sized to its content on phones (glossary, install)
 *       onClose  called once when this content leaves: onClose("close" | "route" | "replace")
 *       swap     force the cross-fade (it is automatic when a sheet is already open)
 *       split    desktop only: no scrim, the page beside stays usable (default: true on My farm)
 *       label    aria-label when the title alone is not a good name
 *       wide     desktop only: "wide" (880 px: charts and tables that need the room) or "wider"
 *                (1160 px: a big map with its controls beside it); default the 560 px panel
 *       foot     optional HTML for a bar fixed under the scrolling body (a Save button), so it never
 *                covers what is in the body; DamDays.sheet.foot(html) changes it later
 *     returns the sheet body element (render into it, wire events).
 *   DamDays.sheet.close()    what X, Escape and the scrim do: one level up (Back if we came
 *                            from there, else replace the address with the level above)
 *   DamDays.sheet.hide(why)  hide without touching the address (the router uses it)
 *   DamDays.sheet.isOpen(), DamDays.sheet.body(), DamDays.sheet.el
 *
 * Focus: goes to the sheet title on open, stays inside the sheet (Tab wraps), and returns to
 * whatever opened it on close. role="dialog", aria-modal="true". Arrow keys step the pager.
 */
window.DamDays = window.DamDays || {};

DamDays.sheet = (function () {
  "use strict";

  const esc = (t) => String(t === null || t === undefined ? "" : t)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const icon = (id) => (DamDays.icon ? DamDays.icon(id) :
    '<svg class="i" aria-hidden="true"><use href="#' + id + '"/></svg>');
  const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), ' +
    'textarea:not([disabled]), summary, [tabindex]:not([tabindex="-1"])';

  let el = null, headEl = null, bodyEl = null, footEl = null, scrim = null;
  let open = false;
  let onClose = null;
  let returnFocus = null;
  let openedAt = "";             // the address the sheet was opened at ("#farm/dam-1"): where focus goes back to
  let pager = { prev: null, next: null };
  let swapTimer = 0;
  let bodyScrolled = false;      // the body is scrolled down (kept by a scroll listener, so opening never reads layout)

  function ensure() {
    if (el) return;
    el = document.getElementById("sheet");
    if (!el) {
      el = document.createElement("div");
      el.id = "sheet";
      el.className = "sheet";
      el.innerHTML = '<div class="sheet-grip" aria-hidden="true"></div><div class="sheet-head" id="sheet-head"></div>' +
                     '<div class="sheet-body" id="sheet-body"></div>';
      document.body.appendChild(el);
    }
    el.setAttribute("role", "dialog");
    el.setAttribute("aria-modal", "true");
    el.setAttribute("tabindex", "-1");
    el.setAttribute("aria-hidden", "true");
    headEl = el.querySelector(".sheet-head");
    bodyEl = el.querySelector(".sheet-body");
    footEl = el.querySelector(".sheet-foot");
    if (!footEl) {
      footEl = document.createElement("div");
      footEl.className = "sheet-foot";
      footEl.hidden = true;
      bodyEl.after(footEl);
    }
    bodyEl.tabIndex = 0;
    bodyEl.setAttribute("role", "region");
    bodyEl.setAttribute("aria-labelledby", "sheet-title");
    scrim = document.getElementById("sheet-scrim");
    bodyEl.addEventListener("scroll", () => { bodyScrolled = bodyEl.scrollTop > 0; }, { passive: true });
    if (!scrim) {
      scrim = document.createElement("div");
      scrim.id = "sheet-scrim";
      scrim.className = "scrim";
      el.parentNode.insertBefore(scrim, el);
    }
    scrim.setAttribute("aria-hidden", "true");
    scrim.addEventListener("click", close);
    headEl.addEventListener("click", onHeadClick);
    el.addEventListener("click", (event) => {
      if (event.target.closest("[data-close]")) { event.preventDefault(); close(); }
    });
    document.addEventListener("keydown", onKey);
  }

  // ---- header -----------------------------------------------------------------
  function pagerHtml(which, p) {
    if (!p) return '<span class="spacer" aria-hidden="true"></span>';
    const ico = icon(which === "prev" ? "i-back" : "i-chev");
    const label = esc(p.label || (which === "prev" ? "Previous" : "Next"));
    if (p.href) {
      return '<a class="iconbtn" href="' + esc(p.href) + '" data-pager="' + which + '" aria-label="' + label + '">' + ico + "</a>";
    }
    return '<button class="iconbtn" type="button" data-pager="' + which + '" aria-label="' + label + '">' + ico + "</button>";
  }
  const closeHtml = () => '<button class="iconbtn" type="button" data-close aria-label="Close">' + icon("i-x") + "</button>";

  function renderHead(opts) {
    const before = document.activeElement;
    const keep = before && headEl.contains(before)
      ? (before.dataset.pager ? '[data-pager="' + before.dataset.pager + '"]' : before.hasAttribute("data-close") ? "[data-close]" : null)
      : null;
    if (typeof opts.head === "string") {
      pager = { prev: null, next: null };
      headEl.innerHTML = opts.head + (/data-close/.test(opts.head) ? "" : closeHtml());
    } else {
      const h = opts.head || {};
      pager = { prev: h.prev || null, next: h.next || null };
      headEl.innerHTML = pagerHtml("prev", pager.prev) +
        '<p class="sheet-title" id="sheet-title" tabindex="-1">' + esc(opts.title || "") + "</p>" +
        pagerHtml("next", pager.next) + closeHtml();
    }
    const titled = headEl.querySelector("#sheet-title");
    if (titled && !opts.label) {
      el.setAttribute("aria-labelledby", "sheet-title");
      el.removeAttribute("aria-label");
      bodyEl.setAttribute("aria-labelledby", "sheet-title");
      bodyEl.removeAttribute("aria-label");
    } else {
      el.removeAttribute("aria-labelledby");
      el.setAttribute("aria-label", opts.label || opts.title || "Details");
      bodyEl.removeAttribute("aria-labelledby");
      bodyEl.setAttribute("aria-label", opts.label || opts.title || "Details");
    }
    return keep;
  }

  function onHeadClick(event) {
    const btn = event.target.closest("[data-pager]");
    if (!btn) return;
    event.preventDefault();
    step(btn.dataset.pager);
  }

  /** Step the pager: "prev" or "next". Address pagers replace the history entry (Back closes the sheet). */
  function step(which) {
    const p = pager[which];
    if (!p) return;
    if (typeof p.onClick === "function") p.onClick();
    else if (p.href && DamDays.router) DamDays.router.go(p.href, { replace: true });
    else if (p.href) location.replace(p.href);
  }

  // ---- open and close -----------------------------------------------------------
  function focusTitle() {
    const target = el.querySelector("#sheet-title") || el;
    try { target.focus({ preventScroll: true }); } catch (e) { target.focus(); }
  }

  function openSheet(opts) {
    ensure();
    opts = opts || {};
    const wasOpen = open;
    if (wasOpen && onClose) { const fn = onClose; onClose = null; try { fn("replace"); } catch (e) { console.error(e); } }
    const focusWasInside = wasOpen && el.contains(document.activeElement);

    el.classList.toggle("is-short", Boolean(opts.short));
    el.classList.toggle("is-wide", opts.wide === "wide" || opts.wide === true);
    el.classList.toggle("is-wider", opts.wide === "wider");
    setFoot(opts.foot);
    const keep = renderHead(opts);
    if (opts.body instanceof Node) bodyEl.replaceChildren(opts.body);
    else bodyEl.innerHTML = opts.body === undefined || opts.body === null ? "" : String(opts.body);
    // back to the top only when it is scrolled: setting scrollTop forces a layout, a long task on a cold deep link
    if (bodyScrolled) { bodyEl.scrollTop = 0; bodyScrolled = false; }

    if (wasOpen || opts.swap) {
      clearTimeout(swapTimer);
      bodyEl.classList.remove("is-swapping");
      void bodyEl.offsetWidth;                       // restart the fade
      bodyEl.classList.add("is-swapping");
      swapTimer = setTimeout(() => bodyEl.classList.remove("is-swapping"), 220);
    }
    const route = DamDays.router && DamDays.router.current ? DamDays.router.current() : null;
    const split = opts.split !== undefined ? Boolean(opts.split) : Boolean(route && route.view === "farm");
    document.body.classList.toggle("sheet-split", split);
    onClose = typeof opts.onClose === "function" ? opts.onClose : null;

    if (!wasOpen) {
      returnFocus = document.activeElement && document.activeElement !== document.body ? document.activeElement : null;
      openedAt = location.hash;
      open = true;
      el.setAttribute("aria-hidden", "false");
      document.body.classList.add("sheet-open");
      // after the frame that shows it: focusing needs a layout, which then comes from the browser's own rendering step
      requestAnimationFrame(() => setTimeout(() => { if (open) focusTitle(); }, 0));
    } else if (keep && headEl.querySelector(keep)) {
      headEl.querySelector(keep).focus({ preventScroll: true });
    } else if (focusWasInside) {
      focusTitle();
    }
    return bodyEl;
  }

  /** The bar under the body (opts.foot): HTML, or nothing to hide it. */
  function setFoot(html) {
    if (!footEl) return;
    const on = html !== undefined && html !== null && html !== "";
    footEl.innerHTML = on ? String(html) : "";
    footEl.hidden = !on;
    el.classList.toggle("has-foot", on);
  }

  /** Hide the sheet without touching the address. */
  function hide(why) {
    if (!open) return;
    open = false;
    document.body.classList.remove("sheet-open");
    el.setAttribute("aria-hidden", "true");
    const fn = onClose;
    onClose = null;
    if (fn) { try { fn(why || "close"); } catch (e) { console.error(e); } }
    const target = focusTarget(returnFocus);
    returnFocus = null;
    if (target) {
      try { target.focus({ preventScroll: true }); } catch (e) { /* ignore */ }
    } else if (el.contains(document.activeElement)) {
      document.activeElement.blur();
    }
  }

  /** Can focus land here: in the page, shown, and not in a hidden view? */
  function focusable(n) {
    return Boolean(n && n.isConnected && typeof n.focus === "function" && !el.contains(n) && n.getClientRects().length &&
      !n.closest("[hidden], .view:not(.is-active), [aria-hidden='true']"));
  }

  /**
   * Where focus goes when the sheet closes: what opened it, if it is still shown; else the link to the same
   * sheet in the page now shown (a dam's row); else that page's heading. Never lost to the body.
   */
  function focusTarget(opener) {
    if (focusable(opener)) return opener;
    const view = document.querySelector(".view.is-active") || document.querySelector("main");
    if (!view) return null;
    if (openedAt) {
      const base = openedAt.split("/").slice(0, 2).join("/");
      const links = Array.from(view.querySelectorAll("a[href]"));
      const same = links.find((a) => a.getAttribute("href") === openedAt && focusable(a)) ||
        links.find((a) => a.getAttribute("href") === base && focusable(a));
      if (same) return same;
    }
    const h = view.querySelector("h1");
    if (h && h.getClientRects().length) {
      if (!h.hasAttribute("tabindex")) h.setAttribute("tabindex", "-1");
      return h;
    }
    return null;
  }

  /** Can Tab reach this element (shown, not inside a closed <details> other than as its summary)? */
  function tabbable(n) {
    if (n === document.activeElement) return true;
    const shown = typeof n.checkVisibility === "function" ? n.checkVisibility({ visibilityProperty: true }) : n.offsetParent !== null;
    if (!shown) return false;
    const closed = n.closest("details:not([open])");
    if (closed && !(n.tagName === "SUMMARY" && n.parentElement === closed)) return false;
    return true;
  }

  /** X, Escape, the scrim: step one level up the addresses (the router hides the sheet). */
  function close() {
    if (!open) return;
    const r = DamDays.router && DamDays.router.current ? DamDays.router.current() : null;
    if (r && r.sub && DamDays.router.up) DamDays.router.up();
    else hide("close");
  }

  // ---- keys: Escape closes, arrows step the pager, Tab stays inside -----------------
  function onKey(event) {
    if (!open) return;
    if (event.key === "Escape") {
      event.preventDefault();
      close();
      return;
    }
    if ((event.key === "ArrowRight" || event.key === "ArrowLeft") && (pager.prev || pager.next) && !event.altKey &&
        !event.ctrlKey && !event.metaKey) {
      const a = document.activeElement;
      if (a && (/^(INPUT|SELECT|TEXTAREA|SUMMARY)$/.test(a.tagName) || a.isContentEditable)) return;
      event.preventDefault();
      step(event.key === "ArrowRight" ? "next" : "prev");
      return;
    }
    // Focus on the title (where it lands on open): the scroll keys scroll the sheet's body.
    const a0 = document.activeElement;
    if (a0 && headEl.contains(a0) && !/^(BUTTON|A)$/.test(a0.tagName) && !event.altKey && !event.ctrlKey && !event.metaKey) {
      const page = Math.max(40, bodyEl.clientHeight - 48);
      const by = { ArrowDown: 40, ArrowUp: -40, PageDown: page, PageUp: -page, " ": event.shiftKey ? -page : page }[event.key];
      if (by !== undefined) { event.preventDefault(); bodyEl.scrollBy({ top: by }); return; }
      if (event.key === "Home" || event.key === "End") {
        event.preventDefault();
        bodyEl.scrollTo({ top: event.key === "Home" ? 0 : bodyEl.scrollHeight });
        return;
      }
    }
    if (event.key === "Tab") {
      const items = Array.from(el.querySelectorAll(FOCUSABLE)).filter(tabbable);
      if (!items.length) { event.preventDefault(); focusTitle(); return; }
      const first = items[0], last = items[items.length - 1];
      const active = document.activeElement;
      if (!el.contains(active)) { event.preventDefault(); first.focus(); return; }
      if (event.shiftKey && (active === first || active === el || active.id === "sheet-title")) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && active === last) { event.preventDefault(); first.focus(); }
    }
  }

  return {
    open: openSheet,
    close,
    hide,
    step,
    isOpen: () => open,
    body: () => { ensure(); return bodyEl; },
    foot: (html) => { ensure(); if (html !== undefined) setFoot(html); return footEl; },
    get el() { ensure(); return el; },
  };
})();
