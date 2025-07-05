from flask import Flask, render_template, request, redirect, url_for, session, flash
import boto3
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "your_secret")

# AWS Configuration
dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION'))
sns = boto3.client('sns', region_name=os.getenv('AWS_REGION'))

# DynamoDB Tables
users_table = dynamodb.Table('medtrack_users')
appointments_table = dynamodb.Table('medtrack_appointments')
prescriptions_table = dynamodb.Table('medtrack_prescriptions')
reminders_table = dynamodb.Table('medtrack_reminders')

SNS_TOPIC_ARN = os.getenv("SNS_TOPIC_ARN")

# Routes

@app.route('/')
def home():
    return render_template("index.html")

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = {
            'email': request.form['email'],
            'password': request.form['password'],
            'name': request.form['name'],
            'user_type': 'patient'
        }
        try:
            users_table.put_item(Item=data)
            flash("Registration successful!", "success")
            return redirect(url_for('login'))
        except:
            flash("Error registering user.", "danger")
    return render_template("register.html")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        resp = users_table.get_item(Key={'email': email})
        user = resp.get('Item')

        if user and user['password'] == password and user['user_type'] == 'patient':
            session['user_email'] = user['email']
            session['user_name'] = user['name']
            session['user_type'] = user['user_type']
            return redirect(url_for('patient_dashboard'))
        flash("Invalid credentials", "danger")
    return render_template("login.html")

@app.route('/doctor_login', methods=['GET', 'POST'])
def doctor_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        resp = users_table.get_item(Key={'email': email})
        user = resp.get('Item')

        if user and user['password'] == password and user['user_type'] == 'doctor':
            session['user_email'] = user['email']
            session['user_name'] = user['name']
            session['user_type'] = user['user_type']
            return redirect(url_for('doctor_dashboard'))
        flash("Invalid credentials", "danger")
    return render_template("doctor_login.html")

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

# Patient Panel
@app.route('/patient_dashboard')
def patient_dashboard():
    if 'user_email' not in session or session['user_type'] != 'patient':
        return redirect(url_for('login'))
    return render_template("patient_dashboard.html")

@app.route('/book_appointment', methods=['GET', 'POST'])
def book_appointment():
    if 'user_email' not in session or session['user_type'] != 'patient':
        return redirect(url_for('login'))
    if request.method == 'POST':
        item = {
            'patient_email': session['user_email'],
            'doctor_email': request.form['doctor_email'],
            'date': request.form['date'],
            'time': request.form['time'],
            'reason': request.form['reason'],
            'status': 'Pending',
            'prescribed': False
        }
        appointments_table.put_item(Item=item)
        flash("Appointment booked successfully", "success")
        return redirect(url_for('patient_dashboard'))
    return render_template("appointment.html")

@app.route('/prescriptions')
def prescriptions():
    if 'user_email' not in session or session['user_type'] != 'patient':
        return redirect(url_for('login'))
    response = prescriptions_table.scan()
    prescriptions = [p for p in response.get('Items', []) if p['patient_email'] == session['user_email']]
    return render_template("prescriptions.html", prescriptions=prescriptions)

@app.route('/reminders', methods=['GET', 'POST'])
def reminders():
    if 'user_email' not in session or session['user_type'] != 'patient':
        return redirect(url_for('login'))
    if request.method == 'POST':
        message = request.form['message']
        time = request.form['time']
        patient_email = session['user_email']

        reminder = {
            'patient_email': patient_email,
            'message': message,
            'time': time
        }
        reminders_table.put_item(Item=reminder)

        # Send SNS
        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Message=f"Reminder from MedTrack+: {message} at {time}",
            Subject="MedTrack+ Reminder"
        )
        flash("Reminder set and SNS notification sent!", "success")
        return redirect(url_for('reminders'))

    response = reminders_table.scan()
    user_reminders = [r for r in response.get('Items', []) if r['patient_email'] == session['user_email']]
    return render_template("reminders.html", reminders=user_reminders)

@app.route('/patient_profile')
def patient_profile():
    if 'user_email' not in session or session['user_type'] != 'patient':
        return redirect(url_for('login'))
    return render_template("patient_profile.html")

# Doctor Panel
@app.route('/doctor_dashboard')
def doctor_dashboard():
    if 'user_email' not in session or session['user_type'] != 'doctor':
        return redirect(url_for('doctor_login'))

    email = session['user_email']
    response = appointments_table.scan()
    appointments = [a for a in response.get('Items', []) if a['doctor_email'] == email]

    return render_template("doctor_dashboard.html", appointments=appointments)

@app.route('/doctor_appointments')
def doctor_appointments():
    if 'user_email' not in session or session['user_type'] != 'doctor':
        return redirect(url_for('doctor_login'))

    email = session['user_email']
    response = appointments_table.scan()
    appointments = [a for a in response.get('Items', []) if a['doctor_email'] == email]
    return render_template("doctor_appointments.html", appointments=appointments)

@app.route('/doctor_prescriptions')
def doctor_prescriptions():
    if 'user_email' not in session or session['user_type'] != 'doctor':
        return redirect(url_for('doctor_login'))

    email = session['user_email']
    response = prescriptions_table.scan()
    prescriptions = [p for p in response.get('Items', []) if p.get('doctor_email') == email]
    return render_template("doctor_prescriptions.html", prescriptions=prescriptions)

@app.route('/add_prescription', methods=['GET', 'POST'])
def add_prescription():
    if 'user_email' not in session or session['user_type'] != 'doctor':
        return redirect(url_for('doctor_login'))

    patient_email = request.args.get('email')
    if request.method == 'POST':
        data = {
            'patient_email': patient_email,
            'doctor_email': session['user_email'],
            'medication': request.form['medication'],
            'dosage': request.form['dosage'],
            'frequency': request.form['frequency'],
            'instructions': request.form['instructions'],
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        prescriptions_table.put_item(Item=data)

        # Update appointment to prescribed
        response = appointments_table.scan()
        for item in response.get('Items', []):
            if item['patient_email'] == patient_email and item['doctor_email'] == session['user_email']:
                appointments_table.delete_item(Key={
                    'patient_email': item['patient_email'],
                    'doctor_email': item['doctor_email']
                })
                item['prescribed'] = True
                appointments_table.put_item(Item=item)
                break

        flash("Prescription added successfully", "success")
        return redirect(url_for('doctor_dashboard'))

    return render_template("add_prescription.html", patient_email=patient_email)

@app.route('/doctor_profile')
def doctor_profile():
    if 'user_email' not in session or session['user_type'] != 'doctor':
        return redirect(url_for('doctor_login'))
    return render_template("doctor_profile.html")


if __name__ == "__main__":
    app.run(debug=True)
