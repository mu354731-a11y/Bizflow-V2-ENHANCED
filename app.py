
import io
from datetime import date, datetime
from urllib.parse import quote

import pandas as pd
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from database import init_db, query, execute
from auth import (
    signup, login, hash_password,
    create_login_session, get_session_user, revoke_login_session,
)
from streamlit_cookies_manager import EncryptedCookieManager

init_db()

st.set_page_config(
    page_title="BizFlow V2",
    page_icon="🌊",
    layout="wide"
)

# ---------------- Persistent login cookie ----------------
cookie_password = st.secrets.get("COOKIE_PASSWORD", "")
if not cookie_password:
    st.error("COOKIE_PASSWORD is missing from Streamlit Secrets.")
    st.stop()

cookies = EncryptedCookieManager(
    prefix="bizflow/",
    password=cookie_password,
)

# The cookie manager needs a browser round-trip before cookies are available.
if not cookies.ready():
    st.stop()

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&family=Manrope:wght@600;700;800&display=swap');
html, body, [class*="css"] {font-family:'DM Sans',sans-serif}
.stApp {background:linear-gradient(135deg,#f7f9fc,#edf4ff)}
.block-container {max-width:1400px;padding-top:1.5rem}
[data-testid="stSidebar"] {background:#101b35}
[data-testid="stSidebar"] * {color:#edf4ff}
.hero {background:linear-gradient(120deg,#101b35,#20518a 68%,#168b91);
color:white;padding:26px 30px;border-radius:22px;margin-bottom:22px}
.hero h1 {font-family:Manrope,sans-serif;font-size:2.2rem;margin:0}
.hero p {color:#dbeafe;margin:.4rem 0 0}
.metric {background:white;border:1px solid #e2e9f3;border-radius:16px;
padding:17px;min-height:100px}
.metric-label {color:#64748b;font-size:.78rem;font-weight:700}
.metric-value {font-family:Manrope,sans-serif;font-size:1.35rem;
font-weight:800;color:#14213d;margin-top:8px}
.stButton>button,.stDownloadButton>button {border-radius:10px;font-weight:700}
</style>
""", unsafe_allow_html=True)


# ---------------- Shared helpers ----------------

def get_business(bid):
    result = query(
        "SELECT * FROM businesses WHERE id=:b",
        {"b": bid}
    )
    return result[0] if result else None


def get_rows(table, business_id, order_by="id DESC"):
    allowed = {
        "customers", "products", "invoices", "expenses",
        "payments", "users", "invoice_items"
    }
    if table not in allowed:
        raise ValueError("Unsupported table")

    return query(
        f"SELECT * FROM {table} WHERE business_id=:b ORDER BY {order_by}",
        {"b": business_id}
    )


def money(value, business):
    return f'{business["currency"]} {float(value or 0):,.2f}'


def invoice_status(total, paid):
    if paid >= total - 0.005:
        return "Paid"
    if paid > 0:
        return "Partial"
    return "Unpaid"


def admin(user):
    return user["role"] in ("owner", "admin")


def finance(user):
    return user["role"] in ("owner", "admin", "cashier")


def create_invoice_pdf(invoice, business, items):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm
    )

    styles = getSampleStyleSheet()
    story = [
        Paragraph(business["name"], styles["Title"]),
        Paragraph(business.get("address") or "", styles["Normal"]),
        Paragraph(
            " · ".join(
                x for x in [
                    business.get("phone") or "",
                    business.get("email") or "",
                    ("Tax ID: " + business["tax_id"])
                    if business.get("tax_id") else ""
                ] if x
            ),
            styles["Normal"]
        ),
        Spacer(1, 12),
        Paragraph(f'INVOICE: {invoice["number"]}', styles["Heading2"]),
        Paragraph(f'Date: {invoice["invoice_date"]}', styles["Normal"]),
        Paragraph(f'Customer: {invoice["customer_name"]}', styles["Normal"]),
        Paragraph(f'Phone: {invoice["phone"] or "—"}', styles["Normal"]),
        Spacer(1, 14)
    ]

    data = [["Description", "Qty", "Unit price", "Amount"]]
    for item in items:
        data.append([
            item["description"],
            str(item["quantity"]),
            money(item["unit_price"], business),
            money(item["line_total"], business)
        ])

    table = Table(data, colWidths=[78*mm, 20*mm, 35*mm, 35*mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#173a70")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d9e2ef")),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
    ]))
    story.extend([table, Spacer(1, 14)])

    totals = [
        ["Subtotal", money(invoice["subtotal"], business)],
        ["Discount", money(invoice["discount"], business)],
        ["Total", money(invoice["total"], business)],
        ["Paid", money(invoice["paid"], business)],
        ["Balance due", money(max(0, invoice["total"] - invoice["paid"]), business)],
        ["Status", invoice["status"]]
    ]
    summary = Table(totals, colWidths=[120*mm, 53*mm], hAlign="RIGHT")
    summary.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d9e2ef")),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.extend([summary, Spacer(1, 18)])
    if invoice.get("notes"):
        story.append(Paragraph("Notes: " + invoice["notes"], styles["Normal"]))
    story.append(Spacer(1, 10))
    story.append(Paragraph("Thank you for your business!", styles["Normal"]))

    doc.build(story)
    return buffer.getvalue()


# ---------------- Login and signup ----------------

if "user" not in st.session_state:
    st.session_state.user = None

# Restore the logged-in user from the browser cookie when Streamlit's
# in-memory session is new or has been restarted.
if not st.session_state.user:
    saved_token = cookies.get("bizflow_session", "")
    if saved_token:
        restored_user = get_session_user(saved_token)
        if restored_user:
            st.session_state.user = restored_user
        else:
            # Remove an expired or invalid token from this browser.
            cookies["bizflow_session"] = ""
            cookies.save()

if not st.session_state.user:
    st.markdown("""
    <div class="hero">
      <h1>🌊 BizFlow <span style="color:#72e0d2">V2</span></h1>
      <p>Your business. Your data. One simple workspace.</p>
    </div>
    """, unsafe_allow_html=True)

    login_tab, signup_tab = st.tabs(["Sign in", "Create account"])

    with login_tab:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button(
                "Sign in", type="primary", use_container_width=True
            )

        if submitted:
            user = login(username, password)
            if user:
                token = create_login_session(user["id"])
                cookies["bizflow_session"] = token
                cookies.save()
                st.session_state.user = user
                st.rerun()
            else:
                st.error("Login failed. Check your details or account status.")

    with signup_tab:
        with st.form("signup_form"):
            business_name = st.text_input("Business name")
            full_name = st.text_input("Your full name")
            username = st.text_input("Choose a username")
            password = st.text_input(
                "Password (minimum 10 characters)", type="password"
            )
            confirm = st.text_input("Confirm password", type="password")
            currency = st.selectbox(
                "Currency", ["PKR", "USD", "GBP", "AED", "SAR", "EUR", "INR"]
            )
            submitted = st.form_submit_button(
                "Create private workspace",
                type="primary",
                use_container_width=True
            )

        if submitted:
            if password != confirm:
                st.error("Passwords do not match.")
            else:
                try:
                    signup(
                        business_name, full_name, username, password, currency
                    )
                    st.success("Account created! Now sign in.")
                except ValueError as error:
                    st.error(str(error))
                except Exception:
                    st.error("Could not create the account. Try another username.")

    st.stop()


# ---------------- Authenticated workspace ----------------

user = st.session_state.user
business_id = int(user["business_id"])
business = get_business(business_id)

if not business:
    st.error("Business workspace not found.")
    st.stop()

with st.sidebar:
    st.markdown("## 🌊 BizFlow")
    st.caption("BUSINESS WORKSPACE")
    st.markdown(f'**{business["name"]}**')
    st.caption(f'{user["full_name"]} · {user["role"].title()}')

    page = st.radio(
        "Navigate",
        [
            "Overview", "Invoices", "Products & stock", "Customers",
            "Expenses", "Analytics", "Business profile", "Staff & access"
        ]
    )

    if st.button("Sign out", use_container_width=True):
        token = cookies.get("bizflow_session", "")
        if token:
            revoke_login_session(token)

        cookies["bizflow_session"] = ""
        cookies.save()
        st.session_state.user = None
        st.rerun()

st.markdown(
    f'<div class="hero"><h1>BizFlow V2</h1>'
    f'<p>Welcome back, {user["full_name"]}. Manage your business with clarity.</p>'
    f'</div>',
    unsafe_allow_html=True
)


# ---------------- Overview ----------------

if page == "Overview":
    invoices = get_rows("invoices", business_id)
    expenses = get_rows("expenses", business_id)
    products = get_rows("products", business_id)

    sales = sum(x["total"] for x in invoices)
    collected = sum(x["paid"] for x in invoices)
    outstanding = sum(max(0, x["total"] - x["paid"]) for x in invoices)
    expense_total = sum(x["amount"] for x in expenses)

    cards = [
        ("INVOICED SALES", money(sales, business)),
        ("PAYMENTS RECEIVED", money(collected, business)),
        ("OUTSTANDING", money(outstanding, business)),
        ("CASH FLOW", money(collected - expense_total, business))
    ]

    columns = st.columns(4)
    for col, (label, value) in zip(columns, cards):
        with col:
            st.markdown(
                f'<div class="metric"><div class="metric-label">{label}</div>'
                f'<div class="metric-value">{value}</div></div>',
                unsafe_allow_html=True
            )

    st.subheader("Recent invoices")
    if invoices:
        st.dataframe(
            pd.DataFrame(invoices).drop(
                columns=["business_id", "created_by"], errors="ignore"
            ).head(10),
            hide_index=True,
            use_container_width=True
        )
    else:
        st.info("Create your first invoice to see activity here.")

    low_stock = [
        p for p in products if p["stock"] <= p["low_stock_limit"]
    ]
    st.subheader("Low-stock alerts")
    if low_stock:
        st.warning(", ".join(
            f'{p["name"]} ({p["stock"]} left)' for p in low_stock
        ))
    else:
        st.success("No low-stock alerts.")

    st.caption(
        "Cash flow here means recorded invoice payments minus recorded expenses. "
        "It is not the same as accounting profit."
    )


# ---------------- Customers ----------------

elif page == "Customers":
    if not finance(user):
        st.error("Your role cannot manage customers.")
        st.stop()

    with st.form("customer_form", clear_on_submit=True):
        name = st.text_input("Customer / business name")
        phone = st.text_input("Phone number")
        email = st.text_input("Email")
        address = st.text_area("Address")
        submitted = st.form_submit_button("Add customer", type="primary")

    if submitted:
        if not name.strip():
            st.error("Customer name is required.")
        else:
            execute("""
                INSERT INTO customers
                (business_id,name,phone,email,address,created_at)
                VALUES (:b,:n,:p,:e,:a,:t)
            """, {
                "b": business_id, "n": name.strip(), "p": phone,
                "e": email, "a": address,
                "t": datetime.now().isoformat()
            })
            st.success("Customer added.")
            st.rerun()

    customers = get_rows("customers", business_id, "name ASC")
    if customers:
        st.dataframe(pd.DataFrame(customers).drop(
            columns=["business_id"], errors="ignore"
        ), hide_index=True, use_container_width=True)
        st.download_button(
            "Export customers CSV",
            pd.DataFrame(customers).to_csv(index=False).encode(),
            "bizflow_customers.csv",
            "text/csv"
        )


# ---------------- Products and inventory ----------------

elif page == "Products & stock":
    if not admin(user):
        st.error("Only owners and admins can manage inventory.")
        st.stop()

    with st.form("product_form", clear_on_submit=True):
        name = st.text_input("Product name")
        sku = st.text_input("SKU")
        col1, col2 = st.columns(2)
        with col1:
            price = st.number_input("Selling price", min_value=0.0)
            cost = st.number_input("Unit cost", min_value=0.0)
        with col2:
            stock = st.number_input("Opening stock", min_value=0, step=1)
            limit = st.number_input("Low-stock threshold", min_value=0, value=5)
        submitted = st.form_submit_button("Add product", type="primary")

    if submitted:
        if not name.strip():
            st.error("Product name is required.")
        else:
            execute("""
                INSERT INTO products
                (business_id,name,sku,price,cost,stock,low_stock_limit)
                VALUES (:b,:n,:s,:p,:c,:q,:l)
            """, {
                "b": business_id, "n": name.strip(), "s": sku,
                "p": price, "c": cost, "q": stock, "l": limit
            })
            st.success("Product added.")
            st.rerun()

    products = get_rows("products", business_id, "name ASC")
    if products:
        st.dataframe(pd.DataFrame(products).drop(
            columns=["business_id"], errors="ignore"
        ), hide_index=True, use_container_width=True)

        options = {
            f'{p["name"]} — stock: {p["stock"]}': p for p in products
        }
        with st.form("stock_adjustment"):
            selected_label = st.selectbox("Product to adjust", list(options))
            delta = st.number_input(
                "Stock change (+ restock, - correction)",
                min_value=-100000, max_value=100000, value=1
            )
            submitted = st.form_submit_button("Save stock adjustment")

        if submitted:
            p = options[selected_label]
            new_stock = p["stock"] + int(delta)
            if new_stock < 0:
                st.error("Stock cannot be negative.")
            else:
                execute("""
                    UPDATE products SET stock=:stock
                    WHERE id=:id AND business_id=:b
                """, {"stock": new_stock, "id": p["id"], "b": business_id})
                st.rerun()

        low_stock = [p for p in products if p["stock"] <= p["low_stock_limit"]]
        if low_stock:
            st.warning("Low stock: " + ", ".join(p["name"] for p in low_stock))


# ---------------- Invoices and payments ----------------

elif page == "Invoices":
    if not finance(user):
        st.error("Your role cannot access invoices.")
        st.stop()

    customers = get_rows("customers", business_id, "name ASC")
    products = get_rows("products", business_id, "name ASC")
    create_tab, register_tab = st.tabs(["Create invoice", "Invoice register"])

    with create_tab:
        with st.form("invoice_form", clear_on_submit=True):
            customer_options = {
                f'{c["name"]} — {c["phone"] or "no phone"}': c
                for c in customers
            }
            customer_choice = None
            if customer_options:
                customer_choice = st.selectbox(
                    "Saved customer (optional)", ["One-time customer"] +
                    list(customer_options)
                )
            else:
                customer_choice = "One-time customer"

            if customer_choice != "One-time customer":
                c = customer_options[customer_choice]
                customer_name = c["name"]
                phone = c["phone"]
            else:
                customer_name = st.text_input("Customer name")
                phone = st.text_input("Customer phone")

            description = st.text_input("Item description")
            matching_product = next(
                (p for p in products
                 if p["name"].strip().lower() == description.strip().lower()),
                None
            )

            col1, col2 = st.columns(2)
            with col1:
                quantity = st.number_input("Quantity", min_value=0.01, value=1.0)
                price = st.number_input(
                    "Unit price",
                    min_value=0.0,
                    value=float(matching_product["price"]) if matching_product else 0.0
                )
            with col2:
                discount = st.number_input("Discount", min_value=0.0)
                initial_paid = st.number_input("Payment received", min_value=0.0)

            invoice_date = st.date_input("Invoice date", date.today())
            due_date = st.date_input("Due date", date.today())
            notes = st.text_input("Notes")
            deduct_stock = st.checkbox(
                "Deduct stock if description matches a product"
            )
            submitted = st.form_submit_button("Create invoice", type="primary")

        if submitted:
            subtotal = round(quantity * price, 2)
            total = round(subtotal - discount, 2)

            if not customer_name.strip() or not description.strip():
                st.error("Customer and item description are required.")
            elif discount > subtotal:
                st.error("Discount cannot exceed subtotal.")
            elif initial_paid > total:
                st.error("Payment cannot exceed the invoice total.")
            elif deduct_stock and matching_product and matching_product["stock"] < quantity:
                st.error("Not enough stock. Adjust stock before creating this invoice.")
            else:
                number = "BF-" + datetime.now().strftime("%Y%m%d%H%M%S%f")
                customer_id = (
                    c["id"] if customer_choice != "One-time customer" else None
                )
                execute("""
                    INSERT INTO invoices
                    (business_id,number,customer_id,customer_name,phone,
                     invoice_date,due_date,subtotal,discount,total,paid,
                     status,notes,created_by,created_at)
                    VALUES (:b,:n,:cid,:cn,:ph,:d,:due,:s,:disc,:t,:paid,
                            :status,:notes,:uid,:created)
                """, {
                    "b": business_id, "n": number, "cid": customer_id,
                    "cn": customer_name.strip(), "ph": phone,
                    "d": str(invoice_date), "due": str(due_date),
                    "s": subtotal, "disc": discount, "t": total,
                    "paid": initial_paid, "status": invoice_status(total, initial_paid),
                    "notes": notes, "uid": user["id"],
                    "created": datetime.now().isoformat()
                })

                saved = query(
                    "SELECT id FROM invoices WHERE business_id=:b AND number=:n",
                    {"b": business_id, "n": number}
                )
                invoice_id = saved[0]["id"]

                execute("""
                    INSERT INTO invoice_items
                    (business_id,invoice_id,product_id,description,quantity,
                     unit_price,unit_cost,line_total)
                    VALUES (:b,:i,:pid,:d,:q,:p,:c,:total)
                """, {
                    "b": business_id, "i": invoice_id,
                    "pid": matching_product["id"] if matching_product else None,
                    "d": description.strip(), "q": quantity, "p": price,
                    "c": matching_product["cost"] if matching_product else 0,
                    "total": subtotal
                })

                if initial_paid:
                    execute("""
                        INSERT INTO payments
                        (business_id,invoice_id,amount,payment_date,method,created_by)
                        VALUES (:b,:i,:a,:d,:m,:u)
                    """, {
                        "b": business_id, "i": invoice_id,
                        "a": initial_paid, "d": str(invoice_date),
                        "m": "Cash", "u": user["id"]
                    })

                if deduct_stock and matching_product:
                    execute("""
                        UPDATE products SET stock=stock-:q
                        WHERE id=:pid AND business_id=:b
                    """, {
                        "q": int(quantity), "pid": matching_product["id"],
                        "b": business_id
                    })

                st.success(f"Invoice {number} created.")
                st.rerun()

    with register_tab:
        invoices = get_rows("invoices", business_id)
        if not invoices:
            st.info("No invoices yet.")
        else:
            st.dataframe(pd.DataFrame(invoices).drop(
                columns=["business_id", "created_by"], errors="ignore"
            ), hide_index=True, use_container_width=True)

            choices = {
                f'{i["number"]} — {i["customer_name"]}': i for i in invoices
            }
            selected = choices[st.selectbox("Select invoice", list(choices))]

            items = query("""
                SELECT * FROM invoice_items
                WHERE business_id=:b AND invoice_id=:i
            """, {"b": business_id, "i": selected["id"]})

            pdf = create_invoice_pdf(selected, business, items)
            st.download_button(
                "Download invoice PDF", pdf,
                f'{selected["number"]}.pdf', "application/pdf"
            )

            balance = max(0, selected["total"] - selected["paid"])
            st.metric("Balance due", money(balance, business))

            with st.form("payment_form"):
                amount = st.number_input(
                    "Payment amount", min_value=0.01, value=max(0.01, min(balance, 100.0))
                )
                payment_date = st.date_input("Payment date", date.today())
                method = st.selectbox(
                    "Method", ["Cash", "Bank transfer", "Card", "Mobile wallet", "Other"]
                )
                reference = st.text_input("Transaction reference")
                submitted = st.form_submit_button("Record payment")

            if submitted:
                if amount > balance + 0.005:
                    st.error("Payment exceeds the remaining balance.")
                else:
                    new_paid = selected["paid"] + amount
                    execute("""
                        INSERT INTO payments
                        (business_id,invoice_id,amount,payment_date,method,reference,created_by)
                        VALUES (:b,:i,:a,:d,:m,:r,:u)
                    """, {
                        "b": business_id, "i": selected["id"], "a": amount,
                        "d": str(payment_date), "m": method,
                        "r": reference, "u": user["id"]
                    })
                    execute("""
                        UPDATE invoices SET paid=:p,status=:s
                        WHERE id=:i AND business_id=:b
                    """, {
                        "p": new_paid, "s": invoice_status(selected["total"], new_paid),
                        "i": selected["id"], "b": business_id
                    })
                    st.success("Payment recorded.")
                    st.rerun()

            phone_digits = "".join(
                ch for ch in (selected["phone"] or "") if ch.isdigit()
            )
            message = (
                f'Hello {selected["customer_name"]}, invoice '
                f'{selected["number"]} from {business["name"]} totals '
                f'{money(selected["total"], business)}. Balance due: '
                f'{money(balance, business)}. Thank you.'
            )
            if phone_digits:
                st.link_button(
                    "Share invoice reminder on WhatsApp",
                    f"https://wa.me/{phone_digits}?text={quote(message)}"
                )


# ---------------- Expenses ----------------

elif page == "Expenses":
    if not finance(user):
        st.error("Your role cannot access expenses.")
        st.stop()

    with st.form("expense_form", clear_on_submit=True):
        category = st.selectbox(
            "Category",
            ["Stock / purchases", "Rent", "Salaries", "Utilities",
             "Transport", "Marketing", "Repairs", "Internet", "Other"]
        )
        description = st.text_input("Description")
        amount = st.number_input("Amount", min_value=0.01, value=100.0)
        expense_date = st.date_input("Expense date", date.today())
        method = st.selectbox(
            "Payment method", ["Cash", "Bank transfer", "Card", "Mobile wallet", "Other"]
        )
        submitted = st.form_submit_button("Save expense", type="primary")

    if submitted:
        execute("""
            INSERT INTO expenses
            (business_id,category,description,amount,expense_date,method,created_by)
            VALUES (:b,:c,:d,:a,:dt,:m,:u)
        """, {
            "b": business_id, "c": category, "d": description,
            "a": amount, "dt": str(expense_date),
            "m": method, "u": user["id"]
        })
        st.success("Expense saved.")
        st.rerun()

    expenses = get_rows("expenses", business_id, "expense_date DESC")
    if expenses:
        st.dataframe(pd.DataFrame(expenses).drop(
            columns=["business_id", "created_by"], errors="ignore"
        ), hide_index=True, use_container_width=True)
        st.download_button(
            "Export expenses CSV",
            pd.DataFrame(expenses).to_csv(index=False).encode(),
            "bizflow_expenses.csv",
            "text/csv"
        )


# ---------------- Analytics ----------------

elif page == "Analytics":
    st.subheader("Business performance")

    start = st.date_input("From", date.today().replace(day=1))
    end = st.date_input("To", date.today())

    if start > end:
        st.error("Start date must be on or before end date.")
        st.stop()

    invoices = query("""
        SELECT * FROM invoices
        WHERE business_id=:b AND invoice_date BETWEEN :s AND :e
    """, {"b": business_id, "s": str(start), "e": str(end)})

    expenses = query("""
        SELECT * FROM expenses
        WHERE business_id=:b AND expense_date BETWEEN :s AND :e
    """, {"b": business_id, "s": str(start), "e": str(end)})

    items = query("""
        SELECT ii.* FROM invoice_items ii
        JOIN invoices i ON i.id=ii.invoice_id AND i.business_id=ii.business_id
        WHERE ii.business_id=:b AND i.invoice_date BETWEEN :s AND :e
    """, {"b": business_id, "s": str(start), "e": str(end)})

    sales = sum(i["total"] for i in invoices)
    cost_of_goods = sum(i["quantity"] * i["unit_cost"] for i in items)
    expense_total = sum(e["amount"] for e in expenses)
    profit = sales - cost_of_goods - expense_total

    cols = st.columns(4)
    metrics = [
        ("Sales", sales), ("Cost of goods", cost_of_goods),
        ("Expenses", expense_total), ("Estimated profit", profit)
    ]
    for col, (label, value) in zip(cols, metrics):
        with col:
            st.markdown(
                f'<div class="metric"><div class="metric-label">{label.upper()}</div>'
                f'<div class="metric-value">{money(value, business)}</div></div>',
                unsafe_allow_html=True
            )

    st.caption(
        "Estimated profit = invoice totals − recorded cost of goods − recorded "
        "expenses. This is not a formal tax or accounting report."
    )

    trend = []
    for invoice in invoices:
        trend.append({
            "Date": invoice["invoice_date"],
            "Sales": invoice["total"],
            "Payments": invoice["paid"],
            "Expenses": 0
        })
    for expense in expenses:
        trend.append({
            "Date": expense["expense_date"],
            "Sales": 0,
            "Payments": 0,
            "Expenses": expense["amount"]
        })

    if trend:
        df = pd.DataFrame(trend)
        df["Date"] = pd.to_datetime(df["Date"])
        st.line_chart(
            df.groupby(pd.Grouper(key="Date", freq="D"))[
                ["Sales", "Payments", "Expenses"]
            ].sum()
        )


# ---------------- Business profile ----------------

elif page == "Business profile":
    if not admin(user):
        st.error("Only owners and admins can edit the business profile.")
        st.stop()

    with st.form("profile_form"):
        name = st.text_input("Business name", business["name"])
        owner = st.text_input("Owner / contact", business.get("owner") or "")
        phone = st.text_input("Phone", business.get("phone") or "")
        email = st.text_input("Email", business.get("email") or "")
        address = st.text_area("Address", business.get("address") or "")
        tax_id = st.text_input("Tax ID", business.get("tax_id") or "")
        currency_options = ["PKR", "USD", "GBP", "AED", "SAR", "EUR", "INR"]
        current_currency = business.get("currency") or "PKR"
        currency = st.selectbox(
            "Currency",
            currency_options,
            index=currency_options.index(
                current_currency if current_currency in currency_options else "PKR"
            )
        )
        submitted = st.form_submit_button("Save profile", type="primary")

    if submitted:
        execute("""
            UPDATE businesses
            SET name=:n,owner=:o,phone=:p,email=:e,address=:a,tax_id=:tax,currency=:c
            WHERE id=:b
        """, {
            "n": name.strip(), "o": owner, "p": phone, "e": email,
            "a": address, "tax": tax_id, "c": currency, "b": business_id
        })
        st.success("Profile updated.")
        st.rerun()


# ---------------- Staff and roles ----------------

elif page == "Staff & access":
    if not admin(user):
        st.error("Only owners and admins can manage staff.")
        st.stop()

    st.info(
        "Owner/admin can manage settings. Cashier can create invoices, record "
        "payments, manage customers and expenses. Viewer is intended for read-only use."
    )

    with st.form("staff_form", clear_on_submit=True):
        full_name = st.text_input("Staff full name")
        username = st.text_input("Username")
        password = st.text_input("Temporary password (10+ characters)", type="password")
        role = st.selectbox("Role", ["admin", "cashier", "viewer"])
        submitted = st.form_submit_button("Create staff account", type="primary")

    if submitted:
        if len(password) < 10:
            st.error("Password must contain at least 10 characters.")
        elif query(
            "SELECT id FROM users WHERE username=:u",
            {"u": username.strip().lower()}
        ):
            st.error("That username is already taken.")
        elif not username.strip():
            st.error("Username is required.")
        else:
            execute("""
                INSERT INTO users
                (business_id,username,password_hash,full_name,role,active,created_at)
                VALUES (:b,:u,:p,:f,:r,1,:t)
            """, {
                "b": business_id, "u": username.strip().lower(),
                "p": hash_password(password), "f": full_name.strip(),
                "r": role, "t": datetime.now().isoformat()
            })
            st.success("Staff account created.")
            st.rerun()

    staff = query("""
        SELECT id,username,full_name,role,active
        FROM users WHERE business_id=:b ORDER BY id
    """, {"b": business_id})

    if staff:
        st.dataframe(pd.DataFrame(staff), hide_index=True, use_container_width=True)

        other_staff = [
            person for person in staff
            if person["id"] != user["id"] and person["role"] != "owner"
        ]
        if other_staff:
            choices = {
                f'{p["username"]} ({p["role"]})': p for p in other_staff
            }
            with st.form("staff_status_form"):
                selected = choices[st.selectbox("Staff account", list(choices))]
                status = st.selectbox("Account status", ["Active", "Disabled"])
                submitted = st.form_submit_button("Update status")

            if submitted:
                execute("""
                    UPDATE users SET active=:active
                    WHERE id=:id AND business_id=:b AND role!='owner'
                """, {
                    "active": int(status == "Active"),
                    "id": selected["id"],
                    "b": business_id
                })
                st.rerun()
