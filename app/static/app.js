const $ = (id) => document.getElementById(id);
const rupee = (n) => "\u20b9" + Number(n).toLocaleString("en-IN");
let menu = [];
let category = "All";
const cart = new Map(); // menu id -> quantity

function el(tag, text, cls) {
  const e = document.createElement(tag);
  if (text !== undefined) e.textContent = text;
  if (cls) e.className = cls;
  return e;
}

async function loadMenu() {
  const res = await fetch("/api/menu");
  menu = await res.json();
  renderFilters();
  renderMenu();
}

function renderFilters() {
  const box = $("filters");
  box.replaceChildren();
  ["All", ...new Set(menu.map((m) => m.category))].forEach((c) => {
    const b = el("button", c);
    b.setAttribute("aria-pressed", String(c === category));
    b.onclick = () => { category = c; renderFilters(); renderMenu(); };
    box.append(b);
  });
}

function renderMenu() {
  const box = $("menu");
  box.replaceChildren();
  menu.filter((m) => category === "All" || m.category === category).forEach((m) => {
    const card = el("div", undefined, "dish");
    const info = el("div");
    const title = el("h3");
    title.append(el("span", undefined, "dot" + (m.veg ? "" : " nonveg")), m.name);
    info.append(title, el("p", m.description));
    const side = el("div");
    side.append(el("span", rupee(m.price), "price"), " ");
    const add = el("button", "Add", "add");
    add.setAttribute("aria-label", "Add " + m.name + " to order");
    add.onclick = () => { cart.set(m.id, (cart.get(m.id) || 0) + 1); renderCart(); };
    side.append(add);
    card.append(info, side);
    box.append(card);
  });
}

function renderCart() {
  const list = $("cart-items");
  list.replaceChildren();
  let total = 0;
  cart.forEach((qty, id) => {
    const item = menu.find((m) => m.id === id);
    if (!item) return;
    total += item.price * qty;
    const li = el("li");
    li.append(el("span", item.name));
    const q = el("span", undefined, "qty");
    const minus = el("button", "-"); minus.setAttribute("aria-label", "Remove one " + item.name);
    const plus = el("button", "+"); plus.setAttribute("aria-label", "Add one " + item.name);
    minus.onclick = () => { qty > 1 ? cart.set(id, qty - 1) : cart.delete(id); renderCart(); };
    plus.onclick = () => { cart.set(id, qty + 1); renderCart(); };
    q.append(minus, " " + qty + " ", plus);
    li.append(q);
    list.append(li);
  });
  if (!cart.size) list.append(el("li", "Your cart is empty."));
  $("cart-total").textContent = rupee(total);
}

$("place-order").onclick = async () => {
  const msg = $("order-msg");
  msg.className = "msg";
  const body = {
    customer_name: $("cust-name").value,
    table_no: $("table-no").value,
    items: [...cart].map(([id, qty]) => ({id, qty})),
  };
  const res = await fetch("/api/orders", {
    method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) { msg.className = "msg err"; msg.textContent = data.error; return; }
  msg.textContent = "Order #" + data.order_id + " placed. Total " + rupee(data.total) + ".";
  cart.clear();
  renderCart();
};

// ---- chatbot
function bubble(text, who) {
  const b = el("div", text, "bubble " + who);
  $("chat-log").append(b);
  $("chat-log").scrollTop = $("chat-log").scrollHeight;
}

$("chat-toggle").onclick = () => {
  const panel = $("chat");
  panel.hidden = !panel.hidden;
  $("chat-toggle").setAttribute("aria-expanded", String(!panel.hidden));
  if (!panel.hidden && !$("chat-log").children.length) {
    bubble("Hi! Ask me about the menu, prices, vegetarian dishes or an order status.", "bot");
  }
};

$("chat-form").onsubmit = async (e) => {
  e.preventDefault();
  const text = $("chat-input").value.trim();
  if (!text) return;
  bubble(text, "me");
  $("chat-input").value = "";
  const res = await fetch("/api/chat", {
    method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({message: text}),
  });
  bubble((await res.json()).reply, "bot");
};

loadMenu();
renderCart();
