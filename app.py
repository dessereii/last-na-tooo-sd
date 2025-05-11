from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, make_response
import sqlite3, json
from datetime import datetime
import os
import io
import csv
from io import BytesIO
from fpdf import FPDF
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter



app = Flask(__name__)
app.secret_key = 'your_secret_key'
DB_NAME = 'database.db'

# database
def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()

        # Create tables if they don't exist
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            name TEXT NOT NULL,
                            email TEXT,
                            password TEXT NOT NULL,
                            role TEXT NOT NULL,
                            student_number TEXT,
                            admin_email TEXT)''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS attendance (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            student_number TEXT,
                            status TEXT,
                            timestamp TEXT)''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS quizzes (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            title TEXT,
                            assigned_to TEXT,
                            deadline TEXT,
                            questions TEXT,
                            type TEXT,
                            duration TEXT)''')  
        
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS assigned_quizzes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    quiz_id INTEGER,
                    student_number TEXT,
                    FOREIGN KEY (quiz_id) REFERENCES quizzes(id))''')


        cursor.execute('''CREATE TABLE IF NOT EXISTS quiz_responses (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            student_number TEXT,
                            quiz_id INTEGER,
                            answers TEXT,
                            score REAL)''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS exams (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            title TEXT NOT NULL,
                            description TEXT,
                            questions TEXT NOT NULL,
                            duration TEXT,
                            type TEXT)''')  
        cursor.execute('''CREATE TABLE IF NOT EXISTS assigned_exams (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            exam_id INTEGER,
                            student_number TEXT,
                            FOREIGN KEY (exam_id) REFERENCES exams(id))''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS exam_responses (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            student_number TEXT,
                            exam_id INTEGER,
                            answers TEXT,
                            score INTEGER,
                            FOREIGN KEY (exam_id) REFERENCES exams(id))''')


def alter_tables():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()

        try:
            cursor.execute("ALTER TABLE quizzes ADD COLUMN duration TEXT")
        except sqlite3.OperationalError:
            pass 

        try:
            cursor.execute("ALTER TABLE exams ADD COLUMN duration TEXT")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE exams ADD COLUMN type TEXT")
        except sqlite3.OperationalError:
            pass

def clean_duplicate_assignments():
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Clean duplicate quiz assignments
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS temp_assigned_quizzes AS
            SELECT DISTINCT quiz_id, student_number
            FROM assigned_quizzes
        """)
        cursor.execute("DROP TABLE assigned_quizzes")
        cursor.execute("ALTER TABLE temp_assigned_quizzes RENAME TO assigned_quizzes")
        
        # Clean duplicate exam assignments
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS temp_assigned_exams AS
            SELECT DISTINCT exam_id, student_number
            FROM assigned_exams
        """)
        cursor.execute("DROP TABLE assigned_exams")
        cursor.execute("ALTER TABLE temp_assigned_exams RENAME TO assigned_exams")
        
        conn.commit()
        
    print("Database cleaned of duplicate assignments")

def add_unique_constraints():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        # First clean up any existing duplicates
        clean_duplicate_assignments()
        
        # Then add unique constraints
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_assigned_quiz ON assigned_quizzes(quiz_id, student_number)")
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_assigned_exam ON assigned_exams(exam_id, student_number)")
        conn.commit()

init_db()
alter_tables()


# ------------------ Routes ------------------
@app.route('/')
def select_role():
    return render_template('select_role.html')

@app.route('/login/<role>', methods=['GET', 'POST'])
def login(role):
    if request.method == 'POST':
        email_or_number = request.form['email']
        password = request.form['password']
        
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            if role == 'student':
                cursor.execute("SELECT * FROM users WHERE student_number=? AND password=? AND role='student'", (email_or_number, password))
            else:
                cursor.execute("SELECT * FROM users WHERE email=? AND password=? AND role='admin'", (email_or_number, password))
            user = cursor.fetchone()
            if user:
                session['user_id'] = user[0]
                session['role'] = user[4].strip().lower()
                print("Logged in. Session now:", dict(session))  
                return redirect(url_for('admin_home') if role == 'admin' else url_for('student_home'))
            else:
                flash('Invalid credentials')

    return render_template('login.html', role=role)


