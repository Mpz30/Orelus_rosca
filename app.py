from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta, date
import calendar

app = Flask(__name__)
app.secret_key = "secret-key"

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///rosca.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# -------------------- MODELS --------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))
    is_admin = db.Column(db.Boolean, default=False)

    # Rosca participation flags
    rosca1 = db.Column(db.Boolean, default=False)
    rosca2 = db.Column(db.Boolean, default=False)

    # Separate contribution amounts
    contribution_amount_rosca1 = db.Column(db.Float, default=0)
    contribution_amount_rosca2 = db.Column(db.Float, default=0)

    # Relationships
    payments = db.relationship('Payment', backref='user', cascade="all, delete-orphan")
    paydays = db.relationship('Payday', backref='user', cascade="all, delete-orphan")


class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    date = db.Column(db.String(20))  # YYYY-MM-DD
    paid = db.Column(db.Boolean, default=False)
    rosca = db.Column(db.Integer, default=1)  # 1 for Rosca 1, 2 for Rosca 2


class Payday(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.String(20))  # YYYY-MM-DD
    amount = db.Column(db.Float)

    #  ADD THIS LINE ONLY
    rosca_value = db.Column(db.Integer, nullable=False, default=1)

    # Keep this exactly as you had it
    user_obj = db.relationship('User', backref=db.backref('payday_entries', lazy=True))


    # new model

class RoscaTemplate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rosca_number = db.Column(db.Integer, nullable=False)  # 1 or 2
    start_date = db.Column(db.String(10), nullable=False)  # YYYY-MM-DD
    end_date = db.Column(db.String(10), nullable=False)    # YYYY-MM-DD

    # Optional: store created_at
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# -------------------- INIT --------------------
def create_tables():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', password='admin', is_admin=True)
        db.session.add(admin)
        db.session.commit()


# -------------------- LOGIN --------------------
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(
            username=request.form['username'],
            password=request.form['password']
        ).first()

        if user:
            session['user_id'] = user.id
            session['is_admin'] = user.is_admin
            session['username'] = user.username
            return redirect(url_for('dashboard'))

    return render_template('login.html')


# -------------------- DASHBOARD --------------------
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    now = datetime.now()
    months = list(calendar.month_name)[1:]

    paydays_by_month = {}
    rosca1_count = 0
    rosca2_count = 0
    next_payday = None

    if session.get('is_admin'):
        all_paydays = Payday.query.order_by(Payday.date).all()
        all_users = User.query.all()

        rosca1_count = sum(1 for u in all_users if u.rosca1)
        rosca2_count = sum(1 for u in all_users if u.rosca2)

        future_paydays = [p for p in all_paydays if datetime.strptime(p.date, "%Y-%m-%d") >= now]
        if future_paydays:
            next_payday = min(future_paydays, key=lambda p: p.date).date

        for m in range(1, 13):
            paydays_by_month[m] = []

        for p in all_paydays:
            user = User.query.get(p.user_id)
            month = int(p.date.split('-')[1])
            paydays_by_month[month].append({
                "username": user.username,
                "date": p.date,
                "amount": p.amount
            })

    # ------------------ CURRENT USER CALENDAR ------------------
    cal = None
    current_month = now.month
    current_year = now.year
    paid_days = {}
    contribution_days = {}

    if not session.get('is_admin'):
        user = User.query.get(session['user_id'])
        cal = calendar.Calendar(firstweekday=0).monthdayscalendar(current_year, current_month)

        # Fetch all payments for this month
        user_payments = []
        if user.rosca1:
            user_payments += Payment.query.filter_by(user_id=user.id, rosca=1).all()
        if user.rosca2:
            user_payments += Payment.query.filter_by(user_id=user.id, rosca=2).all()

        # Map paid days
        for p in user_payments:
            pay_date = datetime.strptime(p.date, "%Y-%m-%d")
            if pay_date.month == current_month and p.paid:
                paid_days[pay_date.day] = True

        # Map contribution amounts on Saturdays
        contribution_days = {}
        # Rosca 1
        if user.rosca1:
            for week in cal:
                for i, day in enumerate(week):
                    if day != 0:
                        day_date = datetime(current_year, current_month, day)
                        if day_date.weekday() == 5:  # Saturday
                            contribution_days[day] = user.contribution_amount_rosca1
        # Rosca 2 (merge if overlapping)
        if user.rosca2:
            for week in cal:
                for i, day in enumerate(week):
                    if day != 0:
                        day_date = datetime(current_year, current_month, day)
                        if day_date.weekday() == 5:  # Saturday
                            if day in contribution_days:
                                contribution_days[day] += user.contribution_amount_rosca2
                            else:
                                contribution_days[day] = user.contribution_amount_rosca2

    return render_template(
        'dashboard.html',
        username=session['username'],
        now=now,
        calendar=calendar,
        paydays_by_month=paydays_by_month,
        rosca1_count=rosca1_count,
        rosca2_count=rosca2_count,
        next_payday=next_payday,
        cal=cal,
        current_month=current_month,
        current_year=current_year,
        paid_days=paid_days,
        contribution_days=contribution_days
    )
