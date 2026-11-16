// Private content lives only in this document: no storage, offline cache or telemetry.
document.documentElement.classList.add("js");
let privacyEpoch = 0;
let checkingAvailability = false;
const pending = new Set<AbortController>();
function maskPrivate() {
  const page = document.querySelector<HTMLElement>("[data-private-page]");
  if (!page) return;
  const hadContent = !!page.querySelector("[data-private-content]");
  privacyEpoch++;
  pending.forEach(controller => controller.abort());
  page.querySelector("[data-private-content]")?.remove();
  const reveal = page.querySelector<HTMLFormElement>("[data-reveal-form]");
  if (reveal) reveal.hidden = false;
  const hide = page.querySelector<HTMLButtonElement>("[data-hide-private]");
  if (hide) hide.hidden = true;
  const status = page.querySelector<HTMLElement>("[data-private-status]");
  if (status) status.textContent = "Cadeau masqué. Les modifications non enregistrées ont été retirées de cet écran.";
  if (hadContent && !document.hidden) reveal?.querySelector<HTMLButtonElement>("button")?.focus();
}
async function checkAvailability() {
  const section = document.querySelector<HTMLElement>("[data-private-page]");
  if (!section || document.hidden || checkingAvailability) return;
  const eventId = new URL(location.href).searchParams.get("event_id");
  if (!eventId) return;
  checkingAvailability = true;
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 10000);
  try {
    const response = await fetch("/api/me/availability?event_id=" + encodeURIComponent(eventId),
      {credentials:"same-origin",cache:"no-store",signal:controller.signal});
    if (!response.ok) {
      if ([401,403,404].includes(response.status)) {
        maskPrivate();
        const status = section.querySelector<HTMLElement>("[data-private-status]");
        if (status) status.textContent = "Accès non confirmé. Reconnecte-toi puis recharge cet espace.";
      }
      return;
    }
    const result = await response.json();
    // This endpoint contains only lifecycle facts, never an assignment or a wishlist.
    if (result.available !== true) {
      maskPrivate();
      section.querySelector<HTMLFormElement>("[data-reveal-form]")?.setAttribute("hidden", "");
      const status = section.querySelector<HTMLElement>("[data-private-status]");
      if (status) status.textContent = result.state === "CANCELLED"
        ? "Événement annulé : n’utilise plus ce tirage. Aucun nouveau cadeau ne sera attribué."
        : "Le cadeau n’est pas disponible. Consulte les règles ou recharge cet espace.";
    } else if (result.state === "CLOSED") {
      section.querySelectorAll<HTMLButtonElement>("[data-private-content] form button").forEach(button => button.disabled = true);
      const status = section.querySelector<HTMLElement>("[data-private-status]");
      if (status) status.textContent = "Événement clôturé : préparation en lecture seule.";
    }
  } catch {
    // Offline cannot prove cancellation or availability; the server remains authoritative.
    const status = section.querySelector<HTMLElement>("[data-private-status]");
    if (status) status.textContent = "Connexion indisponible : état du groupe non actualisé. Masque le cadeau si tu quittes cet écran.";
  } finally {
    clearTimeout(timeout); checkingAvailability = false;
  }
}