@app.route('/signup/<role>', methods=['GET', 'POST'])
def signup(role):
    if request.method == 'POST':
        name = request.form['name']
        email = request.form.get('email')
        student_number = request.form.get('student_number')
        admin_email = request.form.get('admin_email')
        password = request.form['password']

        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute('''INSERT INTO users (name, email, password, role, student_number, admin_email)
                              VALUES (?, ?, ?, ?, ?, ?)''',
                           (name, email, password, role, student_number, admin_email))
            conn.commit()
        return redirect(url_for('login', role=role))

    return render_template('signup.html', role=role)

@app.route('/student/home')
def student_home():
    if session.get('role') != 'student':
        return redirect('/')
    user_id = session['user_id']  
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id=?", (user_id,))
        user = cursor.fetchone()
    return render_template('student_home.html', user=user)

@app.route('/admin/home')
def admin_home():
    if session.get('role') != 'admin':
        return redirect('/')
    user_id = session['user_id']  
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id=?", (user_id,))
        user = cursor.fetchone()
    return render_template('admin_home.html', user=user)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

@app.route('/student/attendance', methods=['GET', 'POST'])
def student_attendance():
    if session.get('role') != 'student':
        return redirect('/')
    
    user_id = session['user_id'] 
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT student_number FROM users WHERE id=?", (user_id,))
        student_number = cursor.fetchone()[0]

        if request.method == 'POST':
            status = request.form['status']
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("INSERT INTO attendance (student_number, status, timestamp) VALUES (?, ?, ?)",
                           (student_number, status, timestamp))
            conn.commit()
            flash('Attendance recorded.')

        cursor.execute("SELECT status, timestamp FROM attendance WHERE student_number=? ORDER BY timestamp DESC", 
                       (student_number,))
        records = cursor.fetchall()
    
    return render_template('student_attendance.html', student_number=student_number, records=records)

