(function () {
  const dialogSessions = new WeakMap();

  function focusableElements(root) {
    return [...root.querySelectorAll(
      'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), summary, [tabindex]:not([tabindex="-1"])'
    )].filter((element) => !element.hidden && element.getAttribute("aria-hidden") !== "true");
  }

  function showDialog(element, options = {}) {
    if (!element || dialogSessions.has(element)) return element;
    const trigger = options.trigger || document.activeElement;
    const inerted = [];
    for (const child of document.body.children) {
      if (child === element || child.tagName === "SCRIPT" || child.tagName === "LINK") continue;
      if (!child.inert) {
        child.inert = true;
        inerted.push(child);
      }
    }
    element.classList.remove("hidden");
    element.setAttribute("role", element.getAttribute("role") || "dialog");
    element.setAttribute("aria-modal", "true");

    const close = (reason = "dismiss") => {
      const session = dialogSessions.get(element);
      if (!session) return;
      element.removeEventListener("keydown", session.onKeyDown);
      element.removeEventListener("click", session.onBackdropClick);
      session.inerted.forEach((item) => { item.inert = false; });
      dialogSessions.delete(element);
      element.classList.add("hidden");
      if (options.removeOnClose) element.remove();
      if (session.trigger instanceof HTMLElement && document.contains(session.trigger)) session.trigger.focus();
      options.onClose?.(reason);
    };

    const onKeyDown = (event) => {
      if (event.key === "Escape" && options.closeOnEscape !== false) {
        event.preventDefault();
        close("escape");
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = focusableElements(element);
      if (!focusable.length) {
        event.preventDefault();
        element.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    const onBackdropClick = (event) => {
      if (options.closeOnBackdrop && event.target === element) close("backdrop");
    };
    dialogSessions.set(element, { close, trigger, inerted, onKeyDown, onBackdropClick });
    element.addEventListener("keydown", onKeyDown);
    element.addEventListener("click", onBackdropClick);
    window.requestAnimationFrame(() => {
      const target = options.initialFocus || focusableElements(element)[0] || element;
      if (!target.hasAttribute("tabindex") && target === element) target.setAttribute("tabindex", "-1");
      target.focus();
    });
    return element;
  }

  function hideDialog(element, reason = "dismiss") {
    const session = element ? dialogSessions.get(element) : null;
    if (session) session.close(reason);
    else element?.classList.add("hidden");
  }

  function confirmAction(options = {}) {
    return new Promise((resolve) => {
      const overlay = document.createElement("div");
      overlay.className = "modal-overlay cerebro-confirm-overlay";
      const titleId = `cerebro-confirm-${Date.now()}-${Math.random().toString(16).slice(2)}`;
      const details = (options.details || []).map((detail) => `<li>${escapeHtml(detail)}</li>`).join("");
      overlay.setAttribute("aria-labelledby", titleId);
      overlay.innerHTML = `
        <div class="modal cerebro-confirm-dialog">
          <h2 id="${titleId}">${escapeHtml(options.title || "Confirm action")}</h2>
          <p>${escapeHtml(options.message || "Are you sure?")}</p>
          ${details ? `<ul class="confirm-detail-list">${details}</ul>` : ""}
          <div class="modal-actions">
            <button type="button" data-dialog-action="cancel">${escapeHtml(options.cancelLabel || "Cancel")}</button>
            <button type="button" data-dialog-action="confirm" class="${options.danger ? "danger-button" : ""}">${escapeHtml(options.confirmLabel || "Continue")}</button>
          </div>
        </div>
      `;
      let resolved = false;
      const finish = (value) => {
        if (resolved) return;
        resolved = true;
        hideDialog(overlay, value ? "confirm" : "cancel");
        resolve(value);
      };
      overlay.querySelector('[data-dialog-action="cancel"]').addEventListener("click", () => finish(false));
      overlay.querySelector('[data-dialog-action="confirm"]').addEventListener("click", () => finish(true));
      document.body.appendChild(overlay);
      showDialog(overlay, {
        removeOnClose: true,
        closeOnBackdrop: true,
        onClose: () => {
          if (!resolved) {
            resolved = true;
            resolve(false);
          }
        },
      });
    });
  }

  function openInspector(options = {}) {
    const overlay = document.createElement("div");
    overlay.className = "cerebro-inspector-overlay";
    const titleId = `cerebro-inspector-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    overlay.setAttribute("aria-labelledby", titleId);
    overlay.innerHTML = `
      <aside class="cerebro-inspector" aria-label="${escapeAttribute(options.ariaLabel || options.title || "Details")}">
        <header class="cerebro-inspector-head">
          <div>
            <p class="eyebrow">${escapeHtml(options.kicker || "Details")}</p>
            <h2 id="${titleId}">${escapeHtml(options.title || "Details")}</h2>
            <p class="cerebro-inspector-subtitle">${escapeHtml(options.subtitle || "")}</p>
          </div>
          <button class="icon-button" type="button" data-inspector-close aria-label="Close details" title="Close">&times;</button>
        </header>
        <div class="cerebro-inspector-body" aria-live="polite">${options.content || '<p class="technical-empty">Loading...</p>'}</div>
      </aside>
    `;
    document.body.appendChild(overlay);
    overlay.querySelector("[data-inspector-close]").addEventListener("click", () => hideDialog(overlay, "close"));
    showDialog(overlay, { removeOnClose: true, closeOnBackdrop: true, trigger: options.trigger });
    const body = overlay.querySelector(".cerebro-inspector-body");
    return {
      element: overlay,
      body,
      setContent(html) { body.innerHTML = html; },
      setSubtitle(text) {
        const subtitle = overlay.querySelector(".cerebro-inspector-subtitle");
        subtitle.textContent = text || "";
      },
      close() { hideDialog(overlay, "close"); },
    };
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function escapeAttribute(value) {
    return escapeHtml(value).replaceAll("\n", "&#10;");
  }

  window.CEREBROUI = { showDialog, hideDialog, confirm: confirmAction, openInspector };
})();
