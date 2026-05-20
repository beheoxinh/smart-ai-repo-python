const { invoke } = window.__TAURI__.core;

const navList = document.getElementById("nav-list");
const frame = document.getElementById("content-frame");
const statusLabel = document.getElementById("status-label");
const currentTitle = document.getElementById("current-title");
const addButton = document.getElementById("add-button");
const modal = document.getElementById("modal");
const cancelButton = document.getElementById("cancel-btn");
const form = document.getElementById("shortcut-form");
const refreshButton = document.getElementById("refresh-slot");
const openButton = document.getElementById("open-link");

let currentNav = null;

window.addEventListener("DOMContentLoaded", () => {
  bootstrap().catch((err) => {
    console.error(err);
    setStatus("Failed to load configuration.");
  });
});

async function bootstrap() {
  try {
    const [nav, saved] = await Promise.all([fetchNav(), fetchLastUrl()]);
    renderNav(nav, saved.url);
    setStatus("Shortcuts are ready.");
  } catch (err) {
    console.error(err);
    setStatus("Failed to load configuration.");
  }
}

async function fetchNav() {
  try {
    return await invoke("read_nav_config");
  } catch (err) {
    throw new Error("cannot read nav data: " + err);
  }
}

async function fetchLastUrl() {
  const res = await fetch("/api/last-url");
  if (!res.ok) {
    return { url: "" };
  }
  return res.json();
}

function renderNav(items, preferredUrl) {
  currentNav = null;
  navList.innerHTML = "";
  if (!items.length) {
    navList.innerHTML = "<p class='hint'>No shortcuts yet.</p>";
    return;
  }

  items.forEach((item) => {
    const btn = document.createElement("button");
    btn.className = "nav-button";
    btn.setAttribute("role", "menuitem");
    btn.innerHTML = `<img src="/assets/${item.icon}" alt="${item.tooltip}" /><strong>${item.tooltip}</strong>`;
    btn.addEventListener("click", () => selectItem(item, btn));
    navList.appendChild(btn);

    if (preferredUrl && preferredUrl === item.url && !currentNav) {
      setActive(btn, item);
    }
  });

  if (!currentNav) {
    const first = navList.querySelector(".nav-button");
    if (first) {
      const firstItem = items[0];
      setActive(first, firstItem);
    }
  }
}

async function selectItem(item, element) {
  if (!item || !element) {
    return;
  }
  setActive(element, item);
  try {
    await persistLastUrl(item.url);
  } catch (err) {
    console.warn("persist failure", err);
    setStatus("Could not persist last visited page.");
  }
}

function setActive(buttonEl, item) {
  navList.querySelectorAll(".nav-button").forEach((node) => node.classList.remove("selected"));
  buttonEl.classList.add("selected");
  currentNav = item;
  currentTitle.textContent = item.tooltip;
  frame.src = item.url;
  setStatus(`Loaded ${item.tooltip}`);
}

async function persistLastUrl(url) {
  await fetch("/api/last-url", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
}

function setStatus(message) {
  statusLabel.textContent = message;
}

addButton.addEventListener("click", () => {
  modal.classList.remove("hidden");
});

cancelButton.addEventListener("click", () => {
  modal.classList.add("hidden");
});

modal.addEventListener("click", (event) => {
  if (event.target === modal) {
    modal.classList.add("hidden");
  }
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = new FormData(form);
  const payload = {
    tooltip: data.get("tooltip").trim(),
    url: data.get("url").trim(),
    icon: data.get("icon").trim(),
    pinned: data.get("pinned") === "on",
    order: Number(data.get("order")) || 0,
  };

  try {
    const res = await fetch("/api/nav", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      setStatus("Saving failed.");
      return;
    }

    const items = await res.json();
    renderNav(items, payload.url);
    modal.classList.add("hidden");
    form.reset();
    setStatus("Shortcut saved locally.");
  } catch (err) {
    console.error(err);
    setStatus("Could not save the shortcut.");
  }
});

refreshButton.addEventListener("click", () => {
  if (!frame.src) {
    return;
  }
  try {
    frame.contentWindow.location.reload();
  } catch (error) {
    const current = frame.getAttribute("src") || "";
    frame.setAttribute("src", current);
  }
});

openButton.addEventListener("click", () => {
  if (currentNav?.url) {
    window.open(currentNav.url, "_blank");
  }
});