@app.route('/student/attendance/export/<filetype>')
def export_student_attendance(filetype):
    if session.get('role') != 'student':
        return redirect('/')
    
    user_id = session['user_id']  
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT student_number FROM users WHERE id=?", (user_id,))
        student_number = cursor.fetchone()[0]
        cursor.execute("SELECT status, timestamp FROM attendance WHERE student_number=?", (student_number,))
        records = cursor.fetchall()

    if filetype == 'csv':
        filename = f"{student_number}_attendance.csv"
        filepath = os.path.join('exports', filename)
        os.makedirs('exports', exist_ok=True)
        with open(filepath, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Status', 'Timestamp'])
            writer.writerows(records)
        return send_file(filepath, as_attachment=True)

    elif filetype == 'pdf':
        filename = f"{student_number}_attendance.pdf"
        filepath = os.path.join('exports', filename)
        os.makedirs('exports', exist_ok=True)
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.cell(200, 10, f"Attendance Records - {student_number}", ln=True, align='C')
        pdf.ln(10)
        for status, timestamp in records:
            pdf.cell(200, 10, f"{status} - {timestamp}", ln=True)
        pdf.output(filepath)
        return send_file(filepath, as_attachment=True)

@app.route('/admin/attendance', methods=['GET', 'POST'])
def admin_attendance():
    if session.get('role') != 'admin':
        return redirect('/')
    
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, student_number, status, timestamp FROM attendance ORDER BY timestamp DESC")
        records = cursor.fetchall()
    
    return render_template('admin_attendance.html', records=records)

@app.route('/admin/attendance/edit/<int:record_id>', methods=['POST'])
def edit_attendance(record_id):
    new_status = request.form['status']
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE attendance SET status=? WHERE id=?", (new_status, record_id))
        conn.commit()
    flash("Attendance updated.")
    return redirect(url_for('admin_attendance'))

@app.route('/admin/attendance/delete/<int:record_id>')
def delete_attendance(record_id):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM attendance WHERE id=?", (record_id,))
        conn.commit()
    flash("Attendance deleted.")
    return redirect(url_for('admin_attendance'))

@app.route('/admin/attendance/export/<filetype>')
def export_admin_attendance(filetype):
    if session.get('role') != 'admin':
        return redirect('/')
    
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT student_number, status, timestamp FROM attendance ORDER BY timestamp DESC")
        records = cursor.fetchall()

    if filetype == 'csv':
        filename = "all_attendance.csv"
        filepath = os.path.join('exports', filename)
        os.makedirs('exports', exist_ok=True)
        with open(filepath, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Student Number', 'Status', 'Timestamp'])
            writer.writerows(records)
        return send_file(filepath, as_attachment=True)

    elif filetype == 'pdf':
        filename = "all_attendance.pdf"
        filepath = os.path.join('exports', filename)
        os.makedirs('exports', exist_ok=True)
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.cell(200, 10, "All Attendance Records", ln=True, align='C')
        pdf.ln(10)
        for sn, status, ts in records:
            pdf.cell(200, 10, f"{sn} - {status} - {ts}", ln=True)
        pdf.output(filepath)
        return send_file(filepath, as_attachment=True)
    
@app.route('/student/quizzes')
def student_quizzes_to_take():
    if session.get('role') != 'student':
        return redirect('/')
        
    user_id = session['user_id']
    
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT student_number FROM users WHERE id = ?", (user_id,))
        student_number = cursor.fetchone()[0]
        
        # Modified query to use DISTINCT to prevent duplicates
        cursor.execute("""
            SELECT DISTINCT q.id, q.title, q.duration 
            FROM quizzes q
            JOIN assigned_quizzes aq ON q.id = aq.quiz_id
            WHERE aq.student_number = ?
            AND NOT EXISTS (
                SELECT 1 FROM quiz_responses 
                WHERE quiz_id = q.id AND student_number = ?
            )
        """, (student_number, student_number))
        
        quizzes = cursor.fetchall()
        
    return render_template('student_quizzes.html', quizzes=quizzes)

@app.route('/student/take_quiz/<int:quiz_id>', methods=['GET', 'POST'])
def take_quiz(quiz_id):
    if session.get('role') != 'student':
        return redirect('/')
        
    user_id = session['user_id']
    
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT student_number FROM users WHERE id = ?", (user_id,))
        student_number = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT 1 FROM assigned_quizzes 
            WHERE quiz_id = ? AND student_number = ?
        """, (quiz_id, student_number))
        
        if not cursor.fetchone():
            flash("You are not assigned to this quiz.")
            return redirect('/student/quizzes')
        
        cursor.execute("""
            SELECT 1 FROM quiz_responses 
            WHERE quiz_id = ? AND student_number = ?
        """, (quiz_id, student_number))
        
        if cursor.fetchone():
            flash("You have already taken this quiz.")
            return redirect('/student/quizzes')
        
        cursor.execute("SELECT title, questions, duration FROM quizzes WHERE id = ?", (quiz_id,))
        quiz = cursor.fetchone()
        
        if not quiz:
            flash("Quiz not found.")
            return redirect('/student/quizzes')
        
        title = quiz[0]
        questions = json.loads(quiz[1])
        duration = quiz[2]
    
    if request.method == 'POST':
        answers = {}
        for i, question in enumerate(questions):
            question_id = f"q{i}"
            if question['type'] == 'mcq':
                answer = request.form.get(question_id, '')
            else:  
                answer = request.form.get(question_id, '')
            
            answers[question_id] = answer
        
        score = 0
        total_possible = 0
        
        for i, question in enumerate(questions):
            question_id = f"q{i}"
            
            if question['type'] == 'mcq':
                total_possible += 1
                student_answer = answers.get(question_id, '').lower()
                correct_answer = question.get('correct', '').lower()
                
                if student_answer == correct_answer:
                    score += 1
        
        percentage_score = (score / total_possible * 100) if total_possible > 0 else 0
        
        
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO quiz_responses (student_number, quiz_id, answers, score) VALUES (?, ?, ?, ?)",
                (student_number, quiz_id, json.dumps(answers), percentage_score)
            )
            conn.commit()
        
        flash(f"Quiz submitted successfully. Your score: {percentage_score:.1f}%")
        return redirect('/student/quiz_results')
    
    return render_template('take_quiz.html', 
                          quiz_id=quiz_id, 
                          title=title, 
                          questions=questions, 
                          duration=duration)


@app.route('/student/quiz_results')
def student_quiz_results():
    if session.get('role') != 'student':
        return redirect('/')

    user_id = session['user_id'] 
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT student_number FROM users WHERE id=?", (user_id,))
        student_number = cursor.fetchone()[0]

        cursor.execute('''
            SELECT qr.id, q.title, qr.score, qr.answers
            FROM quiz_responses qr
            JOIN quizzes q ON qr.quiz_id = q.id
            WHERE qr.student_number=?
        ''', (student_number,))
        records = cursor.fetchall()

    return render_template('student_quiz_results.html', records=records)

@app.route('/student/export_quiz_results/csv')
def export_quiz_results_csv():
    if session.get('role') != 'student':
        return redirect('/')

    user_id = session['user_id'] 
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT student_number FROM users WHERE id=?", (user_id,))
        student_number = cursor.fetchone()[0]

        cursor.execute('''
            SELECT q.title, qr.score
            FROM quiz_responses qr
            JOIN quizzes q ON qr.quiz_id = q.id
            WHERE qr.student_number=?
        ''', (student_number,))
        records = cursor.fetchall()

    output = make_response()
    writer = csv.writer(output)
    writer.writerow(['Quiz Title', 'Score'])
    writer.writerows(records)

    output.headers["Content-Disposition"] = "attachment; filename=quiz_results.csv"
    output.headers["Content-type"] = "text/csv"
    return output

@app.route('/student/export_quiz_results/pdf')
def export_quiz_results_pdf():
    if session.get('role') != 'student':
        return redirect('/')

    user_id = session['user_id'] 
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT student_number FROM users WHERE id=?", (user_id,))
        student_number = cursor.fetchone()[0]

        cursor.execute('''
            SELECT q.title, qr.score
            FROM quiz_responses qr
            JOIN quizzes q ON qr.quiz_id = q.id
            WHERE qr.student_number=?
        ''', (student_number,))
        records = cursor.fetchall()

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt="Quiz Results", ln=True, align='C')
    pdf.ln(10)

    for row in records:
        pdf.cell(200, 10, txt=f"{row[0]} - Score: {row[1]}", ln=True)

    response = make_response(pdf.output(dest='S').encode('latin1'))
    response.headers['Content-Disposition'] = 'attachment; filename=quiz_results.pdf'
    response.headers['Content-Type'] = 'application/pdf'
    return response

@app.route('/admin/manage_quizzes', methods=['GET', 'POST'])
def admin_manage_quizzes():
    if session.get('role') != 'admin':
        return redirect('/')
        
    if request.method == 'POST':
        title = request.form['title']
        duration = request.form['duration']
        questions = []
        i = 1
        while f'question{i}' in request.form:
            question_text = request.form[f'question{i}']
            question_type = request.form[f'type{i}']
            
            question_data = {
                'text': question_text,
                'type': question_type
            }
            
            if question_type == 'mcq':
                question_data['choices'] = {
                    'a': request.form[f'choice{i}a'],
                    'b': request.form[f'choice{i}b'],
                    'c': request.form[f'choice{i}c'],
                    'd': request.form[f'choice{i}d']
                }
                question_data['correct'] = request.form[f'correct{i}'].lower()
            
            questions.append(question_data)
            i += 1
        
        questions_json = json.dumps(questions)
        
        with sqlite3.connect(DB_NAME) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO quizzes (title, questions, duration, type) VALUES (?, ?, ?, ?)",
                (title, questions_json, duration, 'quiz')
            )
            quiz_id = cursor.lastrowid
            
            # Get unique student numbers to prevent duplicates
            cursor.execute("SELECT DISTINCT student_number FROM users WHERE role = 'student'")
            students = cursor.fetchall()
            
            # Check if assignment already exists before inserting
            for student in students:
                student_number = student[0]
                # Check if this quiz is already assigned to this student
                cursor.execute(
                    "SELECT 1 FROM assigned_quizzes WHERE quiz_id = ? AND student_number = ?",
                    (quiz_id, student_number)
                )
                if not cursor.fetchone():  # Only insert if not exists
                    cursor.execute(
                        "INSERT INTO assigned_quizzes (quiz_id, student_number) VALUES (?, ?)",
                        (quiz_id, student_number)
                    )
                
            conn.commit()
        
        return redirect('/admin/manage_quizzes')
    
    # Use DISTINCT in query to prevent duplicate quizzes in display
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT id, title, duration FROM quizzes WHERE type = 'quiz' OR type IS NULL")
        quizzes = cursor.fetchall()
        
    return render_template('admin_manage_quizzes.html', quizzes=quizzes)


@app.route('/admin/quiz_submissions')
def admin_quiz_submissions():
    if session.get('role') != 'admin':
        return redirect('/')

    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT qr.id, qr.student_number, q.title, qr.answers, qr.score, qr.quiz_id
            FROM quiz_responses qr
            JOIN quizzes q ON qr.quiz_id = q.id
            WHERE q.type = 'quiz'
        ''')
        records = cursor.fetchall()

    return render_template('admin_quiz_submissions.html', records=records)

@app.route('/admin/grade_quiz/<int:response_id>', methods=['GET', 'POST'])
def grade_quiz(response_id):
    if session.get('role') != 'admin':
        return redirect('/')

    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()

        if request.method == 'POST':
            score = float(request.form['score'])
            cursor.execute("UPDATE quiz_responses SET score=? WHERE id=?", (score, response_id))
            conn.commit()
            flash("Score updated!")
            return redirect(url_for('admin_quiz_submissions'))

        cursor.execute("SELECT qr.answers, q.title FROM quiz_responses qr JOIN quizzes q ON qr.quiz_id = q.id WHERE qr.id=?", (response_id,))
        data = cursor.fetchone()

    return render_template('grade_quiz.html', data=data, response_id=response_id)

@app.route('/admin/export_quiz_results/csv')
def admin_export_quiz_csv():
    if session.get('role') != 'admin':
        return redirect('/')

    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT qr.student_number, q.title, qr.score
            FROM quiz_responses qr
            JOIN quizzes q ON qr.quiz_id = q.id
            WHERE q.type = 'quiz'
        ''')
        records = cursor.fetchall()

    output = make_response()
    writer = csv.writer(output)
    writer.writerow(['Student Number', 'Quiz Title', 'Score'])
    writer.writerows(records)

    output.headers["Content-Disposition"] = "attachment; filename=quiz_report.csv"
    output.headers["Content-type"] = "text/csv"
    return output

@app.route('/admin/export_quiz_results/pdf')
def admin_export_quiz_pdf():
    if session.get('role') != 'admin':
        return redirect('/')

    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT qr.student_number, q.title, qr.score
            FROM quiz_responses qr
            JOIN quizzes q ON qr.quiz_id = q.id
            WHERE q.type = 'quiz'
        ''')
        records = cursor.fetchall()

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt="Quiz Results Report", ln=True, align='C')
    pdf.ln(10)

    for row in records:
        pdf.cell(200, 10, txt=f"{row[0]} | {row[1]} | Score: {row[2]}", ln=True)

    response = make_response(pdf.output(dest='S').encode('latin1'))
    response.headers['Content-Disposition'] = 'attachment; filename=quiz_report.pdf'
    response.headers['Content-Type'] = 'application/pdf'
    return response

@app.route('/student/exams')
def student_exams_to_take():
    if session.get('role') != 'student':
        return redirect('/')
        
    user_id = session['user_id']
    
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT student_number FROM users WHERE id = ?", (user_id,))
        student_number = cursor.fetchone()[0]
        
        # Modified query to use DISTINCT to prevent duplicates
        cursor.execute("""
            SELECT DISTINCT e.id, e.title, e.duration 
            FROM exams e
            JOIN assigned_exams ae ON e.id = ae.exam_id
            WHERE ae.student_number = ?
            AND NOT EXISTS (
                SELECT 1 FROM exam_responses 
                WHERE exam_id = e.id AND student_number = ?
            )
        """, (student_number, student_number))
        
        exams = cursor.fetchall()
        
    return render_template('student_exams.html', exams=exams)

@app.route('/student/take_exam/<int:exam_id>', methods=['GET', 'POST'])
def take_exam(exam_id):
    if session.get('role') != 'student':
        return redirect('/')
        
    user_id = session['user_id']
    
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT student_number FROM users WHERE id = ?", (user_id,))
        student_number = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT 1 FROM assigned_exams 
            WHERE exam_id = ? AND student_number = ?
        """, (exam_id, student_number))
        
        if not cursor.fetchone():
            flash("You are not assigned to this exam.")
            return redirect('/student/exams')
        
        cursor.execute("""
            SELECT 1 FROM exam_responses 
            WHERE exam_id = ? AND student_number = ?
        """, (exam_id, student_number))
        
        if cursor.fetchone():
            flash("You have already taken this exam.")
            return redirect('/student/exams')
        
        cursor.execute("SELECT title, questions, duration FROM exams WHERE id = ?", (exam_id,))
        exam = cursor.fetchone()
        
        if not exam:
            flash("Exam not found.")
            return redirect('/student/exams')
        
        title = exam[0]
        questions = json.loads(exam[1])
        duration = exam[2]

        for q in questions:
            if q.get('type') in ['short', 'text']:
                q['type'] = 'written'
    
    if request.method == 'POST':
        answers = {}
        for i, question in enumerate(questions):
            question_id = f"q{i}"
            answer = request.form.get(question_id, '')
            answers[question_id] = answer
        
        score = 0
        total_possible = 0
        
        for i, question in enumerate(questions):
            question_id = f"q{i}"
            if question['type'] == 'mcq':
                total_possible += 1
                student_answer = answers.get(question_id, '').lower()
                correct_answer = question.get('correct', '').lower()
                if student_answer == correct_answer:
                    score += 1
        
        percentage_score = (score / total_possible * 100) if total_possible > 0 else 0
        
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO exam_responses (student_number, exam_id, answers, score) VALUES (?, ?, ?, ?)",
                (student_number, exam_id, json.dumps(answers), percentage_score)
            )
            conn.commit()
        
        flash(f"Exam submitted successfully. Your score: {percentage_score:.1f}%")
        return redirect('/student/exam_results')
    
    return render_template('take_exam.html', 
                          exam_id=exam_id, 
                          title=title, 
                          questions=questions, 
                          duration=duration)

