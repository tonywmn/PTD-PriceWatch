const C = window.PTD_CONFIG;

const sb = supabase.createClient(
  C.supabaseUrl,
  C.supabasePublishableKey,
  {
    auth: {
      persistSession: true,
      detectSessionInUrl: true,
    },
  },
);

let product;
let sources = [];
let chart;
let days = 30;

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const euro = (value) =>
  value == null
    ? "–"
    : new Intl.NumberFormat("de-DE", {
        style: "currency",
        currency: "EUR",
      }).format(value);

const date = (value) =>
  value
    ? new Intl.DateTimeFormat("de-DE", {
        dateStyle: "short",
        timeStyle: "short",
      }).format(new Date(value))
    : "Noch nicht geprüft";

const logos = {
  "PlayStation Direct DE":
    "https://cdn.simpleicons.org/playstation/0070D1",
  "Amazon.de":
    "https://cdn.simpleicons.org/amazon/FF9900",
  "MediaMarkt DE":
    "https://cdn.simpleicons.org/mediamarkt/DF0000",
  "Saturn DE":
    "https://cdn.simpleicons.org/saturn/0066B3",
  "Alternate DE":
    "https://www.google.com/s2/favicons?domain=alternate.de&sz=128",
  "Expert DE":
    "https://www.google.com/s2/favicons?domain=expert.de&sz=128",
  "Geizhals DE":
    "https://www.google.com/s2/favicons?domain=geizhals.de&sz=128",
  "Idealo DE":
    "https://cdn.simpleicons.org/idealo/FF6600",
};

function toast(message) {
  $("#toast").textContent = message;
  $("#toast").classList.add("show");

  setTimeout(() => {
    $("#toast").classList.remove("show");
  }, 3000);
}

function newestScanTime() {
  return sources
    .map((source) => source.last_checked_at)
    .filter(Boolean)
    .sort()
    .pop() || null;
}

async function load() {
  const { data: products, error: productError } = await sb
    .from("products")
    .select("*")
    .eq("active", true)
    .limit(1);

  if (productError || !products?.length) {
    $("#systemStatus").textContent =
      "Keine Produktkonfiguration";
    return;
  }

  product = products[0];

  const { data: sourceData, error: sourceError } = await sb
    .from("product_sources")
    .select("*,providers(*)")
    .eq("product_id", product.id);

  if (sourceError) {
    $("#systemStatus").textContent =
      "Anbieterdaten konnten nicht geladen werden";
    return;
  }

  sources = sourceData || [];

  render();
  await loadHistory();
}

function render() {
  const validSources = sources
    .filter(
      (source) =>
        source.availability === "available" &&
        source.last_price != null,
    )
    .sort((a, b) => a.last_price - b.last_price);

  const best = validSources[0];

  $("#heroPrice").textContent = best
    ? euro(best.last_price)
    : "Kein Treffer";

  $("#heroText").textContent = best
    ? `${best.providers.name} · verfügbar`
    : "Derzeit kein bestätigtes Angebot";

  $("#alertPrice").textContent = euro(product.alert_price);
  $("#targetPrice").textContent = euro(product.target_price);
  $("#lastUpdated").textContent = date(newestScanTime());
  $("#providerCount").textContent = `${sources.length} Quellen`;

  $("#providerGrid").innerHTML = sources
    .sort((a, b) =>
      a.providers.name.localeCompare(b.providers.name),
    )
    .map((source) => {
      const availability =
        source.availability || "unknown";

      const availabilityLabel =
        availability === "available"
          ? "Verfügbar"
          : availability === "unavailable"
            ? "Nicht verfügbar"
            : "Unbestätigt";

      const providerType =
        source.providers.provider_type === "comparison"
          ? "Vergleichsportal"
          : "Direktanbieter";

      const updatedAt =
        source.last_success_at || source.last_checked_at;

      return `
        ${source.product_url}
          <div class="provider-top">
            <div class="brand">
              ${
                  logos[source.providers.name] ||
                  

              <div>
                <h3>${source.providers.name}</h3>
                <small>${providerType}</small>
              </div>
            </div>

            <span class="badge ${availability}">
              ${availabilityLabel}
            </span>
          </div>

          <div class="provider-price">
            ${euro(source.last_price)}
          </div>

          <div class="provider-meta">
            ${source.status || "Noch nicht geprüft"}
            <br>
            Aktualisiert: ${date(updatedAt)}
          </div>
        </a>
      `;
    })
    .join("");

  fillSettings();
}