# -------------------- CALENDAR --------------------
#@app.route('/calendar/<int:month>')
#def view_calendar(month):
   ### year = datetime.now().year
    #cal = calendar.monthcalendar(year, month)

    # Get all payments for this user
    #payments = Payment.query.filter_by(user_id=session['user_id']).all()

    # Pass the logged-in user
   # user = User.query.get(session['user_id'])

    # Pass current datetime as 'now'
    #now = datetime.now()

    #return render_template(
        #'calendar.html',
        #user=user,
        #cal=cal,
        #month=month,
        #year=year,
        #payments=payments,
        #username=session['username'],
        #calendar=calendar,
        #now=now  # <-- this fixes the undefined error
    #)

@app.route('/calendar')
def user_calendar():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = request.args.get('user_id')
    rosca_number = request.args.get('rosca_number', type=int)

    if session.get('is_admin') and user_id:
        user = User.query.get(user_id)
    else:
        user = User.query.get(session['user_id'])

    now = datetime.now()

    # Fetch payments for both Roscas if user has them
    payments_rosca1 = Payment.query.filter_by(user_id=user.id, rosca=1).all() if user.rosca1 else []
    payments_rosca2 = Payment.query.filter_by(user_id=user.id, rosca=2).all() if user.rosca2 else []

    # Get Rosca templates
    template1 = RoscaTemplate.query.filter_by(rosca_number=1).order_by(RoscaTemplate.created_at.desc()).first() if user.rosca1 else None
    template2 = RoscaTemplate.query.filter_by(rosca_number=2).order_by(RoscaTemplate.created_at.desc()).first() if user.rosca2 else None

    # Build months_by_year separately per Rosca
    def build_months(template):
        months_by_year = {}
        if template:
            start = datetime.strptime(template.start_date, "%Y-%m-%d")
            end = datetime.strptime(template.end_date, "%Y-%m-%d")
            current = start
            while current <= end:
                y, m = current.year, current.month
                months_by_year.setdefault(y, set()).add(m)
                if m == 12:
                    current = current.replace(year=y+1, month=1)
                else:
                    current = current.replace(month=m+1)
            months_by_year = {y: sorted(list(m)) for y, m in months_by_year.items()}
        return months_by_year

    months_by_year1 = build_months(template1)
    months_by_year2 = build_months(template2)

    return render_template(
        'calendar.html',
        user=user,
        now=now,
        calendar=calendar,
        payments_rosca1=payments_rosca1,
        payments_rosca2=payments_rosca2,
        months_by_year1=months_by_year1,
        months_by_year2=months_by_year2
    )
# -------------------- ADMIN PANEL --------------------
@app.route('/admin')
def admin():
    if not session.get('is_admin'):
        return redirect(url_for('dashboard'))

    users = User.query.filter_by(is_admin=False).all()
    now = datetime.now()

    # Pass all Rosca templates to the template
    rosca_templates = RoscaTemplate.query.order_by(RoscaTemplate.created_at.desc()).all()

    return render_template(
        'admin.html',
        users=users,
        now=now,
        rosca_templates=rosca_templates
    )

# -------------------- CREATE USER + AUTO CALENDAR (WITH ROSCA TEMPLATE) --------------------

from datetime import datetime, timedelta
from flask import flash, redirect, url_for, request, session