@app.route('/student/exam/history')
def student_exam_history():
    if session.get('role') != 'student':
        return redirect('/')
    
    user_id = session['user_id']  
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT student_number FROM users WHERE id=?", (user_id,))
        student_number = cursor.fetchone()[0]

        cursor.execute('''SELECT quizzes.title, quiz_responses.score, quiz_responses.answers
                          FROM quiz_responses 
                          JOIN quizzes ON quiz_responses.quiz_id = quizzes.id
                          WHERE quiz_responses.student_number=? AND quizzes.type='exam' ''', 
                          (student_number,))
        records = cursor.fetchall()

    return render_template('student_exam_history.html', records=records)

@app.route('/admin/create_exam', methods=['GET', 'POST'])
def create_exam():
    if session.get('role') != 'admin':
        return redirect('/')

    if request.method == 'POST':
        title = request.form['title']
        assigned_to = request.form['assigned_to']
        deadline = request.form['deadline']
        quiz_type = request.form['type']

        questions = []
        for i in range(1, 101):
            q_text = request.form.get(f'q{i}')
            q_type = request.form.get(f'q{i}_type')
            if q_text and q_type:
                question = {'question': q_text, 'type': q_type}
                if q_type == 'mcq':
                    options = [
                        request.form.get(f'q{i}_opt1'),
                        request.form.get(f'q{i}_opt2'),
                        request.form.get(f'q{i}_opt3'),
                        request.form.get(f'q{i}_opt4')
                    ]
                    question['options'] = options
                    question['answer'] = request.form.get(f'q{i}_correct')
                questions.append(question)

        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute('''INSERT INTO quizzes (title, assigned_to, deadline, questions, type)
                              VALUES (?, ?, ?, ?, ?)''',
                           (title, assigned_to, deadline, json.dumps(questions), quiz_type))
            conn.commit()
        flash("Quiz/Exam created successfully.")
        return redirect(url_for('admin_home'))

    return render_template('create_exam.html')

