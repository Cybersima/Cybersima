"""Optional demo alert injector for Lockwell local development."""

from __future__ import annotations

import random
import time

from app import Alert, User, app, audit, db, utcnow

CATEGORIES = [
    (
        "breach",
        "high",
        "New breach corpus match",
        "A monitored credential hash matched an updated breach set.",
    ),
    (
        "darkweb",
        "medium",
        "Paste-site exposure",
        "Simulated dark-web monitor found a matching identifier hash.",
    ),
    (
        "device",
        "low",
        "Device posture drift",
        "A enrolled device reported a weakened protection control.",
    ),
]


def main() -> None:
    with app.app_context():
        while True:
            user = User.query.order_by(User.id.asc()).first()
            if user:
                category, severity, title, detail = random.choice(CATEGORIES)
                alert = Alert(
                    user_id=user.id,
                    category=category,
                    severity=severity,
                    title=title,
                    detail=detail,
                    source="Demo Injector",
                    created_at=utcnow(),
                )
                db.session.add(alert)
                audit(user.id, "alert.inject", title)
                db.session.commit()
                print(f"Injected {severity} {category} alert for user {user.id}")
            else:
                print("No users yet; waiting...")
            time.sleep(30)


if __name__ == "__main__":
    main()
