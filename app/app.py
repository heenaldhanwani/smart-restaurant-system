"""Smart Restaurant Management System: Flask + SQLite.

Run:  python app/app.py     (listens on 0.0.0.0:5000)
Customer page: /     Admin page: /admin     Health check: /health
"""
import os
import re
import sqlite3
from datetime import datetime

from flask import (Flask, g, jsonify, redirect, render_template, request,
                   session, url_for)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE_DIR, "restaurant.db"))
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key")

STATUSES = ["Placed", "Preparing", "Ready", "Served", "Cancelled"]

SEED_MENU = [
    ("Paneer Tikka", "Starters", 220, 1, "Char-grilled cottage cheese with mint chutney"),
    ("Chicken 65", "Starters", 260, 0, "Spicy fried chicken with curry leaves"),
    ("Veg Spring Rolls", "Starters", 180, 1, "Crisp rolls filled with vegetables"),
    ("Butter Chicken", "Main Course", 340, 0, "Creamy tomato gravy with tandoori chicken"),
    ("Paneer Butter Masala", "Main Course", 300, 1, "Paneer in rich buttery tomato gravy"),
    ("Veg Biryani", "Main Course", 260, 1, "Fragrant basmati rice cooked with vegetables"),
    ("Chicken Biryani", "Main Course", 320, 0, "Dum-cooked basmati rice with chicken"),
    ("Butter Naan", "Breads", 50, 1, "Soft tandoor bread brushed with butter"),
    ("Gulab Jamun", "Desserts", 90, 1, "Warm milk dumplings in sugar syrup"),
    ("Chocolate Brownie", "Desserts", 140, 1, "Fudgy brownie with chocolate sauce"),
    ("Masala Chai", "Beverages", 40, 1, "Spiced Indian tea"),
    ("Fresh Lime Soda", "Beverages", 70, 1, "Sweet or salted lime soda"),
]

CATEGORY_WORDS = {
    "starter": "Starters", "appetizer": "Starters",
    "main": "Main Course", "bread": "Breads", "naan": "Breads",
    "dessert": "Desserts", "sweet": "Desserts",
    "drink": "Beverages", "beverage": "Beverages",
}