@app.route('/student/exam_results')
def student_exam_results():
    if session.get('role') != 'student':
        return redirect('/')

    user_id = session['user_id']
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT student_number FROM users WHERE id=?", (user_id,))
        student_number = cursor.fetchone()[0]

        cursor.execute('''
            SELECT er.id, e.title, er.score, er.answers
            FROM exam_responses er
            JOIN exams e ON er.exam_id = e.id
            WHERE er.student_number = ?
        ''', (student_number,))
        
        records = cursor.fetchall()

    return render_template('student_exam_results.html', exams=records)

@app.route('/student/exam_result/<int:exam_id>')
def student_exam_result_detail(exam_id):
    """Shows detailed results for a specific exam"""
    
    if session.get('role') != 'student':
        return redirect('/')
    
    user_id = session['user_id']
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT student_number FROM users WHERE id=?", (user_id,))
        student_number = cursor.fetchone()[0]
        
        
        cursor.execute('''
            SELECT er.id, e.title, er.score 
            FROM exam_responses er
            JOIN exams e ON er.exam_id = e.id
            WHERE er.student_number = ? AND er.exam_id = ?
        ''', (student_number, exam_id))
        
        records = cursor.fetchall()
    
    if not records:
        flash('No results found for this exam')
        return redirect(url_for('student_exam_results'))
    
    return render_template('student/student_exam_result_detail.html', records=records)