function enhance() {
  document.querySelectorAll<HTMLButtonElement>("[data-hide-private]").forEach(button => {
    button.onclick = () => { maskPrivate(); document.querySelector<HTMLButtonElement>("[data-reveal-form] button")?.focus(); };
  });
  document.querySelectorAll<HTMLButtonElement>("[data-copy]").forEach(button => {
    button.onclick = async () => { try { await navigator.clipboard.writeText(button.dataset.copy ?? ""); button.textContent = "Copié"; } catch { button.textContent = "Sélectionne et copie le titre ci-dessus"; } };
  });
  document.querySelectorAll<HTMLFormElement>("form[data-async]").forEach(form => {
    form.onsubmit = async (event: SubmitEvent) => {
      event.preventDefault();
      if (form.getAttribute("aria-busy") === "true") return;
      const controller = new AbortController(), epoch = privacyEpoch;
      pending.add(controller);
      const buttons = Array.from(form.querySelectorAll<HTMLButtonElement>("button[type=submit],button:not([type])"));
      const data = new FormData(form);
      const submitter = event.submitter as HTMLButtonElement | null;
      if (submitter?.name) data.set(submitter.name, submitter.value);
      const status = document.createElement("div"); status.role = "status"; status.className = "notice";
      status.textContent = "Enregistrement en cours…";
      form.querySelector("[data-form-status]")?.remove(); status.dataset.formStatus = ""; form.prepend(status);
      form.setAttribute("aria-busy", "true"); buttons.forEach(button => button.disabled = true);
      const timeout = window.setTimeout(() => controller.abort(), 15000);
      try {
        const response = await fetch(new URL(form.getAttribute("action") || location.href, location.href), {method:"POST", body:data, credentials:"same-origin", signal:controller.signal});
        if (new URL(response.url).origin !== location.origin) throw new Error("origin");
        if (response.status === 401 || response.status === 403) {
          status.textContent = "Session expirée ou accès refusé. Ta saisie est conservée dans cette page. ";
          const link = document.createElement("a"); link.href = "/accounts/login/code/"; link.target = "_blank"; link.rel = "noopener"; link.textContent = "Se reconnecter dans un autre onglet";
          const resume = document.createElement("button"); resume.type = "button"; resume.textContent = "Reprendre après connexion";
          resume.onclick = async () => { try {
            const fresh = await fetch(location.href, {credentials:"same-origin",cache:"no-store"});
            if (!fresh.ok) throw new Error("session");
            const doc = new DOMParser().parseFromString(await fresh.text(), "text/html");
            const csrf = doc.querySelector<HTMLInputElement>("input[name=csrfmiddlewaretoken]")?.value;
            if (!csrf) throw new Error("csrf");
            form.querySelectorAll<HTMLInputElement>("input[name=csrfmiddlewaretoken]").forEach(input => input.value = csrf);
            resume.textContent = "Session reprise : vérifie puis enregistre"; resume.disabled = true;
          } catch { resume.textContent = "Connexion non confirmée, réessaie"; } };
          status.append(link, document.createTextNode(" "), resume); return;
        }
        if (response.status >= 500 || !(response.headers.get("content-type") ?? "").includes("text/html")) throw new Error("unconfirmed");
        const html = await response.text();
        if (epoch !== privacyEpoch) return;
        const doc = new DOMParser().parseFromString(html, "text/html");
        // Scripts are self-hosted and already loaded; imported markup never executes scripts.
        doc.querySelectorAll("script").forEach(script => script.remove());
        document.body.replaceWith(document.importNode(doc.body,true));
        document.title = "Noël Secret — accès personnel";
        history.replaceState(null,"",response.url); enhance();
        const focus = document.querySelector<HTMLElement>(".error-summary,main h1");
        if (focus) { focus.tabIndex = -1; focus.focus(); }
      } catch {
        if (epoch === privacyEpoch) status.textContent = "Enregistrement non confirmé (réseau ou délai dépassé). Ta saisie reste dans cette page. Réessaie la même demande ; ne suppose pas qu’elle a échoué côté serveur.";
      } finally {
        clearTimeout(timeout); pending.delete(controller); form.removeAttribute("aria-busy"); buttons.forEach(button => button.disabled = false);
      }
    };
  });
}
document.addEventListener("keydown", event => { if (event.key === "Escape") maskPrivate(); });
window.addEventListener("pagehide", maskPrivate);
window.addEventListener("focus", () => { void checkAvailability(); });
window.setInterval(() => { void checkAvailability(); }, 15000);
window.addEventListener("pageshow", event => { if (event.persisted) maskPrivate(); });
document.addEventListener("visibilitychange", () => { if (document.hidden) maskPrivate(); else void checkAvailability(); });
enhance();
