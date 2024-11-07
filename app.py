from datetime import datetime
from bson import ObjectId
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, IntegerField, FileField
from wtforms.validators import DataRequired, Email, Length, EqualTo, Optional
from pymongo import MongoClient, ASCENDING
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
import os
from werkzeug.utils import secure_filename
from config import Config
from wtforms import ValidationError

app = Flask(__name__)
app.config.from_object(Config)

client = MongoClient(app.config['MONGO_URI'])

# Specify the database and collection you want to use
db = client.myFirstDatabase

bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'index'


def email_not_exists(form, field):
    email = field.data
    admin = db.admin.find_one({'email': email})
    student = db.students.find_one({'email': email})
    if admin or student:
        raise ValidationError('Email already exists. Please use a different email.')


# # Create indexes for students collection
# db.students.create_index([('grade', ASCENDING), ('roll_number', ASCENDING)])
# db.students.create_index('email')
# db.marks.create_index('student_id')
# db.admin.create_index('email')


# Admin User Model
class Admin(UserMixin):
    def __init__(self, email, password_hash, **kwargs):
        self.email = email
        self.password_hash = password_hash
        for k, v in kwargs.items():
            setattr(self, k, v)

    @staticmethod
    def from_mongo(data):
        return Admin(**data)

    def get_id(self):
        return str(self.email)  # Ensure this matches the way you identify users


@login_manager.user_loader
def load_user(user_id):
    user_data = db.admin.find_one({'email': user_id})
    if not user_data:
        user_data = db.students.find_one({'email': user_id})
    return Admin.from_mongo(user_data) if user_data else None


class AdminLoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')


class AdminRegisterForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email(), email_not_exists])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Register')


class StudentForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    age = IntegerField('Age', validators=[DataRequired()])
    roll_number = StringField('Roll Number', validators=[DataRequired()])
    grade = StringField('Grade', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email(), email_not_exists])
    photo = FileField('Photo')
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    submit = SubmitField('Submit')