@app.route('/admin/create_user', methods=['POST'])
def create_user():
    if not session.get('is_admin'):
        return redirect(url_for('dashboard'))

    username = request.form['username']
    password = request.form['password']

    # Check for duplicate username
    if User.query.filter_by(username=username).first():
        flash(f"Username '{username}' already exists!", "danger")
        return redirect(url_for('admin'))

    # Determine which Roscas the user is part of
    rosca1 = 'rosca1' in request.form
    rosca2 = 'rosca2' in request.form

    # Safely parse contribution amounts
    contribution_amount_rosca1 = float(request.form.get('contribution_amount_rosca1') or 0)
    contribution_amount_rosca2 = float(request.form.get('contribution_amount_rosca2') or 0)

    # Create user
    user = User(
        username=username,
        password=password,
        rosca1=rosca1,
        rosca2=rosca2,
        contribution_amount_rosca1=contribution_amount_rosca1,
        contribution_amount_rosca2=contribution_amount_rosca2
    )
    db.session.add(user)
    db.session.commit()

    # ------------------ Assign Payment Calendar from RoscaTemplate ------------------
    def assign_calendar(user_id, rosca_number):
        template = (
            RoscaTemplate.query
            .filter_by(rosca_number=rosca_number)
            .order_by(RoscaTemplate.created_at.desc())
            .first()
        )
        if not template:
            return  # No template exists

        # Make Rosca immediately visible by storing its title/date somewhere for display
        rosca_display_title = f"Rosca {rosca_number}: from {template.start_date} - {template.end_date}"
        flash(f"{rosca_display_title} is ready.", "info")

        start = datetime.strptime(template.start_date, "%Y-%m-%d")
        end = datetime.strptime(template.end_date, "%Y-%m-%d")
        current = start

        while current <= end:
            date_str = current.strftime("%Y-%m-%d")
            exists = Payment.query.filter_by(user_id=user_id, rosca=rosca_number, date=date_str).first()
            if not exists:
                db.session.add(Payment(user_id=user_id, rosca=rosca_number, date=date_str, paid=False))
            current += timedelta(days=1)

    if rosca1:
        assign_calendar(user.id, 1)
    if rosca2:
        assign_calendar(user.id, 2)

    db.session.commit()

    flash(f"User '{username}' created successfully.", "success")
    return redirect(url_for('admin'))

# -------------------- EDIT USER --------------------
@app.route('/admin/edit_user/<int:user_id>', methods=['POST'])
def edit_user(user_id):
    if not session.get('is_admin'):
        return redirect(url_for('dashboard'))

    user = User.query.get(user_id)
    if user:
        contribution_amount = request.form.get('contribution_amount')
        if contribution_amount:
            try:
                user.contribution_amount = float(contribution_amount)
                db.session.commit()
            except ValueError:
                pass  # ignore invalid input

    return redirect(url_for('admin'))


# -------------------- VIEW USER (ADMIN) --------------------
@app.route('/admin/user/<int:user_id>')
def admin_user(user_id):
    if not session.get('is_admin'):
        return redirect(url_for('dashboard'))

    user = User.query.get(user_id)
    now = datetime.now()
    year = now.year

    # Fetch payments per Rosca
    payments_rosca1 = Payment.query.filter_by(user_id=user_id, rosca=1).all() if user.rosca1 else []
    payments_rosca2 = Payment.query.filter_by(user_id=user_id, rosca=2).all() if user.rosca2 else []

    return render_template(
        'admin_user.html',
        user=user,
        payments_rosca1=payments_rosca1,
        payments_rosca2=payments_rosca2,
        calendar=calendar,
        now=now,
        year=year
    )

# -------------------- RESET PASSWORD --------------------
@app.route('/admin/reset_password/<int:user_id>', methods=['POST'])
def reset_password(user_id):
    if not session.get('is_admin'):
        return redirect(url_for('dashboard'))

    user = User.query.get(user_id)
    if user:
        new_password = request.form['new_password']
        user.password = new_password
        db.session.commit()

    return redirect(url_for('admin'))


#--------------------- ADMIN DELETE USER-------------
@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    # Only allow admins
    if not session.get('is_admin'):
        return redirect(url_for('dashboard'))

    # Fetch the user
    user = User.query.get(user_id)
    if user:
        try:
            db.session.delete(user)
            db.session.commit()
            # Optional: flash message (make sure you have `from flask import flash`)
            # flash(f"User {user.username} has been deleted.", "success")
        except Exception as e:
            db.session.rollback()
            # Optional: flash(f"Error deleting user: {str(e)}", "danger")
            print(f"Error deleting user: {str(e)}")

    # Redirect back to your admin panel route
    return redirect(url_for('admin'))  # ← match your actual admin route name

