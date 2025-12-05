from flask import Flask, render_template, redirect, url_for, request, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///smart_pg.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

# ---- Models (kept here for single-file simplicity) ----
class Role:
    OWNER = 'owner'
    MANAGER = 'manager'
    TENANT = 'tenant'

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120))
    email = db.Column(db.String(150), unique=True, nullable=False)
    phone = db.Column(db.String(30))
    password_hash = db.Column(db.String(255))
    role = db.Column(db.String(50), default=Role.MANAGER)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

class PG(db.Model):
    # default table name will be 'pg' (lowercase)
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150))
    address = db.Column(db.Text)

class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # <-- FIX: use lowercase table name 'pg' to match PG's default table name
    pg_id = db.Column(db.Integer, db.ForeignKey('pg.id'), nullable=True)
    room_no = db.Column(db.String(50))
    room_type = db.Column(db.String(50))
    total_beds = db.Column(db.Integer, default=1)
    rent_per_bed = db.Column(db.Float, default=0.0)

    pg = db.relationship('PG', backref='rooms')

class Tenant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150))
    phone = db.Column(db.String(30))
    email = db.Column(db.String(150))
    id_type = db.Column(db.String(50))
    id_number = db.Column(db.String(150))
    address = db.Column(db.Text)
    created_at = db.Column(db.Date, default=date.today)

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'))
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'))
    bed_no = db.Column(db.Integer, default=1)
    checkin_date = db.Column(db.Date, default=date.today)
    checkout_date = db.Column(db.Date, nullable=True)
    deposit_amount = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(30), default='Active')

    tenant = db.relationship('Tenant', backref='bookings')
    room = db.relationship('Room', backref='bookings')

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('booking.id'))
    amount = db.Column(db.Float)
    payment_date = db.Column(db.Date, default=date.today)
    mode = db.Column(db.String(50))
    txn_ref = db.Column(db.String(200))
    remarks = db.Column(db.String(255))

    booking = db.relationship('Booking', backref='payments')

# ---- Login loader ----
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ---- Routes ----
@app.route('/')
@login_required
def index():
    # Simple dashboard metrics
    total_rooms = Room.query.count()
    total_tenants = Tenant.query.count()
    active_bookings = Booking.query.filter_by(status='Active').count()
    total_income = db.session.query(db.func.coalesce(db.func.sum(Payment.amount), 0)).scalar()
    return render_template('index.html', total_rooms=total_rooms, total_tenants=total_tenants,
                           active_bookings=active_bookings, total_income=total_income)

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        pw = request.form['password']
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'danger')
            return redirect(url_for('register'))
        user = User(name=name, email=email, role=Role.MANAGER)
        user.set_password(pw)
        db.session.add(user)
        db.session.commit()
        flash('Registered. Please login.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        pw = request.form['password']
        # debug prints can be enabled temporarily if needed:
        # print("Login attempt for:", email)
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(pw):
            login_user(user)
            flash('Logged in successfully', 'success')
            return redirect(url_for('index'))
        flash('Invalid credentials', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out', 'info')
    return redirect(url_for('login'))

# Tenants
@app.route('/tenants')
@login_required
def tenants():
    tenants = Tenant.query.order_by(Tenant.created_at.desc()).all()
    return render_template('tenants.html', tenants=tenants)

@app.route('/tenants/add', methods=['GET','POST'])
@login_required
def add_tenant():
    if request.method == 'POST':
        t = Tenant(
            name=request.form['name'],
            phone=request.form['phone'],
            email=request.form.get('email'),
            id_type=request.form.get('id_type'),
            id_number=request.form.get('id_number'),
            address=request.form.get('address')
        )
        db.session.add(t)
        db.session.commit()
        flash('Tenant added', 'success')
        return redirect(url_for('tenants'))
    return render_template('add_tenant.html')

# Rooms + Bookings
@app.route('/bookings')
@login_required
def bookings():
    bookings = Booking.query.order_by(Booking.checkin_date.desc()).all()
    return render_template('bookings.html', bookings=bookings)

@app.route('/bookings/add', methods=['GET','POST'])
@login_required
def add_booking():
    if request.method == 'POST':
        tenant_id = int(request.form['tenant_id'])
        room_id = int(request.form['room_id'])
        deposit = float(request.form.get('deposit', 0))
        bed_no = int(request.form.get('bed_no', 1))
        b = Booking(tenant_id=tenant_id, room_id=room_id, deposit_amount=deposit, bed_no=bed_no)
        db.session.add(b)
        db.session.commit()
        flash('Booking created', 'success')
        return redirect(url_for('bookings'))
    tenants = Tenant.query.all()
    rooms = Room.query.all()
    return render_template('add_booking.html', tenants=tenants, rooms=rooms)

# Payments
@app.route('/payments')
@login_required
def payments():
    payments = Payment.query.order_by(Payment.payment_date.desc()).all()
    return render_template('payments.html', payments=payments)

@app.route('/payments/add', methods=['POST'])
@login_required
def add_payment():
    booking_id = int(request.form['booking_id'])
    amount = float(request.form['amount'])
    mode = request.form.get('mode', 'Cash')
    txn = request.form.get('txn_ref', '')
    p = Payment(booking_id=booking_id, amount=amount, mode=mode, txn_ref=txn)
    db.session.add(p)
    db.session.commit()
    flash('Payment recorded', 'success')
    return redirect(url_for('payments'))

# ---- Utilities ----
@app.cli.command("init-db")
def init_db():
    """Initialize the DB and create a default user and sample data."""
    db.create_all()
    if not User.query.filter_by(email='owner@example.com').first():
        u = User(name='Owner', email='owner@example.com', role=Role.OWNER)
        u.set_password('ownerpass')
        db.session.add(u)

    if PG.query.count() == 0:
        pg = PG(name='Central PG', address='123, MG Road')
        db.session.add(pg)
        db.session.flush()
        r1 = Room(pg_id=pg.id, room_no='101', room_type='Single', total_beds=1, rent_per_bed=6000)
        r2 = Room(pg_id=pg.id, room_no='102', room_type='Double', total_beds=2, rent_per_bed=4000)
        db.session.add_all([r1, r2])
    db.session.commit()
    print("DB initialized with sample data. Owner login: owner@example.com / ownerpass")

if __name__ == '__main__':
    app.run(debug=True)