class StudentFormEdit(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    age = IntegerField('Age', validators=[DataRequired()])
    roll_number = StringField('Roll Number', validators=[DataRequired()])
    grade = StringField('Grade', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    photo = FileField('Photo')
    password = PasswordField('Password', validators=[Optional(), Length(min=6)])
    submit = SubmitField('Submit')


class MarksForm(FlaskForm):
    subject = StringField('Subject', validators=[DataRequired()])
    marks = IntegerField('Marks', validators=[DataRequired()])
    submit = SubmitField('Submit')


class EditMarksForm(FlaskForm):
    subject = StringField('Subject', validators=[DataRequired()])
    marks = IntegerField('Marks', validators=[DataRequired()])
    submit = SubmitField('Submit')


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    form = AdminLoginForm()
    if form.validate_on_submit():
        admin = db.admin.find_one({'email': form.email.data, })
        if admin and admin['password_hash'] == form.password.data:
            login_user(Admin.from_mongo(admin))
            flash('Logged in successfully!', 'success')
            return redirect(url_for('admin_index'))
        else:
            flash('Login Unsuccessful. Please check email and password', 'danger')
    return render_template('admin_login.html', form=form)


@app.route('/admin', methods=['GET'])
@login_required
def admin_index():
    selected_grade = request.args.get('grade')
    selected_roll_number = request.args.get('roll_number')

    pipeline = []

    # Match stage for filtering by grade
    if selected_grade and selected_grade != '':
        pipeline.append({
            '$match': {
                'grade': selected_grade
            }
        })

    # Match stage for filtering by roll number
    if selected_roll_number and selected_roll_number != '':
        pipeline.append({
            '$match': {
                'roll_number': selected_roll_number
            }
        })

    # Group stage to group students by grade
    pipeline.append({
        '$group': {
            '_id': '$grade',
            'students': {
                '$push': {
                    '_id': '$_id',
                    'name': '$name',
                    'roll_number': '$roll_number',
                    'email': '$email',
                    'photo': '$photo'
                }
            }
        }
    })

    # Sort by grade
    pipeline.append({
        '$sort': {
            '_id': 1
        }
    })

    # Execute the aggregation pipeline
    student_data = list(db.students.aggregate(pipeline))

    # Extract unique grades and roll numbers for the dropdown filters
    all_grades = db.students.distinct('grade')
    roll_numbers = db.students.distinct('roll_number',
                                        {'grade': selected_grade}) if selected_grade else db.students.distinct(
        'roll_number')

    return render_template('admin_index.html', student_data=student_data, all_grades=all_grades,
                           roll_numbers=roll_numbers, selected_grade=selected_grade,
                           selected_roll_number=selected_roll_number)


@app.route('/admin/student_marks/<student_id>', methods=['GET'])
@login_required
def student_marks(student_id):
    try:
        student_id = ObjectId(student_id)
    except Exception as e:
        flash('Invalid student ID', 'danger')
        return redirect(url_for('admin_index'))

    student = db.students.find_one({'_id': student_id})
    if not student:
        flash('Student not found', 'danger')
        return redirect(url_for('admin_index'))

    marks = list(db.marks.find({'student_id': student_id}))

    return render_template('student_marks.html', student=student, marks=marks)


@app.route('/admin/logout')
@login_required
def admin_logout():
    logout_user()
    return redirect(url_for('home'))


@app.route('/admin/register', methods=['GET', 'POST'])
def admin_register():
    form = AdminRegisterForm()
    if form.validate_on_submit():
        email = form.email.data
        password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        db.admin.insert_one({'email': email, 'password_hash': password})
        flash('Admin registered successfully!', 'success')
        return redirect(url_for('admin_login'))
    return render_template('admin_register.html', form=form)


@app.route('/admin/add_student', methods=['GET', 'POST'])
@login_required
def add_student():
    form = StudentForm()
    if form.validate_on_submit():
        existing_student = db.students.find_one({'grade': form.grade.data, 'roll_number': form.roll_number.data})
        if existing_student:
            flash('Roll number already exists for the grade. Please use a different roll number.', 'danger')
            return render_template('add_student.html', form=form)

        photo = form.photo.data
        print("photo: ", photo)
        filename = secure_filename(photo.filename)
        filename = form.name.data + form.grade.data + form.roll_number.data + filename
        photo.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        print("photo: ", filename)
        student = {
            'name': form.name.data,
            'age': form.age.data,
            'roll_number': form.roll_number.data,
            'grade': form.grade.data,
            'email': form.email.data,
            'photo': filename,
            'password_hash': bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        }
        db.students.insert_one(student)
        flash('Student added successfully!', 'success')
        return redirect(url_for('admin_index'))
    return render_template('add_student.html', form=form)


@app.route('/admin/edit_student/<student_id>', methods=['GET', 'POST'])
@login_required
def edit_student(student_id):
    try:
        student_id = ObjectId(student_id)
    except Exception as e:
        flash('Invalid student ID', 'danger')
        return redirect(url_for('admin_index'))

    student = db.students.find_one({'_id': student_id})

    if not student:
        flash('Student not found', 'danger')
        return redirect(url_for('admin_index'))

    form = StudentFormEdit()

    if form.validate_on_submit():
        updated_student = {
            'name': form.name.data,
            'age': form.age.data,
            'roll_number': form.roll_number.data,
            'grade': form.grade.data,
            'email': form.email.data,
            'photo': student.get('photo')
        }

        # Update the password only if it's provided
        if form.password.data:
            updated_student['password_hash'] = bcrypt.generate_password_hash(form.password.data).decode('utf-8')

        if form.photo.data:
            photo = form.photo.data
            # Delete the previous photo
            previous_photo_path = os.path.join(app.config['UPLOAD_FOLDER'], student.get('photo', ''))
            if os.path.exists(previous_photo_path):
                os.remove(previous_photo_path)
            filename = secure_filename(photo.filename)
            filename = form.name.data + form.grade.data + form.roll_number.data + filename
            photo.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            updated_student['photo'] = filename

        db.students.update_one({'_id': student_id}, {'$set': updated_student})
        flash('Student updated successfully!', 'success')
        return redirect(url_for('admin_index'))
    elif request.method == 'GET':
        form.name.data = student['name']
        form.age.data = student['age']
        form.roll_number.data = student['roll_number']
        form.grade.data = student['grade']
        form.email.data = student['email']

    # Print form errors for debugging
    if form.errors:
        print(form.errors)

    print(f"Rendering form with data: {form.data}")
    return render_template('edit_student.html', form=form)


@app.route('/admin/delete_student/<student_id>', methods=['POST'])
@login_required
def delete_student(student_id):
    # Convert student_id to ObjectId
    try:
        student_id = ObjectId(student_id)
    except Exception as e:
        flash('Invalid student ID', 'danger')
        return redirect(url_for('admin_index'))
    student = db.students.find_one({'_id': student_id})
    # Perform the deletion of the student
    result = db.students.delete_one({'_id': student_id})
    if result.deleted_count and student:
        # Delete the previous photo
        previous_photo_path = os.path.join(app.config['UPLOAD_FOLDER'], student['photo'])
        if os.path.exists(previous_photo_path):
            os.remove(previous_photo_path)
        # Perform the deletion of the student's marks
        db.marks.delete_many({'student_id': student_id})
        flash('Student and their marks deleted successfully!', 'success')
    else:
        flash('Student not found', 'danger')

    return redirect(url_for('admin_index'))


@app.route('/admin/add_marks/<student_id>', methods=['GET', 'POST'])
@login_required
def add_marks(student_id):
    form = MarksForm()
    if form.validate_on_submit():
        marks = {
            'student_id': ObjectId(student_id),
            'subject': form.subject.data,
            'marks': form.marks.data,
            'date': datetime.utcnow()
        }
        db.marks.insert_one(marks)
        flash('Marks added successfully!', 'success')
        return redirect(url_for('admin_index'))
    return render_template('add_marks.html', form=form)


# Routes for Student
@app.route('/student/login', methods=['GET', 'POST'])
def student_login():
    form = AdminLoginForm()
    if form.validate_on_submit():
        student = db.students.find_one({'email': form.email.data})
        print(student)
        if student and bcrypt.check_password_hash(student['password_hash'], form.password.data):
            login_user(Admin.from_mongo(student))
            flash('Logged in successfully!', 'success')
            return redirect(url_for('student_marks_list'))
        else:
            flash('Login Unsuccessful. Please check email and password', 'danger')
    return render_template('student_login.html', form=form)


@app.route('/student/marks_list')
@login_required
def student_marks_list():
    print(f"Current User ID: {current_user._id}")
    student = db.students.find_one({'_id': current_user._id})
    marks_cursor = db.marks.find({'student_id': current_user._id})  # Ensure this matches the identifier
    marks = list(marks_cursor)  # Convert cursor to list for easier handling
    for mark in marks:
        print(mark)
    return render_template('marks_list.html', student=student, marks=marks)


@app.route('/student/logout')
@login_required
def student_logout():
    logout_user()
    return redirect(url_for('home'))


@app.route('/admin/edit_marks/<mark_id>', methods=['GET', 'POST'])
@login_required
def edit_marks(mark_id):
    form = EditMarksForm()
    try:
        mark_id = ObjectId(mark_id)
    except Exception as e:
        flash('Invalid mark ID', 'danger')
        return redirect(url_for('admin_index'))

    mark = db.marks.find_one({'_id': mark_id})

    if not mark:
        flash('Marks not found', 'danger')
        return redirect(url_for('admin_index'))

    if form.validate_on_submit():
        updated_mark = {
            'subject': form.subject.data,
            'marks': form.marks.data,
            'date': datetime.utcnow()
        }
        db.marks.update_one({'_id': mark_id}, {'$set': updated_mark})
        flash('Marks updated successfully!', 'success')
        return redirect(url_for('admin_index'))
    elif request.method == 'GET':
        form.subject.data = mark['subject']
        form.marks.data = mark['marks']

    return render_template('edit_marks.html', form=form)


@app.route('/admin/delete_marks/<mark_id>', methods=['POST'])
@login_required
def delete_marks(mark_id):
    try:
        mark_id = ObjectId(mark_id)
    except Exception as e:
        flash('Invalid mark ID', 'danger')
        return redirect(url_for('admin_index'))

    result = db.marks.delete_one({'_id': mark_id})
    if result.deleted_count:
        flash('Marks deleted successfully!', 'success')
    else:
        flash('Marks not found', 'danger')

    return redirect(url_for('admin_index'))


@app.route('/show/<filename>')
def show_image(filename):
    return render_template('show_image.html', filename=filename)


if __name__ == "__main__":
    app.run()