# ---------------------------------------------------------------- database
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS menu (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            price REAL NOT NULL,
            veg INTEGER NOT NULL DEFAULT 1,
            description TEXT DEFAULT '',
            available INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT NOT NULL,
            table_no TEXT NOT NULL,
            total REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'Placed',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL REFERENCES orders(id),
            menu_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            qty INTEGER NOT NULL
        );
        """
    )
    if db.execute("SELECT COUNT(*) FROM menu").fetchone()[0] == 0:
        db.executemany(
            "INSERT INTO menu (name, category, price, veg, description) VALUES (?,?,?,?,?)",
            SEED_MENU,
        )
    db.commit()
    db.close()


def rows(cursor):
    return [dict(r) for r in cursor.fetchall()]


def money(value):
    return "\u20b9{:g}".format(value)


# ---------------------------------------------------------- customer pages
@app.route("/health")
def health():
    return jsonify(status="ok")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/menu")
def api_menu():
    cur = get_db().execute(
        "SELECT id, name, category, price, veg, description FROM menu "
        "WHERE available = 1 ORDER BY category, name"
    )
    return jsonify(rows(cur))


@app.route("/api/orders", methods=["POST"])
def api_place_order():
    data = request.get_json(silent=True) or {}
    name = str(data.get("customer_name", "")).strip()
    table_no = str(data.get("table_no", "")).strip()
    items = data.get("items") or []
    if not name or not table_no:
        return jsonify(error="Enter your name and table number."), 400
    if not items:
        return jsonify(error="Your cart is empty."), 400

    db = get_db()
    lines, total = [], 0
    for entry in items:
        try:
            menu_id, qty = int(entry["id"]), int(entry["qty"])
        except (KeyError, TypeError, ValueError):
            return jsonify(error="Invalid cart item."), 400
        if qty < 1 or qty > 20:
            return jsonify(error="Quantity must be between 1 and 20."), 400
        item = db.execute(
            "SELECT * FROM menu WHERE id = ? AND available = 1", (menu_id,)
        ).fetchone()
        if item is None:
            return jsonify(error="An item in your cart is no longer available."), 400
        lines.append((item["id"], item["name"], item["price"], qty))
        total += item["price"] * qty

    cur = db.execute(
        "INSERT INTO orders (customer_name, table_no, total, created_at) VALUES (?,?,?,?)",
        (name, table_no, total, datetime.now().strftime("%Y-%m-%d %H:%M")),
    )
    order_id = cur.lastrowid
    db.executemany(
        "INSERT INTO order_items (order_id, menu_id, name, price, qty) VALUES (?,?,?,?,?)",
        [(order_id,) + line for line in lines],
    )
    db.commit()
    return jsonify(order_id=order_id, total=total, status="Placed"), 201


@app.route("/api/orders/<int:order_id>")
def api_order_status(order_id):
    db = get_db()
    order = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if order is None:
        return jsonify(error="Order not found."), 404
    items = rows(db.execute(
        "SELECT name, price, qty FROM order_items WHERE order_id = ?", (order_id,)))
    return jsonify(dict(order), items=items)


# ----------------------------------------------------------------- chatbot
def chatbot_reply(message):
    text = message.lower().strip()
    db = get_db()
    menu = rows(db.execute("SELECT * FROM menu WHERE available = 1"))

    if not text:
        return "Type a question, for example: show the menu."

    if re.search(r"\b(hi|hello|hey|namaste)\b", text):
        return ("Hello! I can show the menu, give prices, suggest dishes, "
                "or check an order. What would you like?")

    # Intent: order status ("status of order 5", "track #5")
    m = re.search(r"(?:order|#)\s*#?\s*(\d+)|(\d+)", text)
    if m and re.search(r"order|status|track|#", text):
        order_id = int(m.group(1) or m.group(2))
        order = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if order is None:
            return "I could not find order #{}. Check the number and try again.".format(order_id)
        return "Order #{} for {} (table {}) is {}. Total: {}.".format(
            order["id"], order["customer_name"], order["table_no"],
            order["status"], money(order["total"]))

    # Intent: details or price of one dish
    for item in menu:
        if item["name"].lower() in text:
            kind = "vegetarian" if item["veg"] else "non-vegetarian"
            return "{} costs {} ({}). {}.".format(
                item["name"], money(item["price"]), kind, item["description"].rstrip("."))

    # Intent: vegetarian / non-vegetarian
    if re.search(r"non[- ]?veg", text):
        names = [i["name"] for i in menu if not i["veg"]]
        return "Non-vegetarian dishes: " + ", ".join(names) + "." if names else "No non-vegetarian dishes today."
    if re.search(r"\bveg(etarian)?\b", text):
        names = [i["name"] for i in menu if i["veg"]]
        return "Vegetarian dishes: " + ", ".join(names) + "."

    # Intent: cheapest / budget
    if re.search(r"cheap|budget|lowest|affordable", text) and menu:
        item = min(menu, key=lambda i: i["price"])
        return "Our most affordable item is {} at {}.".format(item["name"], money(item["price"]))

    # Intent: category list
    for word, category in CATEGORY_WORDS.items():
        if word in text:
            items = [i for i in menu if i["category"] == category]
            if items:
                return "{}: {}.".format(category, ", ".join(
                    "{} ({})".format(i["name"], money(i["price"])) for i in items))

    # Intent: recommendation
    if re.search(r"recommend|suggest|popular|best|special", text):
        top = rows(db.execute(
            "SELECT name, SUM(qty) AS sold FROM order_items GROUP BY menu_id "
            "ORDER BY sold DESC LIMIT 3"))
        if top:
            return "Most ordered right now: " + ", ".join(t["name"] for t in top) + "."
        picks = [i["name"] for i in menu[:3]]
        return "Good choices to start with: " + ", ".join(picks) + "."

    # Intent: full menu
    if "menu" in text:
        cats = sorted({i["category"] for i in menu})
        return ("We serve " + ", ".join(cats) + ". Ask for a category, "
                "for example 'show desserts', or use the menu on this page.")

    # Intent: timings and ordering help
    if re.search(r"open|close|timing|hours", text):
        return "We are open every day from 11:00 AM to 11:00 PM."
    if re.search(r"how.*order|place.*order|cart", text):
        return "Add dishes to your cart, enter your name and table number, then press Place order."

    return ("Sorry, I did not understand that. Try: show the menu, "
            "price of butter chicken, vegetarian dishes, or status of order 1.")


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(silent=True) or {}
    return jsonify(reply=chatbot_reply(str(data.get("message", ""))))


# ------------------------------------------------------------------- admin
def admin_only(view):
    from functools import wraps

    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            if request.path.startswith("/api/"):
                return jsonify(error="Admin login required."), 401
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)

    return wrapper


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("admin"))
        error = "Wrong password."
    return render_template("admin.html", login=True, error=error)


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


@app.route("/admin")
@admin_only
def admin():
    return render_template("admin.html", login=False, error=None)


@app.route("/api/admin/stats")
@admin_only
def admin_stats():
    db = get_db()
    totals = db.execute(
        "SELECT COUNT(*) AS orders, COALESCE(SUM(total), 0) AS revenue "
        "FROM orders WHERE status != 'Cancelled'").fetchone()
    top = rows(db.execute(
        "SELECT name, SUM(qty) AS sold FROM order_items "
        "GROUP BY menu_id ORDER BY sold DESC LIMIT 5"))
    return jsonify(orders=totals["orders"], revenue=totals["revenue"], top_items=top)


@app.route("/api/admin/orders")
@admin_only
def admin_orders():
    db = get_db()
    orders = rows(db.execute("SELECT * FROM orders ORDER BY id DESC"))
    for order in orders:
        order["items"] = rows(db.execute(
            "SELECT name, qty FROM order_items WHERE order_id = ?", (order["id"],)))
    return jsonify(orders)


@app.route("/api/admin/orders/<int:order_id>/status", methods=["POST"])
@admin_only
def admin_set_status(order_id):
    status = (request.get_json(silent=True) or {}).get("status")
    if status not in STATUSES:
        return jsonify(error="Unknown status."), 400
    db = get_db()
    db.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
    db.commit()
    return jsonify(order_id=order_id, status=status)


@app.route("/api/admin/menu")
@admin_only
def admin_menu():
    return jsonify(rows(get_db().execute(
        "SELECT * FROM menu ORDER BY category, name")))


@app.route("/api/admin/menu", methods=["POST"])
@admin_only
def admin_add_item():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    category = str(data.get("category", "")).strip()
    try:
        price = float(data.get("price"))
    except (TypeError, ValueError):
        return jsonify(error="Enter a valid price."), 400
    if not name or not category or price <= 0:
        return jsonify(error="Name, category and a price above 0 are required."), 400
    db = get_db()
    db.execute(
        "INSERT INTO menu (name, category, price, veg, description) VALUES (?,?,?,?,?)",
        (name, category, price, 1 if data.get("veg", True) else 0,
         str(data.get("description", "")).strip()))
    db.commit()
    return jsonify(ok=True), 201


@app.route("/api/admin/menu/<int:item_id>/toggle", methods=["POST"])
@admin_only
def admin_toggle_item(item_id):
    db = get_db()
    db.execute("UPDATE menu SET available = 1 - available WHERE id = ?", (item_id,))
    db.commit()
    return jsonify(ok=True)


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
