from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///threats.db'
db = SQLAlchemy(app)

class Threat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(50))
    time = db.Column(db.String(20))
    severity = db.Column(db.String(10))

@app.before_first_request
def create_tables():
    db.create_all()

@app.route('/api/threats')
def get_threats():
    threats = Threat.query.all()
    return jsonify([{
        'type': t.type,
        'time': t.time,
        'severity': t.severity
    } for t in threats])

if __name__ == '__main__':
    app.run(debug=True)