async function loadHistory() {
  if (!sources.length) {
    return;
  }

  const since = new Date(
    Date.now() - days * 86400000,
  ).toISOString();

  const sourceIds = sources.map((source) => source.id);

  const { data, error } = await sb
    .from("price_history")
    .select("price,checked_at,source_id")
    .in("source_id", sourceIds)
    .eq("validated", true)
    .gte("checked_at", since)
    .order("checked_at");

  if (error) {
    $("#chartEmpty").hidden = false;
    $("#chartEmpty").textContent =
      "Preishistorie konnte nicht geladen werden.";
    return;
  }

  const rows = data || [];

  $("#chartEmpty").hidden = rows.length > 0;

  const grouped = {};

  rows.forEach((row) => {
    grouped[row.source_id] ??= [];
    grouped[row.source_id].push(row);
  });

  const colors = [
    "#007aff",
    "#34c759",
    "#ff9500",
    "#af52de",
    "#ff3b30",
    "#5ac8fa",
    "#ff2d55",
    "#5856d6",
  ];

  const datasets = Object.entries(grouped).map(
    ([sourceId, values], index) => ({
      label:
        sources.find((source) => source.id === sourceId)
          ?.providers.name || "Quelle",
      data: values.map((row) => ({
        x: row.checked_at,
        y: row.price,
      })),
      borderColor: colors[index % colors.length],
      pointRadius: 1,
      tension: 0.25,
    }),
  );

  chart?.destroy();

  chart = new Chart($("#priceChart"), {
    type: "line",
    data: {
      datasets,
    },
    options: {
      responsive: true,
      parsing: false,
      plugins: {
        legend: {
          display: false,
        },
      },
      scales: {
        x: {
          type: "category",
          ticks: {
            display: false,
          },
          grid: {
            display: false,
          },
        },
        y: {
          grid: {
            color: "rgba(128,128,128,.14)",
          },
        },
      },
    },
  });
}

function fillSettings() {
  if (!product) {
    return;
  }

  $("#alertInput").value = product.alert_price;
  $("#targetInput").value = product.target_price;

  $("#sourceToggles").innerHTML = sources
    .map(
      (source) => `
        <label class="toggle-row">
          ${source.providers.name}

          <input
            class="switch"
            type="checkbox"
            data-id="${source.id}"
            ${source.active ? "checked" : ""}
          >
        </label>
      `,
    )
    .join("");
}

async function authState() {
  const {
    data: { session },
  } = await sb.auth.getSession();

  $("#authBlock").hidden = Boolean(session);
  $("#settingsContent").hidden = !session;
}

async function triggerManualScan() {
  const {
    data: { session },
  } = await sb.auth.getSession();

  if (!session) {
    $("#settingsDialog").showModal();
    await authState();

    toast(
      "Bitte zuerst mit deiner privaten E-Mail anmelden",
    );
    return;
  }

  const previousScanTime = newestScanTime();

  $("#refreshBtn").disabled = true;
  $("#refreshBtn").textContent = "…";

  toast("Preisprüfung wird gestartet");

  const { error } = await sb.functions.invoke(
    "trigger-price-scan",
    {
      body: {},
    },
  );

  if (error) {
    toast(`Start fehlgeschlagen: ${error.message}`);

    $("#refreshBtn").disabled = false;
    $("#refreshBtn").textContent = "↻";
    return;
  }

  toast("Preisprüfung läuft");

  let attempts = 0;
  const maximumAttempts = 18;

  const pollResults = setInterval(async () => {
    attempts += 1;

    await load();

    const currentScanTime = newestScanTime();

    if (
      currentScanTime &&
      currentScanTime !== previousScanTime
    ) {
      clearInterval(pollResults);

      $("#refreshBtn").disabled = false;
      $("#refreshBtn").textContent = "↻";

      toast("Neue Ergebnisse geladen");
      return;
    }

    if (attempts >= maximumAttempts) {
      clearInterval(pollResults);

      $("#refreshBtn").disabled = false;
      $("#refreshBtn").textContent = "↻";

      toast(
        "Scan wurde gestartet. Ergebnisse folgen nach Abschluss.",
      );
    }
  }, 10000);
}