@app.route('/student/export_exam_results/csv')
def export_exam_results_csv():
    if session.get('role') != 'student':
        return redirect('/')

    user_id = session['user_id']
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT student_number FROM users WHERE id=?", (user_id,))
        student_number = cursor.fetchone()[0]

        # Modified query - removed the timestamp column reference
        cursor.execute('''
            SELECT e.title, er.score
            FROM exam_responses er
            JOIN exams e ON er.exam_id = e.id
            WHERE er.student_number=?
        ''', (student_number,))
        records = cursor.fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Exam Title', 'Score'])
    writer.writerows(records)

    # Create a proper CSV response
    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = "attachment; filename=exam_results.csv"
    response.headers["Content-type"] = "text/csv"
    return response


@app.route('/student/export_exam_results/pdf')
def export_exam_results_pdf():
    if session.get('role') != 'student':
        return redirect('/')

    user_id = session['user_id']
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT student_number, name FROM users WHERE id=?", (user_id,))
        user_data = cursor.fetchone()
        student_number = user_data[0]
        student_name = user_data[1]

        # Modified query - removed the timestamp column reference
        cursor.execute('''
            SELECT e.title, er.score
            FROM exam_responses er
            JOIN exams e ON er.exam_id = e.id
            WHERE er.student_number=?
        ''', (student_number,))
        records = cursor.fetchall()

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=f"Exam Results for {student_name}", ln=True, align='C')
    pdf.ln(10)

    # Headers
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(150, 10, "Exam Title", border=1)
    pdf.cell(40, 10, "Score", border=1)
    pdf.ln()
    
    # Data
    pdf.set_font("Arial", size=12)
    for row in records:
        pdf.cell(150, 10, str(row[0]), border=1)
        pdf.cell(40, 10, str(row[1]), border=1)
        pdf.ln()

    response = make_response(pdf.output(dest='S').encode('latin1'))
    response.headers['Content-Disposition'] = 'attachment; filename=exam_results.pdf'
    response.headers['Content-Type'] = 'application/pdf'
    return response


