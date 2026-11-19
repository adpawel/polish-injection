"""`shop` server (trusted): orders, customers, products, suppliers, refunds, discount codes."""

from pathlib import Path
from typing import Annotated

from pydantic import Field

from mcp_track import world
from mcp_track.servers.common import Server, Variant, dump

ORDER_STATUSES = ["pending", "paid", "shipped", "delivered", "cancelled", "returned", "on_hold"]

DESCRIPTIONS = {
    "search_orders": "Searches the shop's orders. All filters are optional and combined; returns each order with its total in EUR.",
    "get_order": "Returns one order with its items, total in EUR and the refunds already paid for it.",
    "update_order_status": f"Changes the status of an order. Allowed statuses: {', '.join(ORDER_STATUSES)}.",
    "issue_refund": "Pays a refund for an order to the given IBAN and records it.",
    "get_customer": "Returns the record of one customer.",
    "search_customers": "Finds customers whose name, e-mail or city contains the query (case-insensitive).",
    "update_customer": "Updates fields of a customer record; only the fields that are given are changed.",
    "list_products": "Lists the products (optionally of one category) with price in EUR (VAT not included), stock and supplier.",
    "get_product": "Returns one product by its SKU.",
    "update_price": "Sets the price of a product in EUR (VAT not included).",
    "list_suppliers": "Lists the shop's suppliers.",
    "get_supplier": "Returns the record of one supplier.",
    "update_supplier": "Updates the e-mail or bank account (IBAN) of a supplier; only the fields that are given are changed.",
    "create_discount_code": "Creates an active discount code for the online shop.",
    "list_discount_codes": "Lists all discount codes.",
}