# -------------------- MARK PAID --------------------
@app.route('/admin/mark_paid', methods=['POST'])
def mark_paid():
    if not session.get('is_admin'):
        return jsonify({'success': False})

    data = request.json

    payment = Payment.query.filter_by(
        user_id=data['user_id'],
        date=data['date'],
        rosca=data['rosca']
    ).first()

    if not payment:
        print("❌ Payment NOT found:", data)
        return jsonify({'success': False})

    payment.paid = not payment.paid
    db.session.commit()

    print("✅ Payment updated:", payment.user_id, payment.date, payment.rosca, payment.paid)

    return jsonify({
        'success': True,
        'paid': payment.paid
    })
# -------------------- PAYDAY --------------------
from datetime import datetime

@app.route('/payday')
def payday():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # Users list for admin dropdown
    users = User.query.filter_by(is_admin=False).all() if session.get('is_admin') else []

    if session.get('is_admin'):
        paydays = Payday.query.all()
    else:
        paydays = Payday.query.filter_by(user_id=session['user_id']).all()

    # Pass 'now' to the template
    return render_template('payday.html', paydays=paydays, username=session['username'], users=users, now=datetime.now())

    # -------------------- ADMIN ADD PAYDAY --------------------
@app.route('/admin/payday/add', methods=['POST'])
def admin_add_payday():
    if not session.get('is_admin'):
        return redirect(url_for('dashboard'))

    user_id = request.form['user_id']
    date = request.form['date']
    amount = float(request.form['amount'])
    rosca_value = int(request.form['rosca'])  # ✅ THIS IS THE FIX

    payday = Payday(
        user_id=user_id,
        date=date,
        amount=amount,
        rosca_value=rosca_value  # ✅ SAVE IT
    )

    db.session.add(payday)
    db.session.commit()
    return redirect(url_for('payday'))

# -------------------- ADMIN DELETE PAYDAY --------------------
@app.route('/admin/payday/delete/<int:payday_id>', methods=['POST'])
def admin_delete_payday(payday_id):
    if not session.get('is_admin'):
        return redirect(url_for('dashboard'))

    payday = Payday.query.get(payday_id)
    if payday:
        db.session.delete(payday)
        db.session.commit()
    return redirect(url_for('payday'))


# -------------------- EDIT PAYDAY --------------------
@app.route("/admin/payday/edit/<int:payday_id>", methods=["POST"])
def edit_payday(payday_id):
    if not session.get('is_admin'):
        return redirect(url_for('dashboard'))

    payday = Payday.query.get(payday_id)  # ✅ use Payday model
    if payday:
        # Map form fields
        payday.user_id = int(request.form.get("user_id"))
        payday.date = request.form.get("date")
        payday.amount = float(request.form.get("amount", 0))
        payday.rosca_value = int(request.form.get("rosca", 1))  # map 'rosca' from form to rosca_value
        db.session.commit()  # save changes

    return redirect(url_for('payday'))

# -------------------- ADMIN ADD MONTH OR YEAR --------------------
# -------------------- ADMIN ADD MONTH OR YEAR --------------------
@app.route('/admin/add_month', methods=['POST'])
def admin_add_month():
    if not session.get('is_admin'):
        return redirect(url_for('dashboard'))

    rosca_num = int(request.form['rosca'])
    add_type = request.form.get('add_type', 'month')  # 'month' or 'year'

    # Step 1: Get all users in this Rosca
    users = User.query.filter_by(**{f'rosca{rosca_num}': True}).all()
    if not users:
        return redirect(url_for('admin'))

    # Step 2: Get the latest template for this Rosca
    template = (
        RoscaTemplate.query
        .filter_by(rosca_number=rosca_num)
        .order_by(RoscaTemplate.created_at.desc())
        .first()
    )

    if template:
        end_date = datetime.strptime(template.end_date, "%Y-%m-%d")
    else:
        # If no template exists, start from current month
        today = datetime.now()
        end_date = datetime(today.year, today.month, 1)
        # Create a new template as placeholder
        template = RoscaTemplate(
            rosca_number=rosca_num,
            start_date=end_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d")
        )
        db.session.add(template)
        db.session.commit()

    # Step 3: Determine how many months to add
    months_to_add = 1 if add_type == 'month' else 12

    current_year = end_date.year
    current_month = end_date.month

    for _ in range(months_to_add):
        # Move to next month
        current_month += 1
        if current_month > 12:
            current_month = 1
            current_year += 1

        days_in_month = calendar.monthrange(current_year, current_month)[1]

        # Add payments for all users for this month
        for user in users:
            for day in range(1, days_in_month + 1):
                date_str = f"{current_year}-{current_month:02d}-{day:02d}"
                exists = Payment.query.filter_by(
                    user_id=user.id, rosca=rosca_num, date=date_str
                ).first()
                if not exists:
                    db.session.add(
                        Payment(user_id=user.id, rosca=rosca_num, date=date_str, paid=False)
                    )

    # Step 4: Update template end_date
    new_end_date = datetime(current_year, current_month, calendar.monthrange(current_year, current_month)[1])
    template.end_date = new_end_date.strftime("%Y-%m-%d")

    db.session.commit()
    return redirect(url_for('admin'))



