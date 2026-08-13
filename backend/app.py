"""Lockwell identity protection API.

Security model (MVP):
- Account passwords are hashed with Werkzeug (pbkdf2).
- Vault payloads are ciphertext-only; the server never receives vault keys.
- Monitored identity values are stored as salted hashes + display masks.
- Every sensitive action writes an audit event for transparency.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timezone

from flask import Flask, g, jsonify, request
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "sqlite:///lockwell.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", secrets.token_hex(32))
app.config["MONITOR_PEPPER"] = os.environ.get(
    "MONITOR_PEPPER", "lockwell-dev-pepper-change-me"
)

CORS(
    app,
    resources={r"/api/*": {"origins": os.environ.get("CORS_ORIGINS", "*")}},
    supports_credentials=True,
)

db = SQLAlchemy(app)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    vault_salt = db.Column(db.String(64), nullable=False)
    sessions = db.relationship("Session", backref="user", lazy=True, cascade="all, delete")
    monitored_items = db.relationship(
        "MonitoredItem", backref="user", lazy=True, cascade="all, delete"
    )
    alerts = db.relationship("Alert", backref="user", lazy=True, cascade="all, delete")
    vault_entries = db.relationship(
        "VaultEntry", backref="user", lazy=True, cascade="all, delete"
    )
    devices = db.relationship("Device", backref="user", lazy=True, cascade="all, delete")
    audit_events = db.relationship(
        "AuditEvent", backref="user", lazy=True, cascade="all, delete"
    )
    guard_nodes = db.relationship(
        "GuardNode", backref="user", lazy=True, cascade="all, delete"
    )
    network_events = db.relationship(
        "NetworkEvent", backref="user", lazy=True, cascade="all, delete"
    )
    block_rules = db.relationship(
        "BlockRule", backref="user", lazy=True, cascade="all, delete"
    )


class Session(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    last_seen_at = db.Column(db.DateTime, default=utcnow, nullable=False)


class MonitoredItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    kind = db.Column(db.String(40), nullable=False)
    label = db.Column(db.String(120), nullable=False)
    value_hash = db.Column(db.String(64), nullable=False)
    display_mask = db.Column(db.String(80), nullable=False)
    status = db.Column(db.String(20), default="clear", nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)


class Alert(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    category = db.Column(db.String(40), nullable=False)
    severity = db.Column(db.String(20), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    detail = db.Column(db.Text, nullable=False)
    source = db.Column(db.String(80), default="Lockwell Monitor", nullable=False)
    acknowledged = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)


class VaultEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    ciphertext = db.Column(db.Text, nullable=False)
    iv = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class Device(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    platform = db.Column(db.String(40), nullable=False)
    vpn_enabled = db.Column(db.Boolean, default=False, nullable=False)
    antivirus_enabled = db.Column(db.Boolean, default=False, nullable=False)
    screen_lock_enabled = db.Column(db.Boolean, default=True, nullable=False)
    updates_current = db.Column(db.Boolean, default=True, nullable=False)
    last_check_in = db.Column(db.DateTime, default=utcnow, nullable=False)


class AuditEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    action = db.Column(db.String(80), nullable=False)
    detail = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)


class GuardNode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    agent_token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    mode = db.Column(db.String(20), default="simulate", nullable=False)
    backend = db.Column(db.String(40), default="simulate", nullable=False)
    interface = db.Column(db.String(80), default="any", nullable=False)
    status = db.Column(db.String(20), default="pending", nullable=False)
    packets_seen = db.Column(db.Integer, default=0, nullable=False)
    packets_blocked = db.Column(db.Integer, default=0, nullable=False)
    last_seen_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)


class NetworkEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    guard_node_id = db.Column(db.Integer, db.ForeignKey("guard_node.id"), nullable=True)
    category = db.Column(db.String(40), nullable=False)
    severity = db.Column(db.String(20), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    detail = db.Column(db.Text, nullable=False)
    src_ip = db.Column(db.String(64), nullable=False)
    dst_ip = db.Column(db.String(64), nullable=False)
    dst_port = db.Column(db.Integer, default=0, nullable=False)
    protocol = db.Column(db.String(20), default="TCP", nullable=False)
    action = db.Column(db.String(20), default="logged", nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)


class BlockRule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    ip = db.Column(db.String(64), nullable=False)
    reason = db.Column(db.String(255), nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    hits = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)


def hash_monitor_value(value: str) -> str:
    normalized = value.strip().lower()
    return hmac.new(
        app.config["MONITOR_PEPPER"].encode("utf-8"),
        normalized.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def mask_value(kind: str, value: str) -> str:
    cleaned = value.strip()
    if kind in {"ssn", "bank", "card"}:
        digits = "".join(ch for ch in cleaned if ch.isdigit())
        tail = digits[-4:] if len(digits) >= 4 else digits
        return f"•••• {tail}"
    if kind == "email":
        if "@" not in cleaned:
            return cleaned[:2] + "•••"
        local, domain = cleaned.split("@", 1)
        return f"{local[:1]}•••@{domain}"
    if len(cleaned) <= 4:
        return "••••"
    return cleaned[:2] + "•••" + cleaned[-2:]


def audit(user_id: int, action: str, detail: str) -> None:
    db.session.add(AuditEvent(user_id=user_id, action=action, detail=detail))


def issue_session(user: User) -> str:
    token = secrets.token_hex(32)
    db.session.add(Session(user_id=user.id, token=token))
    return token


def current_user() -> User | None:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth.split(" ", 1)[1].strip()
    session = Session.query.filter_by(token=token).first()
    if not session:
        return None
    session.last_seen_at = utcnow()
    return session.user


@app.before_request
def load_user() -> None:
    g.user = current_user()


def require_user():
    if g.user is None:
        return jsonify({"error": "Authentication required"}), 401
    return None


def current_guard_node() -> GuardNode | None:
    token = request.headers.get("X-Guard-Token", "").strip()
    if not token:
        return None
    return GuardNode.query.filter_by(agent_token=token).first()


def require_guard_node():
    node = current_guard_node()
    if node is None:
        return None, (jsonify({"error": "Valid X-Guard-Token required"}), 401)
    return node, None


def seed_demo_for_user(user: User) -> None:
    if user.monitored_items:
        return

    samples = [
        ("email", "Primary email", "alex@example.com"),
        ("phone", "Mobile", "5550148291"),
        ("card", "Everyday card", "4111111111111111"),
        ("ssn", "SSN", "123456789"),
    ]
    for kind, label, value in samples:
        db.session.add(
            MonitoredItem(
                user_id=user.id,
                kind=kind,
                label=label,
                value_hash=hash_monitor_value(value),
                display_mask=mask_value(kind, value),
                status="clear",
            )
        )

    db.session.add_all(
        [
            Alert(
                user_id=user.id,
                category="breach",
                severity="high",
                title="Credential pair seen in a breach corpus",
                detail="A monitored email hash matched a known breach dump. Rotate the password and enable MFA.",
                source="Breach Graph",
            ),
            Alert(
                user_id=user.id,
                category="darkweb",
                severity="medium",
                title="Phone number surfaced on a paste site",
                detail="Simulated dark-web hit for educational MVP monitoring. No live dark-web crawling is performed.",
                source="Paste Watch",
            ),
            Alert(
                user_id=user.id,
                category="device",
                severity="low",
                title="VPN inactive on MacBook Air",
                detail="Device protection recommends enabling the secure tunnel on public networks.",
                source="Device Guard",
            ),
        ]
    )

    db.session.add_all(
        [
            Device(
                user_id=user.id,
                name="MacBook Air",
                platform="macos",
                vpn_enabled=False,
                antivirus_enabled=True,
                screen_lock_enabled=True,
                updates_current=True,
            ),
            Device(
                user_id=user.id,
                name="Pixel 8",
                platform="android",
                vpn_enabled=True,
                antivirus_enabled=True,
                screen_lock_enabled=True,
                updates_current=False,
            ),
        ]
    )

    db.session.add(
        GuardNode(
            user_id=user.id,
            name="Home edge gateway",
            agent_token=secrets.token_hex(24),
            mode="simulate",
            backend="simulate",
            interface="wan0",
            status="pending",
        )
    )
    db.session.add(
        Alert(
            user_id=user.id,
            category="network",
            severity="medium",
            title="Network Guard awaiting edge agent",
            detail=(
                "Deploy the Lockwell Network Guard agent on your router/firewall "
                "host so hostile packets can be dropped before they forward into the LAN."
            ),
            source="Network Guard",
        )
    )
    audit(user.id, "seed", "Demo monitoring profile initialized")


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "service": "lockwell", "version": "0.1.0"})


@app.post("/api/auth/register")
def register():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    display_name = (data.get("displayName") or "").strip() or email.split("@")[0]

    if not email or "@" not in email:
        return jsonify({"error": "Valid email required"}), 400
    if len(password) < 10:
        return jsonify({"error": "Password must be at least 10 characters"}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already registered"}), 409

    user = User(
        email=email,
        password_hash=generate_password_hash(password),
        display_name=display_name,
        vault_salt=secrets.token_hex(16),
    )
    db.session.add(user)
    db.session.flush()
    seed_demo_for_user(user)
    token = issue_session(user)
    audit(user.id, "auth.register", "Account created")
    db.session.commit()
    return jsonify({"token": token, "user": serialize_user(user)}), 201


@app.post("/api/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "Invalid email or password"}), 401
    token = issue_session(user)
    audit(user.id, "auth.login", "Signed in")
    db.session.commit()
    return jsonify({"token": token, "user": serialize_user(user)})


@app.post("/api/auth/logout")
def logout():
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth.split(" ", 1)[1].strip()
        session = Session.query.filter_by(token=token).first()
        if session:
            audit(session.user_id, "auth.logout", "Signed out")
            db.session.delete(session)
            db.session.commit()
    return jsonify({"ok": True})


@app.get("/api/me")
def me():
    denied = require_user()
    if denied:
        return denied
    return jsonify({"user": serialize_user(g.user)})


@app.get("/api/dashboard")
def dashboard():
    denied = require_user()
    if denied:
        return denied
    user = g.user
    open_alerts = Alert.query.filter_by(user_id=user.id, acknowledged=False).count()
    high_alerts = Alert.query.filter_by(
        user_id=user.id, acknowledged=False, severity="high"
    ).count()
    monitored = MonitoredItem.query.filter_by(user_id=user.id).count()
    devices = Device.query.filter_by(user_id=user.id).all()
    device_score = 0
    checks = 0
    for device in devices:
        for flag in (
            device.vpn_enabled,
            device.antivirus_enabled,
            device.screen_lock_enabled,
            device.updates_current,
        ):
            checks += 1
            if flag:
                device_score += 1
    protection = int((device_score / checks) * 100) if checks else 0
    recent = (
        Alert.query.filter_by(user_id=user.id)
        .order_by(Alert.created_at.desc())
        .limit(5)
        .all()
    )
    blocked_packets = (
        db.session.query(db.func.coalesce(db.func.sum(GuardNode.packets_blocked), 0))
        .filter(GuardNode.user_id == user.id)
        .scalar()
    )
    return jsonify(
        {
            "summary": {
                "openAlerts": open_alerts,
                "highSeverity": high_alerts,
                "monitoredItems": monitored,
                "deviceProtectionScore": protection,
                "vaultMode": "zero-knowledge",
                "networkPacketsBlocked": int(blocked_packets or 0),
            },
            "recentAlerts": [serialize_alert(a) for a in recent],
            "devices": [serialize_device(d) for d in devices],
        }
    )


@app.get("/api/alerts")
def list_alerts():
    denied = require_user()
    if denied:
        return denied
    alerts = (
        Alert.query.filter_by(user_id=g.user.id)
        .order_by(Alert.created_at.desc())
        .all()
    )
    return jsonify({"alerts": [serialize_alert(a) for a in alerts]})


@app.post("/api/alerts/<int:alert_id>/ack")
def ack_alert(alert_id: int):
    denied = require_user()
    if denied:
        return denied
    alert = Alert.query.filter_by(id=alert_id, user_id=g.user.id).first()
    if not alert:
        return jsonify({"error": "Alert not found"}), 404
    alert.acknowledged = True
    audit(g.user.id, "alert.ack", f"Acknowledged alert #{alert.id}")
    db.session.commit()
    return jsonify({"alert": serialize_alert(alert)})


@app.get("/api/monitored")
def list_monitored():
    denied = require_user()
    if denied:
        return denied
    items = (
        MonitoredItem.query.filter_by(user_id=g.user.id)
        .order_by(MonitoredItem.created_at.desc())
        .all()
    )
    return jsonify({"items": [serialize_monitored(i) for i in items]})


@app.post("/api/monitored")
def add_monitored():
    denied = require_user()
    if denied:
        return denied
    data = request.get_json(silent=True) or {}
    kind = (data.get("kind") or "").strip().lower()
    label = (data.get("label") or "").strip()
    value = (data.get("value") or "").strip()
    allowed = {"email", "phone", "card", "ssn", "bank", "passport", "license"}
    if kind not in allowed:
        return jsonify({"error": "Unsupported monitor kind"}), 400
    if not label or not value:
        return jsonify({"error": "Label and value required"}), 400

    item = MonitoredItem(
        user_id=g.user.id,
        kind=kind,
        label=label,
        value_hash=hash_monitor_value(value),
        display_mask=mask_value(kind, value),
        status="clear",
    )
    db.session.add(item)
    audit(g.user.id, "monitor.add", f"Added {kind} monitor")
    db.session.commit()
    return jsonify({"item": serialize_monitored(item)}), 201


@app.get("/api/vault")
def get_vault():
    denied = require_user()
    if denied:
        return denied
    entries = (
        VaultEntry.query.filter_by(user_id=g.user.id)
        .order_by(VaultEntry.updated_at.desc())
        .all()
    )
    return jsonify(
        {
            "vaultSalt": g.user.vault_salt,
            "entries": [serialize_vault(e) for e in entries],
        }
    )


@app.post("/api/vault")
def upsert_vault():
    denied = require_user()
    if denied:
        return denied
    data = request.get_json(silent=True) or {}
    ciphertext = data.get("ciphertext")
    iv = data.get("iv")
    entry_id = data.get("id")
    if not ciphertext or not iv:
        return jsonify({"error": "ciphertext and iv required"}), 400

    if entry_id:
        entry = VaultEntry.query.filter_by(id=entry_id, user_id=g.user.id).first()
        if not entry:
            return jsonify({"error": "Vault entry not found"}), 404
        entry.ciphertext = ciphertext
        entry.iv = iv
        entry.updated_at = utcnow()
        action = "vault.update"
    else:
        entry = VaultEntry(user_id=g.user.id, ciphertext=ciphertext, iv=iv)
        db.session.add(entry)
        action = "vault.create"

    audit(g.user.id, action, "Ciphertext vault write (server cannot decrypt)")
    db.session.commit()
    return jsonify({"entry": serialize_vault(entry)})


@app.delete("/api/vault/<int:entry_id>")
def delete_vault(entry_id: int):
    denied = require_user()
    if denied:
        return denied
    entry = VaultEntry.query.filter_by(id=entry_id, user_id=g.user.id).first()
    if not entry:
        return jsonify({"error": "Vault entry not found"}), 404
    db.session.delete(entry)
    audit(g.user.id, "vault.delete", f"Deleted vault entry #{entry_id}")
    db.session.commit()
    return jsonify({"ok": True})


@app.get("/api/devices")
def list_devices():
    denied = require_user()
    if denied:
        return denied
    devices = Device.query.filter_by(user_id=g.user.id).all()
    return jsonify({"devices": [serialize_device(d) for d in devices]})


@app.patch("/api/devices/<int:device_id>")
def update_device(device_id: int):
    denied = require_user()
    if denied:
        return denied
    device = Device.query.filter_by(id=device_id, user_id=g.user.id).first()
    if not device:
        return jsonify({"error": "Device not found"}), 404
    data = request.get_json(silent=True) or {}
    for field in (
        "vpn_enabled",
        "antivirus_enabled",
        "screen_lock_enabled",
        "updates_current",
    ):
        camel = "".join(
            part.capitalize() if i else part
            for i, part in enumerate(field.split("_"))
        )
        if camel in data:
            setattr(device, field, bool(data[camel]))
        elif field in data:
            setattr(device, field, bool(data[field]))
    device.last_check_in = utcnow()
    audit(g.user.id, "device.update", f"Updated device {device.name}")
    db.session.commit()
    return jsonify({"device": serialize_device(device)})


@app.get("/api/audit")
def list_audit():
    denied = require_user()
    if denied:
        return denied
    events = (
        AuditEvent.query.filter_by(user_id=g.user.id)
        .order_by(AuditEvent.created_at.desc())
        .limit(100)
        .all()
    )
    return jsonify(
        {
            "events": [
                {
                    "id": e.id,
                    "action": e.action,
                    "detail": e.detail,
                    "createdAt": e.created_at.isoformat(),
                }
                for e in events
            ]
        }
    )


@app.get("/api/architecture")
def architecture():
    return jsonify(
        {
            "product": "Lockwell",
            "principles": [
                "Zero-knowledge vault: encryption keys never leave the browser",
                "Hashed monitoring: raw identity values are not stored in plaintext",
                "Transparent audit trail for every sensitive account action",
                "Least privilege API tokens scoped to a single session",
                "Defense-in-depth device posture scoring",
                "Network Guard sits on the edge gateway to drop hostile packets before LAN forward",
            ],
            "mvpLimits": [
                "Breach and dark-web alerts are simulated for the demo corpus",
                "Credit bureau feeds and insurance require licensed partners",
                "Device antivirus/VPN toggles are posture controls, not full endpoint agents",
                "True packet blocking requires deploying the agent on a gateway/firewall host",
                "Demo mode uses synthetic packet metadata; enforce mode needs nftables privileges",
            ],
        }
    )


@app.get("/api/network/summary")
def network_summary():
    denied = require_user()
    if denied:
        return denied
    user = g.user
    nodes = GuardNode.query.filter_by(user_id=user.id).all()
    events = (
        NetworkEvent.query.filter_by(user_id=user.id)
        .order_by(NetworkEvent.created_at.desc())
        .limit(25)
        .all()
    )
    blocks = (
        BlockRule.query.filter_by(user_id=user.id, active=True)
        .order_by(BlockRule.created_at.desc())
        .all()
    )
    return jsonify(
        {
            "summary": {
                "nodes": len(nodes),
                "onlineNodes": sum(1 for n in nodes if n.status == "online"),
                "packetsSeen": sum(n.packets_seen for n in nodes),
                "packetsBlocked": sum(n.packets_blocked for n in nodes),
                "activeBlocks": len(blocks),
            },
            "nodes": [serialize_guard_node(n, include_token=True) for n in nodes],
            "events": [serialize_network_event(e) for e in events],
            "blocks": [serialize_block_rule(b) for b in blocks],
        }
    )


@app.post("/api/network/nodes")
def create_guard_node():
    denied = require_user()
    if denied:
        return denied
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip() or "Edge gateway"
    node = GuardNode(
        user_id=g.user.id,
        name=name,
        agent_token=secrets.token_hex(24),
        mode=(data.get("mode") or "simulate").strip(),
        interface=(data.get("interface") or "any").strip(),
        status="pending",
    )
    db.session.add(node)
    audit(g.user.id, "network.node.create", f"Created guard node {name}")
    db.session.commit()
    return jsonify({"node": serialize_guard_node(node, include_token=True)}), 201


@app.get("/api/network/events")
def list_network_events():
    denied = require_user()
    if denied:
        return denied
    events = (
        NetworkEvent.query.filter_by(user_id=g.user.id)
        .order_by(NetworkEvent.created_at.desc())
        .limit(200)
        .all()
    )
    return jsonify({"events": [serialize_network_event(e) for e in events]})


@app.get("/api/network/blocks")
def list_blocks():
    denied = require_user()
    if denied:
        return denied
    blocks = (
        BlockRule.query.filter_by(user_id=g.user.id)
        .order_by(BlockRule.created_at.desc())
        .all()
    )
    return jsonify({"blocks": [serialize_block_rule(b) for b in blocks]})


@app.post("/api/network/blocks")
def create_block():
    denied = require_user()
    if denied:
        return denied
    data = request.get_json(silent=True) or {}
    ip = (data.get("ip") or "").strip()
    reason = (data.get("reason") or "Manual block").strip()
    if not ip:
        return jsonify({"error": "ip required"}), 400
    existing = BlockRule.query.filter_by(user_id=g.user.id, ip=ip, active=True).first()
    if existing:
        return jsonify({"block": serialize_block_rule(existing)})
    block = BlockRule(user_id=g.user.id, ip=ip, reason=reason, active=True)
    db.session.add(block)
    audit(g.user.id, "network.block", f"Blocked {ip}")
    db.session.commit()
    return jsonify({"block": serialize_block_rule(block)}), 201


@app.delete("/api/network/blocks/<int:block_id>")
def delete_block(block_id: int):
    denied = require_user()
    if denied:
        return denied
    block = BlockRule.query.filter_by(id=block_id, user_id=g.user.id).first()
    if not block:
        return jsonify({"error": "Block not found"}), 404
    block.active = False
    audit(g.user.id, "network.unblock", f"Unblocked {block.ip}")
    db.session.commit()
    return jsonify({"ok": True, "block": serialize_block_rule(block)})


@app.post("/api/network/agent/heartbeat")
def agent_heartbeat():
    node, error = require_guard_node()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    node.packets_seen = int(data.get("packetsSeen", node.packets_seen) or 0)
    node.packets_blocked = int(data.get("packetsBlocked", node.packets_blocked) or 0)
    node.mode = (data.get("mode") or node.mode)[:20]
    node.backend = (data.get("backend") or node.backend)[:40]
    node.interface = (data.get("interface") or node.interface)[:80]
    node.status = (data.get("status") or "online")[:20]
    node.last_seen_at = utcnow()
    db.session.commit()
    return jsonify({"ok": True, "node": serialize_guard_node(node)})


@app.post("/api/network/agent/events")
def agent_events():
    node, error = require_guard_node()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    events = data.get("events") or []
    created = 0
    for item in events[:100]:
        src_ip = (item.get("srcIp") or item.get("src_ip") or "").strip()
        if not src_ip:
            continue
        action = (item.get("action") or "logged").strip()
        title = (item.get("title") or "Network event")[:200]
        detail = item.get("detail") or ""
        event = NetworkEvent(
            user_id=node.user_id,
            guard_node_id=node.id,
            category=(item.get("category") or "network")[:40],
            severity=(item.get("severity") or "medium")[:20],
            title=title,
            detail=detail,
            src_ip=src_ip[:64],
            dst_ip=(item.get("dstIp") or item.get("dst_ip") or "")[:64],
            dst_port=int(item.get("dstPort") or item.get("dst_port") or 0),
            protocol=(item.get("protocol") or "TCP")[:20],
            action=action[:20],
        )
        db.session.add(event)
        created += 1

        if action == "blocked":
            block = BlockRule.query.filter_by(
                user_id=node.user_id, ip=src_ip, active=True
            ).first()
            if block:
                block.hits += 1
            else:
                db.session.add(
                    BlockRule(
                        user_id=node.user_id,
                        ip=src_ip,
                        reason=title,
                        active=True,
                        hits=1,
                    )
                )
            db.session.add(
                Alert(
                    user_id=node.user_id,
                    category="network",
                    severity=(item.get("severity") or "high")[:20],
                    title=title,
                    detail=detail,
                    source="Network Guard",
                )
            )

    node.last_seen_at = utcnow()
    node.status = "online"
    db.session.commit()
    return jsonify({"ok": True, "accepted": created})


@app.get("/api/network/agent/blocklist")
def agent_blocklist():
    node, error = require_guard_node()
    if error:
        return error
    blocks = BlockRule.query.filter_by(user_id=node.user_id, active=True).all()
    return jsonify({"blocks": [serialize_block_rule(b) for b in blocks]})


def serialize_user(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "displayName": user.display_name,
        "vaultSalt": user.vault_salt,
        "createdAt": user.created_at.isoformat(),
    }


def serialize_alert(alert: Alert) -> dict:
    return {
        "id": alert.id,
        "category": alert.category,
        "severity": alert.severity,
        "title": alert.title,
        "detail": alert.detail,
        "source": alert.source,
        "acknowledged": alert.acknowledged,
        "createdAt": alert.created_at.isoformat(),
    }


def serialize_monitored(item: MonitoredItem) -> dict:
    return {
        "id": item.id,
        "kind": item.kind,
        "label": item.label,
        "displayMask": item.display_mask,
        "status": item.status,
        "createdAt": item.created_at.isoformat(),
    }


def serialize_vault(entry: VaultEntry) -> dict:
    return {
        "id": entry.id,
        "ciphertext": entry.ciphertext,
        "iv": entry.iv,
        "createdAt": entry.created_at.isoformat(),
        "updatedAt": entry.updated_at.isoformat(),
    }


def serialize_device(device: Device) -> dict:
    return {
        "id": device.id,
        "name": device.name,
        "platform": device.platform,
        "vpnEnabled": device.vpn_enabled,
        "antivirusEnabled": device.antivirus_enabled,
        "screenLockEnabled": device.screen_lock_enabled,
        "updatesCurrent": device.updates_current,
        "lastCheckIn": device.last_check_in.isoformat(),
    }


def serialize_guard_node(node: GuardNode, include_token: bool = False) -> dict:
    payload = {
        "id": node.id,
        "name": node.name,
        "mode": node.mode,
        "backend": node.backend,
        "interface": node.interface,
        "status": node.status,
        "packetsSeen": node.packets_seen,
        "packetsBlocked": node.packets_blocked,
        "lastSeenAt": node.last_seen_at.isoformat() if node.last_seen_at else None,
        "createdAt": node.created_at.isoformat(),
    }
    if include_token:
        payload["agentToken"] = node.agent_token
    return payload


def serialize_network_event(event: NetworkEvent) -> dict:
    return {
        "id": event.id,
        "guardNodeId": event.guard_node_id,
        "category": event.category,
        "severity": event.severity,
        "title": event.title,
        "detail": event.detail,
        "srcIp": event.src_ip,
        "dstIp": event.dst_ip,
        "dstPort": event.dst_port,
        "protocol": event.protocol,
        "action": event.action,
        "createdAt": event.created_at.isoformat(),
    }


def serialize_block_rule(block: BlockRule) -> dict:
    return {
        "id": block.id,
        "ip": block.ip,
        "reason": block.reason,
        "active": block.active,
        "hits": block.hits,
        "createdAt": block.created_at.isoformat(),
    }


with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