@app.route('/admin/grade_short_answers')
def grade_short_answers():
    if session.get('role') != 'admin':
        return redirect('/')
    
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT qr.id, qr.student_number, q.title, qr.answers, q.questions 
            FROM quiz_responses qr 
            JOIN quizzes q ON qr.quiz_id = q.id
        ''')
        responses = cursor.fetchall()

    ungraded = []
    for row in responses:
        response_id, student_number, title, answers_json, questions_json = row
        answers = json.loads(answers_json)
        questions = json.loads(questions_json)

        if any(q['type'] == 'short' for q in questions):
            ungraded.append((response_id, student_number, title, questions, answers))

    return render_template('admin_grade.html', submissions=ungraded)

@app.route('/admin/submit_grades/<int:response_id>', methods=['POST'])
def submit_grades(response_id):
    if session.get('role') != 'admin':
        return redirect('/')
        
    scores = []
    total_score = 0

    for key in request.form:
        if key.startswith("score_"):
            score = float(request.form[key])
            scores.append(score)
            total_score += score

    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE quiz_responses SET score=? WHERE id=?", (total_score, response_id))
        conn.commit()

    flash("Scores submitted successfully.")
    return redirect(url_for('grade_short_answers'))

@app.route('/admin/manage_exams', methods=['GET', 'POST'])
def admin_manage_exams():
    if session.get('role') != 'admin':
        return redirect('/')
        
    if request.method == 'POST':
        title = request.form['title']
        duration = request.form['duration']
        questions = []
        i = 1
        while f'question{i}' in request.form:
            question_text = request.form[f'question{i}']
            question_type = request.form[f'type{i}']
            
            question_data = {
                'text': question_text,
                'type': question_type
            }
            
            if question_type == 'mcq':
                question_data['choices'] = {
                    'a': request.form[f'choice{i}a'],
                    'b': request.form[f'choice{i}b'],
                    'c': request.form[f'choice{i}c'],
                    'd': request.form[f'choice{i}d']
                }
                question_data['correct'] = request.form[f'correct{i}'].lower()
            
            questions.append(question_data)
            i += 1
        
        questions_json = json.dumps(questions)
        
        with sqlite3.connect(DB_NAME) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO exams (title, questions, duration, type) VALUES (?, ?, ?, ?)",
                (title, questions_json, duration, 'exam')
            )
            exam_id = cursor.lastrowid
            
            # Get unique student numbers to prevent duplicates
            cursor.execute("SELECT DISTINCT student_number FROM users WHERE role = 'student'")
            students = cursor.fetchall()
            
            # Check if assignment already exists before inserting
            for student in students:
                student_number = student[0]
                # Check if this exam is already assigned to this student
                cursor.execute(
                    "SELECT 1 FROM assigned_exams WHERE exam_id = ? AND student_number = ?",
                    (exam_id, student_number)
                )
                if not cursor.fetchone():  # Only insert if not exists
                    cursor.execute(
                        "INSERT INTO assigned_exams (exam_id, student_number) VALUES (?, ?)",
                        (exam_id, student_number)
                    )
                
            conn.commit()
        
        return redirect('/admin/manage_exams')
    
    # Use DISTINCT in query to prevent duplicate exams in display
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT id, title, duration FROM exams")
        exams = cursor.fetchall()
        
    return render_template('admin_manage_exams.html', exams=exams)

@app.route('/admin/export_exam_results/csv')
def admin_export_exam_results_csv():
    if session.get('role') != 'admin':
        return redirect('/')

    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT u.name, u.student_number, q.title, qr.score
            FROM quiz_responses qr
            JOIN quizzes q ON qr.quiz_id = q.id
            JOIN users u ON qr.student_number = u.student_number
            WHERE q.type='exam'
        ''')
        records = cursor.fetchall()

    output = make_response()
    writer = csv.writer(output)
    writer.writerow(['Student Name', 'Student Number', 'Exam Title', 'Score'])
    writer.writerows(records)

    output.headers["Content-Disposition"] = "attachment; filename=all_exam_results.csv"
    output.headers["Content-type"] = "text/csv"
    return output

