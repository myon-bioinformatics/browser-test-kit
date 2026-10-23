(options) => {
  /* Both hosts pass this expression to Playwright. It reads the main document only. */
  const includeHidden = !!(options && options.includeHidden);
  const roleFilter = options && options.role ? String(options.role).toLowerCase() : "";
  const hardCap = options && Number.isFinite(options.hardCap) && options.hardCap >= 1 ? Math.floor(options.hardCap) : 500;
  const selector = [
    "a[href]", "button", "input", "select", "textarea", "summary",
    "[role='button']", "[role='link']", "[role='textbox']", "[role='checkbox']",
    "[role='radio']", "[role='tab']", "[role='menuitem']", "[role='combobox']",
    "[role='switch']", "[role='searchbox']", "[contenteditable='true']", "[contenteditable='']"
  ].join(",");

  const clip = (value) => {
    const text = String(value || "").replace(/\s+/g, " ").trim();
    return text.length > 120 ? text.slice(0, 120) : text;
  };

  const roleOf = (el) => {
    const explicit = (el.getAttribute("role") || "").trim().toLowerCase();
    if (explicit) return explicit;
    const editable = el.getAttribute("contenteditable");
    if (editable !== null && editable.toLowerCase() !== "false") return "textbox";
    const tag = el.tagName;
    if (tag === "A") return "link";
    if (tag === "BUTTON" || tag === "SUMMARY") return "button";
    if (tag === "SELECT") return "combobox";
    if (tag === "TEXTAREA") return "textbox";
    if (tag === "INPUT") {
      const type = (el.getAttribute("type") || "text").toLowerCase();
      const map = {
        search: "searchbox", checkbox: "checkbox", radio: "radio", range: "slider",
        number: "spinbutton", button: "button", submit: "button", reset: "button",
        email: "textbox", password: "textbox", tel: "textbox", url: "textbox", text: "textbox"
      };
      return map[type] || "textbox";
    }
    return "generic";
  };

  const textOf = (el) => clip(el.innerText || el.textContent || "");

  const nameOf = (el) => {
    const aria = el.getAttribute("aria-label");
    if (aria && aria.trim()) return clip(aria);
    const labelled = el.getAttribute("aria-labelledby");
    if (labelled) {
      const parts = labelled.split(/\s+/).map((id) => {
        const node = document.getElementById(id);
        return node ? textOf(node) : "";
      }).filter(Boolean);
      if (parts.length) return clip(parts.join(" "));
    }
    if (el.id) {
      const label = document.querySelector("label[for='" + CSS.escape(el.id) + "']");
      if (label && textOf(label)) return textOf(label);
    }
    const wrap = el.closest && el.closest("label");
    if (wrap && textOf(wrap)) return textOf(wrap);
    const alt = el.getAttribute("alt");
    if (alt && alt.trim()) return clip(alt);
    if (el.tagName === "INPUT" && /^(button|submit|reset)$/i.test(el.getAttribute("type") || "")) {
      if (el.value) return clip(el.value);
    }
    return textOf(el);
  };

  const isVisible = (el) => {
    if (el.hidden || el.getAttribute("aria-hidden") === "true") return false;
    const style = getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };

  const cssOf = (el) => {
    if (el.id && document.querySelectorAll("#" + CSS.escape(el.id)).length === 1) {
      return "#" + CSS.escape(el.id);
    }
    const parts = [];
    let node = el;
    let depth = 0;
    while (node && node.nodeType === 1 && node !== document.body && depth < 6) {
      let part = node.tagName.toLowerCase();
      const parent = node.parentElement;
      if (parent) {
        const same = Array.from(parent.children).filter((child) => child.tagName === node.tagName);
        if (same.length > 1) part += ":nth-of-type(" + (same.indexOf(node) + 1) + ")";
      }
      parts.unshift(part);
      node = parent;
      depth += 1;
    }
    return parts.join(" > ");
  };

  const geometry = (el) => {
    const rect = el.getBoundingClientRect();
    const box = {
      x: Math.floor(rect.x), y: Math.floor(rect.y),
      width: Math.floor(rect.width), height: Math.floor(rect.height)
    };
    const inView = box.width > 0 && box.height > 0 && box.x < window.innerWidth && box.y < window.innerHeight
      && box.x + box.width > 0 && box.y + box.height > 0;
    if (!inView) return {box, in_viewport: false, obscured: false};
    const hit = document.elementFromPoint(Math.floor(rect.x + rect.width / 2), Math.floor(rect.y + rect.height / 2));
    return {box, in_viewport: true, obscured: !hit || (hit !== el && !el.contains(hit))};
  };

  const matched = [];
  for (const el of document.querySelectorAll(selector)) {
    if (el.tagName === "INPUT" && (el.getAttribute("type") || "").toLowerCase() === "hidden") continue;
    const role = roleOf(el);
    if (roleFilter && role !== roleFilter) continue;
    const shown = isVisible(el);
    if (!includeHidden && !shown) continue;
    matched.push({el, role, shown});
  }

  const elements = [];
  for (const item of matched.slice(0, hardCap)) {
    const el = item.el;
    const id = el.id || "";
    const testid = el.getAttribute("data-testid") || "";
    const place = geometry(el);
    let css = "";
    try { css = cssOf(el); } catch (error) { css = ""; }
    let idUnique = false;
    let testidUnique = false;
    let cssUnique = false;
    try {
      if (id) idUnique = document.querySelectorAll("#" + CSS.escape(id)).length === 1;
      if (testid) testidUnique = document.querySelectorAll("[data-testid='" + CSS.escape(testid) + "']").length === 1;
      if (css) cssUnique = document.querySelectorAll(css).length === 1;
    } catch (error) {
      idUnique = false;
      testidUnique = false;
      cssUnique = false;
    }
    elements.push({
      tag: el.tagName.toLowerCase(),
      role: item.role,
      name: nameOf(el),
      text: textOf(el),
      id, testid,
      href: el.tagName === "A" && el.href ? String(el.href).slice(0, 500) : "",
      visible: item.shown,
      enabled: !el.disabled && el.getAttribute("aria-disabled") !== "true",
      in_viewport: place.in_viewport,
      obscured: place.obscured,
      box: place.box,
      parent_tag: el.parentElement ? el.parentElement.tagName.toLowerCase() : "",
      css, id_unique: idUnique, testid_unique: testidUnique, css_unique: cssUnique
    });
  }

  let shadowRoots = false;
  let shadowScan = "complete";
  const nodes = document.querySelectorAll("*");
  const scanCount = Math.min(nodes.length, 2000);
  for (let i = 0; i < scanCount; i++) {
    if (nodes[i].shadowRoot) { shadowRoots = true; break; }
  }
  if (!shadowRoots && nodes.length > 2000) shadowScan = "partial";

  return {
    title: document.title || "",
    child_frames: window.length,
    shadow_roots: shadowRoots,
    shadow_scan: shadowScan,
    total: matched.length,
    truncated: matched.length > hardCap,
    elements
  };
}
