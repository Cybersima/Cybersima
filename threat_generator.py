import time
import random
from app import db, Threat

types = ['Anomaly', 'Malware', 'Unauthorized Access']
severities = ['Low', 'Medium', 'High']

while True:
    new_threat = Threat(
        type=random.choice(types),
        time=time.strftime("%I:%M %p"),
        severity=random.choice(severities)
    )
    db.session.add(new_threat)
    db.session.commit()
    print(f"Added threat: {new_threat.type} at {new_threat.time}")
    time.sleep(10)