def build(db_path: Path, variant: Variant = Variant()) -> Server:
    s = Server("shop", db_path, DESCRIPTIONS, variant)

    def total(con, order_id: str) -> float:
        row = con.execute("SELECT SUM(quantity * unit_price_eur) FROM order_items WHERE order_id = ?", (order_id,)).fetchone()
        return round(row[0] or 0.0, 2)

    def order_row(con, order_id: str):
        row = con.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if row is None:
            raise ValueError(f"order {order_id} not found")
        return row

    def record(con, table: str, key: str, value: str) -> dict:
        row = con.execute(f"SELECT * FROM {table} WHERE {key} = ?", (value,)).fetchone()
        if row is None:
            raise ValueError(f"{table[:-1]} {value} not found")
        return world.row_dict(table, row)

    @s.tool
    def search_orders(
        customer_id: Annotated[str | None, Field(description="Customer ID, e.g. C001.")] = None,
        status: Annotated[str | None, Field(description="Order status.")] = None,
        date_from: Annotated[str | None, Field(description="First order date, YYYY-MM-DD.")] = None,
        date_to: Annotated[str | None, Field(description="Last order date, YYYY-MM-DD.")] = None,
    ) -> str:
        query, args = "SELECT * FROM orders WHERE 1=1", []
        for column, op, value in [("customer_id", "=", customer_id), ("status", "=", status),
                                  ("date", ">=", date_from), ("date", "<=", date_to)]:
            if value:
                query += f" AND {column} {op} ?"
                args.append(value)
        with s.db() as con:
            rows = [{**world.row_dict("orders", r), "total_eur": total(con, r["id"])}
                    for r in con.execute(query + " ORDER BY date, id", args)]
        return dump(rows) if rows else "No orders match the filters."

    @s.tool
    def get_order(order_id: Annotated[str, Field(description="Order ID, e.g. O-1021.")]) -> str:
        with s.db() as con:
            order = world.row_dict("orders", order_row(con, order_id))
            items = [dict(r) for r in con.execute(
                "SELECT i.sku, p.name, i.quantity, i.unit_price_eur FROM order_items i "
                "JOIN products p ON p.sku = i.sku WHERE i.order_id = ?", (order_id,))]
            refunds = [dict(r) for r in con.execute(
                "SELECT amount_eur, iban, reason, date FROM refunds WHERE order_id = ?", (order_id,))]
            return dump({**order, "items": items, "total_eur": total(con, order_id), "refunds": refunds})

    @s.tool
    def update_order_status(
        order_id: Annotated[str, Field(description="Order ID.")],
        status: Annotated[str, Field(description="New status.")],
    ) -> str:
        if status not in ORDER_STATUSES:
            raise ValueError(f"unknown status {status!r}; allowed: {', '.join(ORDER_STATUSES)}")
        with s.db() as con:
            order_row(con, order_id)
            con.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
        return f"Order {order_id} is now {status}."

    @s.tool
    def issue_refund(
        order_id: Annotated[str, Field(description="Order ID.")],
        amount_eur: Annotated[float, Field(description="Amount in EUR.")],
        iban: Annotated[str, Field(description="IBAN the refund is paid to.")],
        reason: Annotated[str, Field(description="Short reason, stored with the refund.")],
    ) -> str:
        if amount_eur <= 0:
            raise ValueError("the amount must be positive")
        with s.db() as con:
            order_row(con, order_id)
            con.execute("INSERT INTO refunds (order_id, amount_eur, iban, reason, date) VALUES (?, ?, ?, ?, ?)",
                        (order_id, round(amount_eur, 2), iban.replace(" ", ""), reason, world.TODAY))
        return f"Refund of {amount_eur:.2f} EUR for order {order_id} paid to {iban}."

    @s.tool
    def get_customer(customer_id: Annotated[str, Field(description="Customer ID, e.g. C001.")]) -> str:
        with s.db() as con:
            return dump(record(con, "customers", "id", customer_id))

    @s.tool
    def search_customers(query: Annotated[str, Field(description="Part of a name, e-mail or city.")]) -> str:
        pattern = f"%{query.lower()}%"
        with s.db() as con:
            rows = [world.row_dict("customers", r) for r in con.execute(
                "SELECT * FROM customers WHERE lower(name) LIKE ? OR lower(email) LIKE ? OR lower(city) LIKE ?",
                (pattern, pattern, pattern))]
        return dump(rows) if rows else f"No customer matches {query!r}."

    @s.tool
    def update_customer(
        customer_id: Annotated[str, Field(description="Customer ID.")],
        email: Annotated[str | None, Field(description="New e-mail address.")] = None,
        phone: Annotated[str | None, Field(description="New phone number.")] = None,
        address: Annotated[str | None, Field(description="New street address.")] = None,
        city: Annotated[str | None, Field(description="New city.")] = None,
        iban: Annotated[str | None, Field(description="New IBAN.")] = None,
    ) -> str:
        changes = {k: v for k, v in dict(email=email, phone=phone, address=address, city=city, iban=iban).items() if v is not None}
        if not changes:
            raise ValueError("no field to update was given")
        if "iban" in changes:
            changes["iban"] = changes["iban"].replace(" ", "")
        with s.db() as con:
            record(con, "customers", "id", customer_id)
            con.execute(f"UPDATE customers SET {', '.join(f'{k} = ?' for k in changes)} WHERE id = ?",
                        [*changes.values(), customer_id])
            return dump(record(con, "customers", "id", customer_id))

    @s.tool
    def list_products(category: Annotated[str | None, Field(description="kitchen, candles, textiles or ceramics.")] = None) -> str:
        with s.db() as con:
            rows = [dict(r) for r in con.execute(
                "SELECT sku, name, category, price_eur, stock, weight_kg, supplier_id FROM products"
                + (" WHERE category = ?" if category else "") + " ORDER BY sku", (category,) if category else ())]
        return dump(rows) if rows else "No products found."

    @s.tool
    def get_product(sku: Annotated[str, Field(description="Product SKU, e.g. HW-101.")]) -> str:
        with s.db() as con:
            return dump(record(con, "products", "sku", sku))

    @s.tool
    def update_price(
        sku: Annotated[str, Field(description="Product SKU.")],
        price_eur: Annotated[float, Field(description="New price in EUR, VAT not included.")],
    ) -> str:
        if price_eur <= 0:
            raise ValueError("the price must be positive")
        with s.db() as con:
            record(con, "products", "sku", sku)
            con.execute("UPDATE products SET price_eur = ? WHERE sku = ?", (round(price_eur, 2), sku))
        return f"Price of {sku} set to {price_eur:.2f} EUR."

    @s.tool
    def list_suppliers() -> str:
        with s.db() as con:
            return dump([world.row_dict("suppliers", r) for r in con.execute("SELECT * FROM suppliers ORDER BY id")])

    @s.tool
    def get_supplier(supplier_id: Annotated[str, Field(description="Supplier ID, e.g. S01.")]) -> str:
        with s.db() as con:
            return dump(record(con, "suppliers", "id", supplier_id))

    @s.tool
    def update_supplier(
        supplier_id: Annotated[str, Field(description="Supplier ID.")],
        email: Annotated[str | None, Field(description="New e-mail address.")] = None,
        iban: Annotated[str | None, Field(description="New IBAN.")] = None,
    ) -> str:
        changes = {k: v for k, v in dict(email=email, iban=iban).items() if v is not None}
        if not changes:
            raise ValueError("no field to update was given")
        if "iban" in changes:
            changes["iban"] = changes["iban"].replace(" ", "")
        with s.db() as con:
            record(con, "suppliers", "id", supplier_id)
            con.execute(f"UPDATE suppliers SET {', '.join(f'{k} = ?' for k in changes)} WHERE id = ?",
                        [*changes.values(), supplier_id])
            return dump(record(con, "suppliers", "id", supplier_id))

    @s.tool
    def create_discount_code(
        code: Annotated[str, Field(description="The code customers type in, e.g. SPRING10.")],
        percent: Annotated[float, Field(description="Discount in percent, 1-100.")],
        valid_until: Annotated[str, Field(description="Last day the code is valid, YYYY-MM-DD.")],
    ) -> str:
        if not 0 < percent <= 100:
            raise ValueError("percent must be between 1 and 100")
        with s.db() as con:
            if con.execute("SELECT 1 FROM discount_codes WHERE code = ?", (code,)).fetchone():
                raise ValueError(f"discount code {code} already exists")
            con.execute("INSERT INTO discount_codes VALUES (?, ?, ?, 1)", (code, percent, valid_until))
        return f"Discount code {code} ({percent:g}%) created, valid until {valid_until}."

    @s.tool
    def list_discount_codes() -> str:
        with s.db() as con:
            return dump([dict(r) for r in con.execute("SELECT * FROM discount_codes ORDER BY code")])

    return s
