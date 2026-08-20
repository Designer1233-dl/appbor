from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from uuid import uuid4


BASE_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = BASE_DIR / "public"
DEFAULT_DB_PATH = BASE_DIR / "bor.db"


def env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value or default


def env_str_alias(primary: str, fallback: str, default: str) -> str:
    value = os.getenv(primary)
    if value and value.strip():
        return value.strip()
    fallback_value = os.getenv(fallback)
    if fallback_value and fallback_value.strip():
        return fallback_value.strip()
    return default


def env_int(name: str, default: int) -> int:
    try:
        return int(env_str(name, str(default)))
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    try:
        return float(env_str(name, str(default)))
    except ValueError:
        return default


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


HOST = env_str("BOR_HOST", "127.0.0.1")
PORT = env_int("BOR_PORT", 8080)
DB_PATH = Path(env_str("BOR_DB_PATH", str(DEFAULT_DB_PATH)))

APP_TITLE = env_str("BOR_APP_TITLE", "BOR")
APP_MODE = env_str("BOR_APP_MODE", "mini-app")
DEFAULT_ADMIN_ID = env_int("BOR_DEFAULT_ADMIN_ID", 1)
DEFAULT_ADMIN_USERNAME = env_str("BOR_DEFAULT_ADMIN_USERNAME", "borlegend")
DEFAULT_ADMIN_DISPLAY_NAME = env_str("BOR_DEFAULT_ADMIN_DISPLAY_NAME", "Пухляк")

CRYPTOBOT_ENABLED = env_bool("BOR_CRYPTOBOT_ENABLED", False)
CRYPTOBOT_BOT_USERNAME = env_str("BOR_CRYPTOBOT_BOT_USERNAME", "CryptoBot")
CRYPTOBOT_API_TOKEN = env_str("BOR_CRYPTOBOT_API_TOKEN", "")
CRYPTOBOT_WEBHOOK_SECRET = env_str("BOR_CRYPTOBOT_WEBHOOK_SECRET", "")
CRYPTOBOT_ASSET = env_str("BOR_CRYPTOBOT_ASSET", "USDT")
CRYPTOBOT_TESTNET = env_bool("BOR_CRYPTOBOT_TESTNET", False)
CRYPTOBOT_INVOICE_EXPIRES_IN = env_int("BOR_CRYPTOBOT_INVOICE_EXPIRES_IN", 3600)

TELEGRAM_BOT_TOKEN = env_str("BOR_TELEGRAM_BOT_TOKEN", "")
WEBAPP_URL = env_str_alias("WEBAPP_URL", "BOR_TELEGRAM_WEBAPP_URL", "")
WEBHOOK_BASE_URL = env_str_alias("WEBHOOK_BASE_URL", "BOR_WEBHOOK_BASE_URL", "")
SESSION_SECRET = env_str("BOR_SESSION_SECRET", "change-me")

AUTO_DEPOSIT_DEFAULT = env_bool("BOR_AUTO_DEPOSIT_DEFAULT", True)
AUTO_WITHDRAW_DEFAULT = env_bool("BOR_AUTO_WITHDRAW_DEFAULT", True)
AUTO_WITHDRAW_LIMIT = env_float("BOR_AUTO_WITHDRAW_LIMIT", 100.0)
RISK_ALERTS_DEFAULT = env_int("BOR_RISK_ALERTS_DEFAULT", 3)
VIP_SILVER_DEFAULT = env_int("BOR_VIP_SILVER_DEFAULT", 120)
VIP_GOLD_DEFAULT = env_int("BOR_VIP_GOLD_DEFAULT", 44)
FREEZE_QUEUE_DEFAULT = env_int("BOR_FREEZE_QUEUE_DEFAULT", 1)

CRYPTO_PAY_BASE_URL = "https://testnet-pay.crypt.bot/api/" if CRYPTOBOT_TESTNET else "https://pay.crypt.bot/api/"


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def webhook_url() -> str:
    if not WEBHOOK_BASE_URL or not CRYPTOBOT_WEBHOOK_SECRET:
        return ""
    return f"{WEBHOOK_BASE_URL.rstrip('/')}/api/cryptobot/webhook/{CRYPTOBOT_WEBHOOK_SECRET}"


def crypto_enabled() -> bool:
    return CRYPTOBOT_ENABLED and bool(CRYPTOBOT_API_TOKEN)