@app.route('/admin/export_exam_results/pdf')
def admin_export_exam_results_pdf():
    if session.get('role') != 'admin':
        return redirect('/')

    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT u.name, u.student_number, q.title, qr.score
            FROM quiz_responses qr
            JOIN quizzes q ON qr.quiz_id = q.id
            JOIN users u ON qr.student_number = u.student_number
            WHERE q.type='exam'
        ''')
        records = cursor.fetchall()

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt="All Students - Exam Results", ln=True, align='C')
    pdf.ln(10)

    for row in records:
        name, student_number, title, score = row
        pdf.cell(200, 10, txt=f"{name} ({student_number}) - {title} - Score: {score}", ln=True)

    response = make_response(pdf.output(dest='S').encode('latin1'))
    response.headers['Content-Disposition'] = 'attachment; filename=all_exam_results.pdf'
    response.headers['Content-Type'] = 'application/pdf'
    return response

@app.route('/admin/exam_submissions')
def admin_exam_submissions():
    if session.get('role') != 'admin':
        return redirect('/')
    
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("PRAGMA table_info(exam_responses)")
        columns = cursor.fetchall()
        column_names = [col['name'] for col in columns]
        
        print("Exam responses table columns:", column_names)
        
        cursor.execute("SELECT * FROM exam_responses")
        records = cursor.fetchall()

        if records:
            print("First record keys:", records[0].keys())
    
    return render_template('exam_responses.html', records=records)

@app.route('/admin/grade_exam/<int:response_id>')
def grade_exam(response_id):
    if session.get('role') != 'admin':
        return redirect('/')
    
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT er.id, u.name, e.title, er.answers, e.questions, e.correct_answers, er.exam_id
            FROM exam_responses er
            JOIN users u ON er.student_id = u.id
            JOIN exams e ON er.exam_id = e.id
            WHERE er.id = ?
        ''', (response_id,))
        
        response = cursor.fetchone()
    
    if not response:
        flash('Exam response not found', 'error')
        return redirect(url_for('admin_exam_submissions'))
    
    return render_template('grade_exam.html', response=response)

@app.route('/admin/submit_exam_grade/<int:response_id>', methods=['POST'])
def submit_exam_grade(response_id):
    if session.get('role') != 'admin':
        return redirect('/')
    
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT e.questions
            FROM exam_responses er
            JOIN exams e ON er.exam_id = e.id
            WHERE er.id = ?
        ''', (response_id,))
        
        result = cursor.fetchone()
        if not result:
            flash('Exam response not found', 'error')
            return redirect(url_for('admin_exam_submissions'))
        
        import json
        questions = json.loads(result[0])
        total_points = 0
        
        for i in range(len(questions)):
            points = float(request.form.get(f'points{i}', 0))
            total_points += points
        
        cursor.execute('''
            UPDATE exam_responses
            SET score = ?
            WHERE id = ?
        ''', (total_points, response_id))
        
        conn.commit()
    
    flash('Exam graded successfully!', 'success')
    return redirect(url_for('admin_exam_submissions'))

if __name__ == '__main__':
    if not os.path.exists(DB_NAME):
        init_db()
    app.run(debug=True)