async function enablePush() {
  if (
    !(
      "serviceWorker" in navigator &&
      "PushManager" in window
    )
  ) {
    toast("Web Push wird hier nicht unterstützt");
    return;
  }

  if (C.vapidPublicKey.startsWith("__")) {
    toast("VAPID-Key ist noch nicht eingerichtet");
    return;
  }

  const permission =
    await Notification.requestPermission();

  if (permission !== "granted") {
    toast("Mitteilungen wurden nicht erlaubt");
    return;
  }

  const registration =
    await navigator.serviceWorker.ready;

  const subscription =
    await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: toBytes(
        C.vapidPublicKey,
      ),
    });

  const json = subscription.toJSON();

  const { error } = await sb
    .from("push_subscriptions")
    .insert({
      endpoint: json.endpoint,
      p256dh: json.keys.p256dh,
      auth: json.keys.auth,
      active: true,
    });

  if (error && error.code !== "23505") {
    toast("Push konnte nicht gespeichert werden");
    return;
  }

  toast("Push-Benachrichtigungen sind aktiviert");
}

function toBytes(value) {
  const padding = "=".repeat(
    (4 - (value.length % 4)) % 4,
  );

  const base64 = (value + padding)
    .replace(/-/g, "+")
    .replace(/_/g, "/");

  const raw = atob(base64);

  return Uint8Array.from(
    [...raw].map((character) =>
      character.charCodeAt(0),
    ),
  );
}

$("#refreshBtn").onclick = triggerManualScan;

$("#settingsBtn").onclick =
  $("#settingsTab").onclick = async () => {
    $("#settingsDialog").showModal();
    await authState();
  };

$("#notifyBtn").onclick = enablePush;
$("#enablePush").onclick = enablePush;

$("#loginBtn").onclick = async () => {
  const email = $("#emailInput").value.trim();

  if (!email) {
    toast("Bitte private E-Mail eingeben");
    return;
  }

  const { error } = await sb.auth.signInWithOtp({
    email,
    options: {
      emailRedirectTo: C.appBaseUrl,
    },
  });

  toast(
    error
      ? error.message
      : "Magic Link wurde per E-Mail gesendet",
  );
};

$("#logoutBtn").onclick = async () => {
  await sb.auth.signOut();
  await authState();
  toast("Abgemeldet");
};

$("#saveSettings").onclick = async () => {
  const updates = {
    alert_price: Number(
      $("#alertInput").value,
    ),
    target_price: Number(
      $("#targetInput").value,
    ),
  };

  const { error } = await sb
    .from("products")
    .update(updates)
    .eq("id", product.id);

  if (error) {
    toast(error.message);
    return;
  }

  for (const toggle of $$(".switch")) {
    await sb
      .from("product_sources")
      .update({
        active: toggle.checked,
      })
      .eq("id", toggle.dataset.id);
  }

  toast("Einstellungen gespeichert");
  await load();
};

$$(".segmented button").forEach((button) => {
  button.onclick = async () => {
    $$(".segmented button").forEach(
      (item) => item.classList.remove("active"),
    );

    button.classList.add("active");
    days = Number(button.dataset.days);

    await loadHistory();
  };
});

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("./sw.js");
}

sb.auth.onAuthStateChange(async () => {
  await authState();
});

load();
