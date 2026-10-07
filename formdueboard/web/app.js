const boardEl = document.querySelector("#board");
const reviewEl = document.querySelector("#review");
const reviewCards = document.querySelector("#review-cards");
const statusEl = document.querySelector("#status");
const footEl = document.querySelector("#foot");
const gmailButton = document.querySelector("#gmail");

const pins = ["red", "gold", "blue", "red"];

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function setStatus(text) {
  statusEl.textContent = text || "";
}

async function loadBoard() {
  const response = await fetch("/api/board");
  if (!response.ok) {
    setStatus("The board could not be loaded.");
    return;
  }
  render(await response.json());
}

function render(board) {
  boardEl.replaceChildren();
  gmailButton.hidden = !board.gmail_enabled;
  const counts = board.counts || {};
  footEl.textContent =
    `Inbox folder: ${board.inbox_dir}. ` +
    `${counts.todo || 0} to do, ${counts.due_soon || 0} due soon, ` +
    `${counts.overdue || 0} overdue, ${counts.review || 0} to review. ` +
    "Mail stays on this computer.";

  board.kids.forEach((kid, index) => {
    const column = el("section", "column");
    column.append(el("div", index % 2 === 0 ? "ribbon blue" : "ribbon red", `★ ${kid.name}`));
    if (!kid.items.length) {
      column.append(el("p", "empty", "Nothing filed yet. Drop a .eml or .mbox file into the inbox and scan."));
    }
    kid.items.forEach((item, itemIndex) => column.append(card(item, itemIndex, board.kids)));
    boardEl.append(column);
  });

  reviewCards.replaceChildren();
  if (!board.review.length) {
    reviewEl.hidden = true;
    return;
  }
  reviewEl.hidden = false;
  board.review.forEach((item) => reviewCards.append(reviewCard(item, board.kids)));
}

function card(item, index) {
  const node = el("article", `card ${item.highlight}`);
  node.append(el("div", `pin ${pins[index % pins.length]}`));
  const kicker = el("div", "kicker");
  kicker.append(el("span", null, item.form_label));
  if (item.attachments && item.attachments.length) {
    kicker.append(el("span", null, "clip"));
  }
  node.append(kicker);
  node.append(el("h3", null, item.title));
  if (item.snippet) node.append(el("p", "snippet", item.snippet));
  if (item.due_display) {
    const label =
      item.highlight === "overdue"
        ? `Overdue: ${item.due_display}`
        : item.highlight === "due_soon"
          ? `Due soon: ${item.due_display}`
          : `Due: ${item.due_display}`;
    node.append(el("div", "due-badge", label));
  } else if (item.cancelled) {
    node.append(el("div", "due-badge", "Cancelled"));
  }
  const meta = el("p", "meta");
  if (item.sender) meta.append(el("span", null, item.sender));
  if (item.event_display) {
    meta.append(el("span", null, meta.childNodes.length ? ` · Event ${item.event_display}` : `Event ${item.event_display}`));
  }
  if (item.fee_amount) {
    meta.append(el("span", null, ` · $${item.fee_amount}`));
  }
  if (item.gmail_url) {
    const link = el("a", null, " Open email");
    link.href = item.gmail_url;
    link.target = "_blank";
    link.rel = "noopener";
    meta.append(link);
  } else if (item.source_name) {
    meta.append(el("span", null, meta.childNodes.length ? ` · ${item.source_name}` : item.source_name));
  }
  node.append(meta);
  if (item.attachments && item.attachments.length) {
    const chips = el("div", "chips");
    item.attachments.forEach((attachment) => chips.append(el("span", "chip", attachment.filename)));
    node.append(chips);
  }
  node.append(statusButtons(item));
  const done = el("button", "done", "Mark done");
  done.type = "button";
  done.disabled = item.status === "returned";
  done.addEventListener("click", () => post(`/api/items/${item.id}/done`, {}));
  node.append(done);
  return node;
}

function statusButtons(item) {
  const row = el("div", "statuses");
  [
    ["todo", "To do"],
    ["signed", "Signed"],
    ["returned", "Returned"],
  ].forEach(([value, label]) => {
    const button = el("button", null, label);
    button.type = "button";
    button.setAttribute("aria-pressed", item.status === value ? "true" : "false");
    button.addEventListener("click", () => post(`/api/items/${item.id}/status`, { status: value }));
    row.append(button);
  });
  return row;
}

function reviewCard(item, kids) {
  const node = el("article", "review-card");
  node.append(el("div", "kicker", item.form_label));
  node.append(el("h3", null, item.title));
  if (item.due_display) node.append(el("div", "due-badge", `Due: ${item.due_display}`));
  node.append(el("p", "reason", item.review_reason || "Needs a look before it is filed."));
  if (item.snippet) node.append(el("p", "snippet", item.snippet));
  const actions = el("div", "assign");
  kids.forEach((kid) => {
    const button = el("button", null, `File under ${kid.name}`);
    button.type = "button";
    if (item.suggested_kid === kid.name) button.textContent = `File under ${kid.name} (suggested)`;
    button.addEventListener("click", () => post(`/api/items/${item.id}/assign`, { kid_name: kid.name }));
    actions.append(button);
  });
  node.append(actions);
  return node;
}

async function post(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    setStatus(payload.error || "That did not work.");
    return;
  }
  if (payload.created != null) {
    setStatus(`Scan finished. ${payload.created} new, ${payload.updated} updated, ${payload.duplicates} duplicates.`);
  } else if (payload.status) {
    setStatus(payload.status === "returned" ? "Marked done." : "Status saved.");
  } else if (payload.kid_name) {
    setStatus(`Filed under ${payload.kid_name}.`);
  }
  await loadBoard();
}

document.querySelector("#scan").addEventListener("click", () => post("/api/scan", {}));
document.querySelector("#samples").addEventListener("click", () => post("/api/samples", {}));
gmailButton.addEventListener("click", () => post("/api/gmail/fetch", {}));
document.querySelector("#files").addEventListener("change", async (event) => {
  const files = event.target.files;
  if (!files || !files.length) return;
  const data = new FormData();
  for (const file of files) data.append("file", file, file.name);
  const response = await fetch("/api/upload", { method: "POST", body: data });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    setStatus(payload.error || "Upload failed.");
  } else {
    setStatus(`Added ${payload.saved || 0} file(s). ${payload.created || 0} new forms.`);
  }
  event.target.value = "";
  await loadBoard();
});

loadBoard().catch(() => setStatus("The board could not be loaded."));