def create_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = create_connection()
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL,
            display_name TEXT NOT NULL,
            balance REAL NOT NULL DEFAULT 0,
            in_game REAL NOT NULL DEFAULT 0,
            games_played INTEGER NOT NULL DEFAULT 0,
            wins INTEGER NOT NULL DEFAULT 0,
            volume REAL NOT NULL DEFAULT 0,
            is_admin INTEGER NOT NULL DEFAULT 0,
            vip_level TEXT NOT NULL DEFAULT 'Silver'
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            action TEXT NOT NULL,
            tag TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            amount REAL NOT NULL,
            status TEXT NOT NULL,
            risk_score TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS promos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            activation_limit INTEGER NOT NULL,
            activated_count INTEGER NOT NULL DEFAULT 0,
            deposit_required INTEGER NOT NULL DEFAULT 0,
            deposit_min REAL NOT NULL DEFAULT 0,
            expires_at TEXT NOT NULL,
            bonus_amount REAL NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS wheels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            prize_pool REAL NOT NULL,
            deposit_required INTEGER NOT NULL DEFAULT 0,
            required_deposit REAL NOT NULL DEFAULT 0,
            participants INTEGER NOT NULL DEFAULT 0,
            winners_count INTEGER NOT NULL DEFAULT 1,
            prize_per_winner REAL NOT NULL DEFAULT 0,
            ends_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'scheduled',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS wheel_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wheel_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(wheel_id, username),
            FOREIGN KEY(wheel_id) REFERENCES wheels(id)
        );

        CREATE TABLE IF NOT EXISTS deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL UNIQUE,
            username TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            asset TEXT NOT NULL,
            source TEXT NOT NULL,
            invoice_id INTEGER,
            invoice_hash TEXT,
            invoice_url TEXT,
            mini_app_invoice_url TEXT,
            web_app_invoice_url TEXT,
            payload TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            credited INTEGER NOT NULL DEFAULT 0,
            credited_at TEXT,
            paid_amount REAL,
            paid_asset TEXT,
            comment TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )

    if cur.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        cur.execute(
            """
            INSERT INTO users (id, username, display_name, balance, in_game, games_played, wins, volume, is_admin, vip_level)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                DEFAULT_ADMIN_ID,
                DEFAULT_ADMIN_USERNAME,
                DEFAULT_ADMIN_DISPLAY_NAME,
                428.40,
                96.00,
                35,
                7,
                5.44,
                1,
                "Silver",
            ),
        )

    defaults = {
        "auto_deposit": "1" if AUTO_DEPOSIT_DEFAULT else "0",
        "auto_withdraw": "1" if AUTO_WITHDRAW_DEFAULT else "0",
        "risk_alerts": str(RISK_ALERTS_DEFAULT),
        "vip_silver": str(VIP_SILVER_DEFAULT),
        "vip_gold": str(VIP_GOLD_DEFAULT),
        "freeze_queue": str(FREEZE_QUEUE_DEFAULT),
    }
    for key, value in defaults.items():
        cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))

    if cur.execute("SELECT COUNT(*) FROM activity_log").fetchone()[0] == 0:
        seed_logs = [
            ("storm.qq", "Создал депозит через CryptoBot на 85 USDT", "02:03"),
            ("nightdrop", "Выигрыш x50 и автозачисление 214 USDT", "01:58"),
            ("mika", "Попытка вывода с нового устройства", "risk"),
            (DEFAULT_ADMIN_USERNAME, "Вошёл по ссылке в денежное колесо", "01:44"),
        ]
        for username, action, tag in seed_logs:
            cur.execute(
                "INSERT INTO activity_log (username, action, tag, created_at) VALUES (?, ?, ?, ?)",
                (username, action, tag, now_iso()),
            )

    if cur.execute("SELECT COUNT(*) FROM withdrawals").fetchone()[0] == 0:
        for username, amount, status, risk_score in [("shiro", 125.0, "pending", "clean"), ("loki", 52.0, "review", "medium")]:
            cur.execute(
                "INSERT INTO withdrawals (username, amount, status, risk_score, created_at) VALUES (?, ?, ?, ?, ?)",
                (username, amount, status, risk_score, now_iso()),
            )

    if cur.execute("SELECT COUNT(*) FROM promos").fetchone()[0] == 0:
        base_time = datetime.now(UTC)
        promos = [
            ("BORVIP", 30, 8, 1, 25.0, base_time + timedelta(days=3), 10.0, 1),
            ("GREENSPIN", 50, 41, 0, 0.0, base_time + timedelta(days=1), 5.0, 1),
        ]
        for code, activation_limit, activated_count, deposit_required, deposit_min, expires_at, bonus_amount, active in promos:
            cur.execute(
                """
                INSERT INTO promos (
                    code, activation_limit, activated_count, deposit_required,
                    deposit_min, expires_at, bonus_amount, active, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    code,
                    activation_limit,
                    activated_count,
                    deposit_required,
                    deposit_min,
                    expires_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                    bonus_amount,
                    active,
                    now_iso(),
                ),
            )

    if cur.execute("SELECT COUNT(*) FROM wheels").fetchone()[0] == 0:
        ends_at = datetime.now(UTC) + timedelta(minutes=13)
        cur.execute(
            """
            INSERT INTO wheels (
                slug, title, prize_pool, deposit_required, required_deposit, participants,
                winners_count, prize_per_winner, ends_at, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "wheel-bor-8902",
                "Weekly Money Wheel",
                500.0,
                0,
                0.0,
                31,
                5,
                100.0,
                ends_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "scheduled",
                now_iso(),
            ),
        )

    conn.commit()
    conn.close()


def fetch_settings(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {row["key"]: row["value"] for row in rows}


def fetch_user(conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM users WHERE id = 1").fetchone()
    return dict(row) if row else {}


def fetch_activity(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, username, action, tag, created_at FROM activity_log ORDER BY id DESC LIMIT 12"
    ).fetchall()
    return [dict(row) for row in rows]


def fetch_withdrawals(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, username, amount, status, risk_score, created_at FROM withdrawals ORDER BY id DESC"
    ).fetchall()
    return [dict(row) for row in rows]


def fetch_promos(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, code, activation_limit, activated_count, deposit_required,
               deposit_min, expires_at, bonus_amount, active, created_at
        FROM promos
        ORDER BY id DESC
        """
    ).fetchall()
    return [dict(row) for row in rows]