# -------------------- ADMIN REMOVE MONTH/YEAR --------------------
#--------------------- ADMIN DELETE MONTH/YEAR-------------
@app.route('/admin/remove_month', methods=['POST'])
def admin_remove_month():
    if not session.get('is_admin'):
        return redirect(url_for('dashboard'))

    rosca_num = int(request.form['rosca'])
    remove_type = request.form.get('remove_type', 'month')  # 'month' or 'year'

    # Step 1: Get latest template for this Rosca
    template = (
        RoscaTemplate.query
        .filter_by(rosca_number=rosca_num)
        .order_by(RoscaTemplate.created_at.desc())
        .first()
    )

    if not template:
        return redirect(url_for('admin'))

    end_date = datetime.strptime(template.end_date, "%Y-%m-%d")
    months_to_remove = 1 if remove_type == 'month' else 12

    current_year = end_date.year
    current_month = end_date.month

    for _ in range(months_to_remove):
        # Delete all payments for this month
        Payment.query.filter(
            Payment.rosca == rosca_num,
            Payment.date.like(f"{current_year}-{current_month:02d}-%")
        ).delete()

        # Move to previous month
        current_month -= 1
        if current_month < 1:
            current_month = 12
            current_year -= 1

    # Update template end_date
    new_end_date = datetime(current_year, current_month, calendar.monthrange(current_year, current_month)[1])
    template.end_date = new_end_date.strftime("%Y-%m-%d")

    db.session.commit()
    return redirect(url_for('admin'))


# -------------------- CREATE ROSCA TEMPLATE --------------------
@app.route('/admin/create_rosca_template', methods=['POST'])
def create_rosca_template():
    if not session.get('is_admin'):
        return redirect(url_for('dashboard'))

    rosca_number = int(request.form['rosca_number'])
    start_date = request.form['start_date']
    end_date = request.form['end_date']

    # Validate dates
    if start_date > end_date:
        return "Error: Start date cannot be after end date", 400

    # Save template
    template = RoscaTemplate(
        rosca_number=rosca_number,
        start_date=start_date,
        end_date=end_date
    )
    db.session.add(template)
    db.session.commit()

    return redirect(url_for('admin'))

# -------------------- PRINT --------------------
@app.route('/print/<int:user_id>')
def print_calendar(user_id):
    month_param = request.args.get('month')
    rosca_param = request.args.get('rosca', type=int)  # ✅ NEW
    year = datetime.now().year

    user = User.query.get(user_id)

    # ✅ FILTER payments by selected Rosca
    if rosca_param:
        payments = Payment.query.filter_by(user_id=user_id, rosca=rosca_param).all()
    else:
        payments = Payment.query.filter_by(user_id=user_id).all()

    # ✅ FULL YEAR
    if not month_param:
        months = list(range(1, 13))

    elif month_param.isdigit():
        selected_month = int(month_param)
        payments = [p for p in payments if int(p.date.split('-')[1]) == selected_month]
        months = [selected_month]

    elif month_param == 'current':
        current_month = datetime.now().month
        payments = [p for p in payments if int(p.date.split('-')[1]) == current_month]
        months = [current_month]

    else:
        months = list(range(1, 13))

    # Organize payments by month
    month_payments = {}
    for m in months:
        month_payments[m] = [p for p in payments if int(p.date.split('-')[1]) == m]

    return render_template(
        'print.html',
        user=user,
        month_payments=month_payments,
        year=year,
        calendar=calendar,
        rosca=rosca_param  # ✅ PASS THIS
    )
# -------------------- LOGOUT --------------------
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# -------------------- RUN --------------------
if __name__ == '__main__':
    with app.app_context():
        create_tables()
    app.run(debug=True)