def fetch_wheels(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, slug, title, prize_pool, deposit_required, required_deposit,
               participants, winners_count, prize_per_winner, ends_at, status, created_at
        FROM wheels
        ORDER BY id DESC
        """
    ).fetchall()
    return [dict(row) for row in rows]


def fetch_deposits(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, request_id, username, amount, asset, source, invoice_id, invoice_hash,
               invoice_url, mini_app_invoice_url, web_app_invoice_url, status, credited,
               credited_at, paid_amount, paid_asset, comment, created_at, updated_at
        FROM deposits
        ORDER BY id DESC
        LIMIT 8
        """
    ).fetchall()
    return [dict(row) for row in rows]


def add_log(conn: sqlite3.Connection, username: str, action: str, tag: str) -> None:
    conn.execute(
        "INSERT INTO activity_log (username, action, tag, created_at) VALUES (?, ?, ?, ?)",
        (username, action, tag, now_iso()),
    )


def crypto_api_request(method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if not crypto_enabled():
        raise RuntimeError("CryptoBot API not configured")

    body = json.dumps(payload or {}).encode("utf-8")
    request = urllib.request.Request(
        url=urllib.parse.urljoin(CRYPTO_PAY_BASE_URL, method),
        data=body,
        headers={
            "Crypto-Pay-API-Token": CRYPTOBOT_API_TOKEN,
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"CryptoBot HTTP {exc.code}: {raw}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"CryptoBot unavailable: {exc.reason}") from exc

    data = json.loads(raw)
    if not data.get("ok"):
        raise RuntimeError(data.get("error", "CryptoBot request failed"))
    return data["result"]


def build_invoice_payload(user: dict[str, Any], amount: float, request_id: str) -> dict[str, Any]:
    app_url = WEBAPP_URL or f"http://{HOST}:{PORT}"
    payload = {
        "bor_request_id": request_id,
        "user_id": user["id"],
        "username": user["username"],
        "amount": amount,
    }
    return {
        "asset": CRYPTOBOT_ASSET,
        "amount": f"{amount:.2f}",
        "description": f"{APP_TITLE} deposit for @{user['username']}",
        "hidden_message": f"Баланс в {APP_TITLE} обновится автоматически после оплаты.",
        "paid_btn_name": "callback",
        "paid_btn_url": app_url,
        "payload": json.dumps(payload, ensure_ascii=False),
        "allow_comments": False,
        "allow_anonymous": True,
        "expires_in": CRYPTOBOT_INVOICE_EXPIRES_IN,
    }


def create_mock_invoice(user: dict[str, Any], amount: float, request_id: str) -> dict[str, Any]:
    slug = f"mock_{request_id}"
    return {
        "invoice_id": None,
        "hash": slug,
        "bot_invoice_url": f"https://t.me/{CRYPTOBOT_BOT_USERNAME}?start={slug}",
        "mini_app_invoice_url": f"{WEBAPP_URL or ''}?invoice={slug}",
        "web_app_invoice_url": f"{WEBAPP_URL or ''}?invoice={slug}",
        "status": "active",
        "payload": json.dumps({"mock": True, "user_id": user["id"], "amount": amount}, ensure_ascii=False),
        "paid_asset": None,
        "paid_amount": None,
        "fee_amount": None,
    }


def save_deposit(
    conn: sqlite3.Connection,
    user: dict[str, Any],
    amount: float,
    source: str,
    invoice: dict[str, Any],
    request_id: str,
) -> None:
    conn.execute(
        """
        INSERT INTO deposits (
            request_id, username, user_id, amount, asset, source, invoice_id, invoice_hash,
            invoice_url, mini_app_invoice_url, web_app_invoice_url, payload, status,
            credited, paid_amount, paid_asset, comment, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?)
        """,
        (
            request_id,
            user["username"],
            user["id"],
            amount,
            CRYPTOBOT_ASSET,
            source,
            invoice.get("invoice_id"),
            invoice.get("hash"),
            invoice.get("bot_invoice_url"),
            invoice.get("mini_app_invoice_url"),
            invoice.get("web_app_invoice_url"),
            invoice.get("payload", ""),
            invoice.get("status", "active"),
            invoice.get("paid_amount"),
            invoice.get("paid_asset"),
            "awaiting payment",
            now_iso(),
            now_iso(),
        ),
    )


def credit_deposit_if_needed(conn: sqlite3.Connection, deposit_row: sqlite3.Row, paid_amount: float | None, paid_asset: str | None) -> bool:
    if deposit_row["credited"]:
        return False

    amount_to_credit = paid_amount if paid_amount is not None else deposit_row["amount"]
    conn.execute(
        "UPDATE users SET balance = balance + ?, volume = volume + ? WHERE id = ?",
        (amount_to_credit, amount_to_credit, deposit_row["user_id"]),
    )
    conn.execute(
        """
        UPDATE deposits
        SET credited = 1,
            credited_at = ?,
            paid_amount = COALESCE(?, paid_amount),
            paid_asset = COALESCE(?, paid_asset),
            updated_at = ?
        WHERE id = ?
        """,
        (now_iso(), paid_amount, paid_asset, now_iso(), deposit_row["id"]),
    )
    add_log(conn, deposit_row["username"], f"Оплата инвойса зачислена: {amount_to_credit:.2f} {paid_asset or deposit_row['asset']}", "deposit")
    return True


def apply_invoice_update(conn: sqlite3.Connection, invoice: dict[str, Any], source: str) -> tuple[bool, str]:
    invoice_id = invoice.get("invoice_id")
    invoice_hash = invoice.get("hash")
    deposit_row = None
    if invoice_id is not None:
        deposit_row = conn.execute("SELECT * FROM deposits WHERE invoice_id = ?", (invoice_id,)).fetchone()
    if deposit_row is None and invoice_hash:
        deposit_row = conn.execute("SELECT * FROM deposits WHERE invoice_hash = ?", (invoice_hash,)).fetchone()
    if deposit_row is None:
        return False, "deposit_not_found"

    status = invoice.get("status", deposit_row["status"])
    paid_amount = invoice.get("paid_amount")
    if paid_amount is not None:
        paid_amount = float(paid_amount)
    paid_asset = invoice.get("paid_asset")
    conn.execute(
        """
        UPDATE deposits
        SET status = ?,
            invoice_url = COALESCE(?, invoice_url),
            mini_app_invoice_url = COALESCE(?, mini_app_invoice_url),
            web_app_invoice_url = COALESCE(?, web_app_invoice_url),
            paid_amount = COALESCE(?, paid_amount),
            paid_asset = COALESCE(?, paid_asset),
            comment = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            status,
            invoice.get("bot_invoice_url"),
            invoice.get("mini_app_invoice_url"),
            invoice.get("web_app_invoice_url"),
            paid_amount,
            paid_asset,
            source,
            now_iso(),
            deposit_row["id"],
        ),
    )

    credited_now = False
    if status == "paid":
        credited_now = credit_deposit_if_needed(conn, deposit_row, paid_amount, paid_asset)
    return credited_now, status


def verify_cryptobot_signature(raw_body: bytes, headers: Any) -> bool:
    if not CRYPTOBOT_API_TOKEN:
        return False
    signature = headers.get("crypto-pay-api-signature", "")
    if not signature:
        return False
    secret = hashlib.sha256(CRYPTOBOT_API_TOKEN.encode("utf-8")).digest()
    calculated = hmac.new(secret, raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(calculated, signature)


def sync_paid_invoices() -> dict[str, Any]:
    if not crypto_enabled():
        return {"updated": 0, "checked": 0}

    result = crypto_api_request("getInvoices", {"status": "paid", "count": 100})
    invoices = result.get("items", [])
    conn = create_connection()
    updated = 0
    for invoice in invoices:
        credited_now, _ = apply_invoice_update(conn, invoice, "sync")
        if credited_now:
            updated += 1
    conn.commit()
    conn.close()
    return {"updated": updated, "checked": len(invoices)}


def bootstrap_payload() -> dict[str, Any]:
    conn = create_connection()
    payload = {
        "app": {
            "title": APP_TITLE,
            "mode": APP_MODE,
            "webappUrl": WEBAPP_URL,
            "webhookBaseUrl": WEBHOOK_BASE_URL,
            "webhookUrl": webhook_url(),
            "cryptobotEnabled": CRYPTOBOT_ENABLED,
            "cryptobotConfigured": bool(CRYPTOBOT_API_TOKEN),
            "cryptobotBotUsername": CRYPTOBOT_BOT_USERNAME,
            "cryptobotAsset": CRYPTOBOT_ASSET,
        },
        "user": fetch_user(conn),
        "settings": fetch_settings(conn),
        "activity": fetch_activity(conn),
        "withdrawals": fetch_withdrawals(conn),
        "promos": fetch_promos(conn),
        "wheels": fetch_wheels(conn),
        "deposits": fetch_deposits(conn),
        "x50Feed": [
            {"user": "@neo", "amount": 0.20},
            {"user": "@ash", "amount": 0.55},
            {"user": "@sai", "amount": 1.00},
            {"user": "@kei", "amount": 0.80},
            {"user": "@ida", "amount": 0.40},
        ],
        "games": [
            {"name": "Pulse", "icon": "🎲", "note": "live", "theme": "pulse"},
            {"name": "Limbo", "icon": "📈", "note": "green", "theme": "limbo"},
            {"name": "Crash", "icon": "☄", "note": "hot", "theme": "crash"},
            {"name": "Mines", "icon": "💣", "note": "risk", "theme": "mines"},
            {"name": "Slot", "icon": "🎰", "note": "jackpot", "theme": "slot"},
            {"name": "Blackjack", "icon": "🂡", "note": "cards", "theme": "blackjack"},
        ],
    }
    conn.close()
    return payload


class AppHandler(BaseHTTPRequestHandler):
    server_version = "BORServer/2.0"

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/bootstrap":
            self.send_json(bootstrap_payload())
            return
        if parsed.path == "/api/deposits/sync":
            try:
                stats = sync_paid_invoices()
            except RuntimeError as exc:
                self.send_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
                return
            self.send_json({"ok": True, "stats": stats, "data": bootstrap_payload()})
            return
        self.serve_static(parsed.path)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        raw_body = self.read_body()

        if parsed.path.startswith("/api/cryptobot/webhook/"):
            secret = parsed.path.rsplit("/", 1)[-1]
            return self.handle_cryptobot_webhook(secret, raw_body)

        body = self.read_json(raw_body)

        if parsed.path == "/api/deposit/create-check":
            return self.handle_create_invoice(body)
        if parsed.path == "/api/withdrawals":
            return self.handle_withdrawal_request(body)
        if parsed.path == "/api/promos/activate":
            return self.handle_activate_promo(body)
        if parsed.path == "/api/admin/settings":
            return self.handle_admin_settings(body)
        if parsed.path == "/api/admin/promos":
            return self.handle_admin_create_promo(body)
        if parsed.path.startswith("/api/admin/promos/") and parsed.path.endswith("/delete"):
            return self.handle_admin_delete_promo(parsed.path.split("/")[4])
        if parsed.path.startswith("/api/admin/withdrawals/") and parsed.path.endswith("/approve"):
            return self.handle_admin_withdrawal_status(parsed.path.split("/")[4], "approved")
        if parsed.path.startswith("/api/admin/withdrawals/") and parsed.path.endswith("/reject"):
            return self.handle_admin_withdrawal_status(parsed.path.split("/")[4], "rejected")
        if parsed.path == "/api/admin/wheels":
            return self.handle_admin_create_wheel(body)
        if parsed.path.startswith("/api/wheels/") and parsed.path.endswith("/join"):
            return self.handle_join_wheel(parsed.path.split("/")[3])

        self.send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def serve_static(self, request_path: str) -> None:
        relative = request_path.lstrip("/") or "index.html"
        file_path = (PUBLIC_DIR / relative).resolve()
        if not str(file_path).startswith(str(PUBLIC_DIR.resolve())) or not file_path.exists() or file_path.is_dir():
            self.send_json({"error": "File not found"}, status=HTTPStatus.NOT_FOUND)
            return

        content_type = "text/plain; charset=utf-8"
        if file_path.suffix == ".html":
            content_type = "text/html; charset=utf-8"
        elif file_path.suffix == ".css":
            content_type = "text/css; charset=utf-8"
        elif file_path.suffix == ".js":
            content_type = "application/javascript; charset=utf-8"

        data = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0"))
        return self.rfile.read(length) if length else b""

    def read_json(self, raw: bytes) -> dict[str, Any]:
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def handle_create_invoice(self, body: dict[str, Any]) -> None:
        amount = float(body.get("amount", 0) or 0)
        if amount <= 0:
            self.send_json({"error": "Введите сумму больше 0"}, status=HTTPStatus.BAD_REQUEST)
            return

        conn = create_connection()
        user = fetch_user(conn)
        request_id = uuid4().hex

        try:
            if crypto_enabled():
                invoice = crypto_api_request("createInvoice", build_invoice_payload(user, amount, request_id))
                source = "cryptobot"
            else:
                invoice = create_mock_invoice(user, amount, request_id)
                source = "mock"
        except RuntimeError as exc:
            conn.close()
            self.send_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
            return

        save_deposit(conn, user, amount, source, invoice, request_id)
        add_log(conn, user["username"], f"Создан инвойс на {amount:.2f} {CRYPTOBOT_ASSET}", "invoice")
        conn.commit()
        conn.close()

        invoice_url = invoice.get("mini_app_invoice_url") or invoice.get("web_app_invoice_url") or invoice.get("bot_invoice_url")
        self.send_json(
            {
                "ok": True,
                "message": f"Инвойс на {amount:.2f} {CRYPTOBOT_ASSET} создан",
                "invoiceUrl": invoice_url,
                "invoiceHash": invoice.get("hash"),
                "data": bootstrap_payload(),
            }
        )

    def handle_cryptobot_webhook(self, secret: str, raw_body: bytes) -> None:
        if not CRYPTOBOT_WEBHOOK_SECRET or secret != CRYPTOBOT_WEBHOOK_SECRET:
            self.send_json({"error": "Forbidden"}, status=HTTPStatus.FORBIDDEN)
            return
        if not verify_cryptobot_signature(raw_body, self.headers):
            self.send_json({"error": "Bad signature"}, status=HTTPStatus.FORBIDDEN)
            return

        try:
            update = self.read_json(raw_body)
        except json.JSONDecodeError:
            self.send_json({"error": "Invalid JSON"}, status=HTTPStatus.BAD_REQUEST)
            return

        if update.get("update_type") != "invoice_paid":
            self.send_json({"ok": True, "ignored": True})
            return

        invoice = update.get("payload") or {}
        conn = create_connection()
        credited_now, status = apply_invoice_update(conn, invoice, "webhook")
        conn.commit()
        conn.close()
        self.send_json({"ok": True, "credited": credited_now, "status": status})

    def handle_withdrawal_request(self, body: dict[str, Any]) -> None:
        amount = float(body.get("amount", 0) or 0)
        conn = create_connection()
        user = fetch_user(conn)
        if amount <= 0:
            conn.close()
            self.send_json({"error": "Введите сумму больше 0"}, status=HTTPStatus.BAD_REQUEST)
            return
        if amount > user["balance"]:
            conn.close()
            self.send_json({"error": "Недостаточно средств"}, status=HTTPStatus.BAD_REQUEST)
            return

        settings = fetch_settings(conn)
        status = "approved" if settings.get("auto_withdraw") == "1" and amount <= AUTO_WITHDRAW_LIMIT else "pending"
        risk_score = "clean" if amount <= AUTO_WITHDRAW_LIMIT else "medium"
        conn.execute(
            "INSERT INTO withdrawals (username, amount, status, risk_score, created_at) VALUES (?, ?, ?, ?, ?)",
            (user["username"], amount, status, risk_score, now_iso()),
        )
        conn.execute("UPDATE users SET balance = balance - ? WHERE id = ?", (amount, user["id"]))
        add_log(conn, user["username"], f"Создана заявка на вывод {amount:.2f} {CRYPTOBOT_ASSET}", status)
        conn.commit()
        conn.close()
        self.send_json({"ok": True, "status": status, "data": bootstrap_payload()})

    def handle_activate_promo(self, body: dict[str, Any]) -> None:
        code = str(body.get("code", "")).strip().upper()
        conn = create_connection()
        row = conn.execute("SELECT * FROM promos WHERE code = ? AND active = 1", (code,)).fetchone()
        user = fetch_user(conn)
        if not row:
            conn.close()
            self.send_json({"error": "Промокод не найден"}, status=HTTPStatus.BAD_REQUEST)
            return
        if row["activated_count"] >= row["activation_limit"]:
            conn.close()
            self.send_json({"error": "Активации закончились"}, status=HTTPStatus.BAD_REQUEST)
            return

        conn.execute("UPDATE promos SET activated_count = activated_count + 1 WHERE id = ?", (row["id"],))
        conn.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (row["bonus_amount"], user["id"]))
        add_log(conn, user["username"], f"Активировал промокод {code} на {row['bonus_amount']:.2f} {CRYPTOBOT_ASSET}", "promo")
        conn.commit()
        conn.close()
        self.send_json({"ok": True, "message": f"Промокод {code} активирован", "data": bootstrap_payload()})

    def handle_admin_settings(self, body: dict[str, Any]) -> None:
        key = str(body.get("key", "")).strip()
        value = "1" if body.get("value") else "0"
        if key not in {"auto_deposit", "auto_withdraw"}:
            self.send_json({"error": "Недопустимая настройка"}, status=HTTPStatus.BAD_REQUEST)
            return

        conn = create_connection()
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        title = "автопополнение" if key == "auto_deposit" else "автовыводы"
        add_log(conn, "admin", f"Переключил {title}: {'вкл' if value == '1' else 'выкл'}", "admin")
        conn.commit()
        conn.close()
        self.send_json({"ok": True, "data": bootstrap_payload()})

    def handle_admin_create_promo(self, body: dict[str, Any]) -> None:
        code = str(body.get("code", "")).strip().upper()
        activation_limit = int(body.get("activation_limit", 0) or 0)
        deposit_required = 1 if body.get("deposit_required") else 0
        deposit_min = float(body.get("deposit_min", 0) or 0)
        bonus_amount = float(body.get("bonus_amount", 0) or 0)
        expires_at = str(body.get("expires_at", "")).strip() or now_iso()
        if not code or activation_limit <= 0:
            self.send_json({"error": "Заполни код и лимит активаций"}, status=HTTPStatus.BAD_REQUEST)
            return

        conn = create_connection()
        conn.execute(
            """
            INSERT INTO promos (
                code, activation_limit, activated_count, deposit_required,
                deposit_min, expires_at, bonus_amount, active, created_at
            ) VALUES (?, ?, 0, ?, ?, ?, ?, 1, ?)
            """,
            (code, activation_limit, deposit_required, deposit_min, expires_at, bonus_amount, now_iso()),
        )
        add_log(conn, "admin", f"Создал промокод {code}", "promo")
        conn.commit()
        conn.close()
        self.send_json({"ok": True, "data": bootstrap_payload()})

    def handle_admin_delete_promo(self, promo_id: str) -> None:
        conn = create_connection()
        row = conn.execute("SELECT code FROM promos WHERE id = ?", (promo_id,)).fetchone()
        if not row:
            conn.close()
            self.send_json({"error": "Промокод не найден"}, status=HTTPStatus.NOT_FOUND)
            return
        conn.execute("DELETE FROM promos WHERE id = ?", (promo_id,))
        add_log(conn, "admin", f"Удалил промокод {row['code']}", "promo")
        conn.commit()
        conn.close()
        self.send_json({"ok": True, "data": bootstrap_payload()})

    def handle_admin_withdrawal_status(self, withdrawal_id: str, status: str) -> None:
        conn = create_connection()
        row = conn.execute("SELECT username, amount FROM withdrawals WHERE id = ?", (withdrawal_id,)).fetchone()
        if not row:
            conn.close()
            self.send_json({"error": "Заявка не найдена"}, status=HTTPStatus.NOT_FOUND)
            return

        conn.execute("UPDATE withdrawals SET status = ? WHERE id = ?", (status, withdrawal_id))
        add_log(conn, "admin", f"Заявка #{withdrawal_id} {status}", "withdraw")
        if status == "rejected" and row["username"] == DEFAULT_ADMIN_USERNAME:
            conn.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (row["amount"], DEFAULT_ADMIN_ID))
        conn.commit()
        conn.close()
        self.send_json({"ok": True, "data": bootstrap_payload()})

    def handle_admin_create_wheel(self, body: dict[str, Any]) -> None:
        slug = str(body.get("slug", "")).strip() or f"wheel-{datetime.now(UTC).strftime('%H%M%S')}"
        title = str(body.get("title", "")).strip() or "BOR Money Wheel"
        prize_pool = float(body.get("prize_pool", 0) or 0)
        deposit_required = 1 if body.get("deposit_required") else 0
        required_deposit = float(body.get("required_deposit", 0) or 0)
        winners_count = int(body.get("winners_count", 1) or 1)
        minutes_until_end = int(body.get("minutes_until_end", 10) or 10)
        if prize_pool <= 0:
            self.send_json({"error": "Призовой фонд должен быть больше 0"}, status=HTTPStatus.BAD_REQUEST)
            return

        ends_at = datetime.now(UTC) + timedelta(minutes=minutes_until_end)
        prize_per_winner = round(prize_pool / winners_count, 2)
        conn = create_connection()
        conn.execute(
            """
            INSERT INTO wheels (
                slug, title, prize_pool, deposit_required, required_deposit,
                participants, winners_count, prize_per_winner, ends_at, status, created_at
            ) VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, 'scheduled', ?)
            """,
            (
                slug,
                title,
                prize_pool,
                deposit_required,
                required_deposit,
                winners_count,
                prize_per_winner,
                ends_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                now_iso(),
            ),
        )
        add_log(conn, "admin", f"Создал колесо {slug} на {prize_pool:.2f} {CRYPTOBOT_ASSET}", "wheel")
        conn.commit()
        conn.close()
        self.send_json({"ok": True, "data": bootstrap_payload()})

    def handle_join_wheel(self, slug: str) -> None:
        conn = create_connection()
        wheel = conn.execute("SELECT * FROM wheels WHERE slug = ?", (slug,)).fetchone()
        user = fetch_user(conn)
        if not wheel:
            conn.close()
            self.send_json({"error": "Колесо не найдено"}, status=HTTPStatus.NOT_FOUND)
            return
        if wheel["deposit_required"] and user["volume"] < wheel["required_deposit"]:
            conn.close()
            self.send_json({"error": "Недостаточный депозит для участия"}, status=HTTPStatus.BAD_REQUEST)
            return

        try:
            conn.execute(
                "INSERT INTO wheel_entries (wheel_id, username, created_at) VALUES (?, ?, ?)",
                (wheel["id"], user["username"], now_iso()),
            )
            conn.execute("UPDATE wheels SET participants = participants + 1 WHERE id = ?", (wheel["id"],))
            add_log(conn, user["username"], f"Вступил в колесо {slug}", "wheel")
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            self.send_json({"error": "Ты уже участвуешь"}, status=HTTPStatus.BAD_REQUEST)
            return

        conn.close()
        self.send_json({"ok": True, "data": bootstrap_payload()})


def main() -> None:
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), AppHandler)
    print(f"BOR server started on http://{HOST}:{PORT}")
    print(f"DB path: {DB_PATH}")
    print(f"CryptoBot enabled: {CRYPTOBOT_ENABLED}")
    print(f"Webhook URL: {webhook_url() or 'not configured'}")
    server.serve_forever()


if __name__ == "__main__":
    main()
