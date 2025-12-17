from time import time
from flask import Flask, render_template, session, redirect, url_for, flash, request, jsonify
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash
from forms import LoginForm, SignupForm, AddWordForm, ForgotPasswordForm
from models import db,UserAcc, UserAchievement, UserWords, Pokemon, Achievement, Vocabulary, WordHistory, Notification
from functools import wraps
import os
from datetime import datetime, date
import pytz
from sqlalchemy.sql import func
from datetime import datetime, timedelta
import random, requests
import os
import secrets
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from flask import request, jsonify, current_app
from werkzeug.utils import secure_filename
import hashlib
from dotenv import load_dotenv


app = Flask(__name__)
app.config['SECRET_KEY'] = 'FinalProjectACP'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///vocabulearner.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)
ph_timezone = pytz.timezone('Asia/Manila')




UPLOAD_FOLDER = 'static/uploads/avatars'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}


# Make sure these are set before using the route
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2MB max


load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'), encoding='utf-8')

# Email verification storage (in production, use Redis or database)
email_verification_store = {}



def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if user is logged in
        if 'user_id' not in session:
            flash("Please login to access the admin panel.", "warning")
            return redirect(url_for('login'))
        
        # Check if user is admin
        user_id = session['user_id']
        user = UserAcc.query.get(user_id)
        
        if not user or not user.is_admin:
            flash("You don't have permission to access the admin panel.", "danger")
            return redirect(url_for('dashboard'))
            
        return f(*args, **kwargs)
    return decorated_function

def check_and_update_pokemon_evolution(user):
    """Check if user qualifies for Pokémon evolution and update if needed."""
    if not user.pokemon_id:
        return False, None, None
    
    current_pokemon = Pokemon.query.get(user.pokemon_id)
    if not current_pokemon:
        return False, None, None
    
    # Get all Pokémon in the same family
    evolution_line = (
        Pokemon.query
        .filter_by(family_id=current_pokemon.family_id)
        .order_by(Pokemon.min_points_required)
        .all()
    )
    
    # Find the highest evolution the user qualifies for
    highest_evolution = None
    for evo in evolution_line:
        if user.total_points >= evo.min_points_required:
            highest_evolution = evo
    
    # If we found a higher evolution than current
    if highest_evolution and highest_evolution.pokemon_id != current_pokemon.pokemon_id:
        # Update user's Pokémon
        user.pokemon_id = highest_evolution.pokemon_id
        
        # Keep the user's custom Pokémon name if they have one
        if user.pokemon_name:
            # User keeps their custom name for the evolved Pokémon
            pass
        else:
            # If no custom name, set to new Pokémon's name
            user.pokemon_name = highest_evolution.name
        
        db.session.commit()
        return True, current_pokemon.name, highest_evolution.name
    
    return False, None, None

def update_user_streak(user):
    """Update the user's streak based on daily login."""
    today = datetime.now(ph_timezone).date()
    
    # If user has never logged in before, start streak
    if not user.last_login:
        user.current_streak = 1
        user.longest_streak = 1
        user.last_login = datetime.now(ph_timezone)
        db.session.commit()
        return
    
    # Convert last_login to Philippine timezone
    if user.last_login.tzinfo is None:
        last_login_ph = pytz.utc.localize(user.last_login).astimezone(ph_timezone)
    else:
        last_login_ph = user.last_login.astimezone(ph_timezone)
    
    last_login_date = last_login_ph.date()
    days_difference = (today - last_login_date).days
    
    if days_difference == 0:
        # Already logged in today - just update last_login time
        # BUT we should still check if current_streak > longest_streak
        # (in case longest_streak was manually changed or there's a bug)
        if user.current_streak > user.longest_streak:
            user.longest_streak = user.current_streak
        user.last_login = datetime.now(ph_timezone)
        db.session.commit()
    elif days_difference == 1:
        # Consecutive day - increment streak
        user.current_streak += 1
        
        # Update longest streak if current streak is greater
        if user.current_streak > user.longest_streak:
            user.longest_streak = user.current_streak
        
        user.last_login = datetime.now(ph_timezone)
        db.session.commit()
    elif days_difference > 1:
        # Streak broken - reset to 1
        user.current_streak = 1
        # Check if we need to update longest_streak (should be same)
        if user.current_streak > user.longest_streak:
            user.longest_streak = user.current_streak
        user.last_login = datetime.now(ph_timezone)
        db.session.commit()

@app.route('/insert_achievement_samples')
def insert_achievement_samples():
    try:
        # Sample achievement data
        sample_achievements = [
            {
                "name": "Vocabulary Novice",
                "description": "Learn your first 10 words",
                "points_reward": 100,
                "requirement": 10
            },
            {
                "name": "Word Collector",
                "description": "Learn 50 different words",
                "points_reward": 250,
                "requirement": 50
            },
            {
                "name": "Language Master",
                "description": "Learn 100 words and maintain a 90% accuracy",
                "points_reward": 500,
                "requirement": 100
            },
            {
                "name": "Flashcard Champion",
                "description": "Complete 20 flashcard sessions",
                "points_reward": 300,
                "requirement": 20
            },
            {
                "name": "Quiz Expert",
                "description": "Score 90% or higher in 10 multiple choice quizzes",
                "points_reward": 400,
                "requirement": 10
            },
            {
                "name": "Matching Pro",
                "description": "Complete 15 matching games with perfect score",
                "points_reward": 350,
                "requirement": 15
            }
        ]
        
        # Insert achievements with pokemon_id skipping by 3 (3, 6, 9, 12, 15, 18)
        pokemon_ids = list(range(3, 19, 3))  # [3, 6, 9, 12, 15, 18]
        
        achievements_added = 0
        for i, achievement_data in enumerate(sample_achievements):
            if i < len(pokemon_ids):
                # Check if achievement already exists
                existing = Achievement.query.filter_by(
                    name=achievement_data["name"],
                    pokemon_id=pokemon_ids[i]
                ).first()
                
                if not existing:
                    new_achievement = Achievement(
                        pokemon_id=pokemon_ids[i],
                        name=achievement_data["name"],
                        description=achievement_data["description"],
                        points_reward=achievement_data["points_reward"],
                        requirement=achievement_data["requirement"]
                    )
                    db.session.add(new_achievement)
                    achievements_added += 1
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": f"Successfully added {achievements_added} sample achievements",
            "pokemon_ids_used": pokemon_ids[:len(sample_achievements)]
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/create_admin_now')
def create_admin_now():
    """ONE-TIME ROUTE to create admin account - REMOVE IN PRODUCTION!"""
    try:
        # Check if admin already exists
        existing = UserAcc.query.filter_by(email='admin@vocabulearner.com').first()
        
        if existing:
            # Update existing to admin
            existing.is_admin = True
            existing.password = generate_password_hash('admin123')
            db.session.commit()
            return "✅ Admin account UPDATED! admin@vocabulearner.com / admin123"
        else:
            # Create new admin
            admin = UserAcc(
                name="Admin User",
                email="admin@vocabulearner.com",
                password=generate_password_hash('admin123'),
                is_admin=True
            )
            db.session.add(admin)
            db.session.commit()
            return "✅ Admin account CREATED! admin@vocabulearner.com / admin123"
            
    except Exception as e:
        db.session.rollback()
        return f"❌ Error: {str(e)}"

# ============ EMAIL VERIFICATION ROUTES ============
@app.route('/api/request_email_change', methods=['POST'])
def request_email_change():
    try:
        if 'user_id' not in session:
            return jsonify({'success': False, 'error': 'Not logged in'}), 401
        
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        new_email = data.get('new_email', '').strip().lower()
        
        if not new_email:
            return jsonify({'success': False, 'error': 'Email is required'}), 400
        
        import re
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_regex, new_email):
            return jsonify({'success': False, 'error': 'Invalid email format'}), 400
        
        user_id = session['user_id']
        current_user = UserAcc.query.get(user_id)
        
        if not current_user:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        # Check if email already exists
        existing_user = UserAcc.query.filter(
            UserAcc.email == new_email,
            UserAcc.user_id != current_user.user_id
        ).first()
        
        if existing_user:
            return jsonify({'success': False, 'error': 'Email already in use'}), 400
        
        import random
        verification_code = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        
        # Store in session
        session['email_change'] = {
            'new_email': new_email,
            'verification_code': verification_code,
            'timestamp': datetime.utcnow().timestamp(),
            'user_id': current_user.user_id
        }
        
        # Send verification email to NEW email
        email_sent = send_verification_email(
            old_email=current_user.email,
            new_email=new_email,
            verification_code=verification_code
        )
        
        if email_sent:
            return jsonify({
                'success': True,
                'message': f'Verification email sent to {new_email}'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to send verification email'
            })
        
    except Exception:
        return jsonify({'success': False, 'error': 'Internal server error'}), 500
    
    
@app.route('/api/verify_email_change', methods=['POST'])
def verify_email_change():
    try:
        if 'user_id' not in session:
            return jsonify({'success': False, 'error': 'Not logged in'}), 401
        
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        # Get verification code from request
        verification_code = data.get('verification_code', '').strip()
        
        if not verification_code:
            return jsonify({'success': False, 'error': 'Verification code is required'}), 400
        
        user_id = session['user_id']
        current_user = UserAcc.query.get(user_id)
        
        if not current_user:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        if 'email_change' not in session:
            return jsonify({'success': False, 'error': 'No pending email change request'}), 400
        
        email_change_data = session['email_change']
        
        # Check if this is the correct user
        if email_change_data['user_id'] != current_user.user_id:
            return jsonify({'success': False, 'error': 'Invalid request'}), 400
        
        # ONLY check the verification code, not the email
        if email_change_data['verification_code'] != verification_code:
            return jsonify({'success': False, 'error': 'Invalid verification code'}), 400
        
        # FIXED: Better timestamp checking
        import time
        from datetime import datetime, timedelta
        
        # Get the timestamp from session
        stored_timestamp = email_change_data['timestamp']
        
        # Calculate if 10 minutes have passed
        current_utc_time = datetime.utcnow().timestamp()  # Use UTC for consistency
        
        if current_utc_time - stored_timestamp > 600:  # 10 minutes
            del session['email_change']
            return jsonify({'success': False, 'error': 'Verification code expired'}), 400
        
        # Get the new email from session (not from request)
        new_email = email_change_data['new_email']
        
        # Check if email is still available
        existing_user = UserAcc.query.filter(
            UserAcc.email == new_email,
            UserAcc.user_id != current_user.user_id
        ).first()
        
        if existing_user:
            del session['email_change']
            return jsonify({'success': False, 'error': 'Email is no longer available'}), 400
        
        # Update user's email
        current_user.email = new_email
        db.session.commit()
        
        # Clear the email change data from session
        del session['email_change']
        
        return jsonify({'success': True, 'message': 'Email updated successfully'})
        
    except Exception as e:
        # For debugging, add logging
        print(f"Error in verify_email_change: {str(e)}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500

@app.route('/api/resend_verification_code', methods=['POST'])
def resend_verification_code():
    try:
        if 'user_id' not in session:
            return jsonify({'success': False, 'error': 'Not logged in'}), 401
        
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        new_email = data.get('new_email', '').strip().lower()
        
        if not new_email:
            return jsonify({'success': False, 'error': 'Email is required'}), 400
        
        if 'email_change' not in session:
            return jsonify({'success': False, 'error': 'No pending email change'}), 400
        
        email_change_data = session['email_change']
        user_id = session['user_id']
        current_user = UserAcc.query.get(user_id)
        
        if not current_user:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        if email_change_data['new_email'] != new_email:
            return jsonify({'success': False, 'error': 'Email mismatch'}), 400
        
        # FIXED: Use UTC timestamp for consistency
        import time
        from datetime import datetime
        
        stored_timestamp = email_change_data['timestamp']
        current_utc_time = datetime.utcnow().timestamp()
        
        if current_utc_time - stored_timestamp > 600:
            del session['email_change']
            return jsonify({'success': False, 'error': 'Previous code expired'}), 400
        
        import random
        verification_code = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        
        session['email_change'] = {
            'new_email': new_email,
            'verification_code': verification_code,
            'timestamp': datetime.utcnow().timestamp(),  # Use UTC
            'user_id': current_user.user_id
        }
        
        email_sent = send_verification_email(
            old_email=current_user.email,
            new_email=new_email,
            verification_code=verification_code
        )
        
        if email_sent:
            return jsonify({
                'success': True,
                'message': f'New verification email sent to {new_email}'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to send verification email'
            })
        
    except Exception as e:
        print(f"Error in resend_verification_code: {str(e)}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500
    

# ============ EMAIL HELPER FUNCTION ============
def send_verification_email(old_email, new_email, verification_code):
    """Send verification email to NEW email address"""
    try:
        # Load email settings from .env file
        SMTP_SERVER = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
        SMTP_PORT = int(os.getenv('MAIL_PORT', 587))
        EMAIL_ADDRESS = os.getenv('MAIL_USERNAME', 'vocabulearner.system@gmail.com')
        EMAIL_PASSWORD = os.getenv('MAIL_PASSWORD', '')
        
        # Check if email credentials are available
        if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
            return False
        
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = 'VocabuLearner - Email Change Verification'
        msg['From'] = EMAIL_ADDRESS
        msg['To'] = new_email  # Send to NEW email address
        
        # Email content
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 10px;">
                <h1 style="color: #4169e1; text-align: center;">VocabuLearner</h1>
                <h2 style="color: #333;">Email Change Verification</h2>
                
                <p>Hello,</p>
                
                <p>You requested to change your VocabuLearner email address to this email.</p>
                
                <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px 0; text-align: center;">
                    <h3 style="color: #4169e1; margin: 0;">Verification Code</h3>
                    <div style="font-size: 32px; font-weight: bold; letter-spacing: 10px; color: #228b22; margin: 10px 0;">
                        {verification_code}
                    </div>
                    <p style="font-size: 12px; color: #666; margin: 0;">
                        This code will expire in 10 minutes
                    </p>
                </div>
                
                <p>If you did not request this change, please ignore this email.</p>
                
                <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
                
                <p style="font-size: 12px; color: #666; text-align: center;">
                    © 2025 VocabuLearner. All rights reserved.
                </p>
            </div>
        </body>
        </html>
        """
        
        text = f"""
        VocabuLearner - Email Change Verification
        
        Hello,
        
        You requested to change your VocabuLearner email address to this email.
        
        Verification Code: {verification_code}
        This code will expire in 10 minutes.
        
        If you did not request this change, please ignore this email.
        
        © 2025 VocabuLearner
        """
        
        part1 = MIMEText(text, 'plain')
        part2 = MIMEText(html, 'html')
        
        msg.attach(part1)
        msg.attach(part2)
        
        # Send email
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.send_message(msg)
        
        return True
        
    except Exception:
        return False

@app.route('/api/delete_account', methods=['DELETE'])
def delete_account():
    try:
        # Check if user is logged in via session
        if 'user_id' not in session:
            return jsonify({'success': False, 'error': 'Not logged in'}), 401
        
        user_id = session['user_id']
        
        # Delete all user data in the correct order (respect foreign key constraints)
        # Delete notifications first (depends on user)
        Notification.query.filter_by(user_id=user_id).delete()
        
        # Delete word history (if it references UserWords, but it doesn't in your model)
        # Delete user words
        UserWords.query.filter_by(user_id=user_id).delete()
        
        # Delete user achievements
        UserAchievement.query.filter_by(user_id=user_id).delete()
        
        # Delete the user
        user = UserAcc.query.get(user_id)
        if user:
            db.session.delete(user)
            db.session.commit()
            
            # Clear session
            session.clear()
            
            return jsonify({'success': True, 'message': 'Account deleted successfully'})
        else:
            return jsonify({'success': False, 'error': 'User not found'}), 404
            
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting account: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to delete account. Please try again or contact support.'}), 500

@app.route('/api/update_pokemon_name', methods=['POST'])
@login_required
def update_pokemon_name():
    user_id = session.get('user_id')
    user = UserAcc.query.get(user_id)
   
    if not user:
        return jsonify({'success': False, 'error': 'User not found'})
   
    data = request.json
    new_name = data.get('pokemon_name', '').strip()
   
    if not new_name:
        return jsonify({'success': False, 'error': 'Name cannot be empty'})
   
    if len(new_name) > 50:
        return jsonify({'success': False, 'error': 'Name too long (max 50 characters)'})
   
    # Update custom Pokémon name
    user.pokemon_name = new_name
    db.session.commit()
   
    return jsonify({'success': True, 'message': 'Pokémon name updated!'})


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/api/upload_avatar', methods=['POST'])
@login_required
def upload_avatar():
    try:
        user_id = session.get('user_id')
        user = UserAcc.query.get(user_id)
       
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404
       
        if 'avatar' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'})
       
        file = request.files['avatar']
       
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'})
       
        if not file or not allowed_file(file.filename):
            return jsonify({'success': False, 'error': 'Invalid file type. Allowed: PNG, JPG, JPEG, GIF, WEBP'})
       
        # Create upload directory if it doesn't exist
        upload_path = app.config['UPLOAD_FOLDER']
        os.makedirs(upload_path, exist_ok=True)
       
        # Generate unique filename
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        extension = file.filename.rsplit('.', 1)[1].lower()
        filename = f"user_{user_id}_{timestamp}.{extension}"
        filepath = os.path.join(upload_path, filename)


        file.save(filepath)


        avatar_url = f"/static/uploads/avatars/{filename}"
       
        # Try to update, but handle if column doesn't exist
        try:
            user.profile_picture = avatar_url
            db.session.commit()
            return jsonify({
                'success': True,
                'avatar_url': avatar_url,
                'message': 'Avatar updated successfully'
            })
        except Exception as e:
            db.session.rollback()
            # If profile_picture column doesn't exist, just return success without saving to DB
            return jsonify({
                'success': True,
                'avatar_url': avatar_url,
                'message': 'Avatar preview updated (not saved to database)'
            })
           
    except Exception as e:
        print(f"Avatar upload error: {str(e)}")
        return jsonify({'success': False, 'error': 'Server error during upload'}), 500


def get_current_user():
    if 'user_id' in session:
        return UserAcc.query.get(session['user_id'])
    return None


@app.route('/select_pokemon')
@login_required
def select_pokemon():
    # Get all available Pokémon
    all_pokemon = Pokemon.query.all()
    current_user = UserAcc.query.get(session['user_id'])
   
    return render_template('select_pokemon.html',
                         all_pokemon=all_pokemon,
                         current_pokemon_id=current_user.pokemon_id)


@app.route('/')
def home():
    return render_template('index.html')


from datetime import datetime


@app.route('/api/update_profile', methods=['POST'])
@login_required
def update_profile():
    user_id = session.get('user_id')
    user = UserAcc.query.get(user_id)
   
    if not user:
        return jsonify({'error': 'User not found'}), 404
   
    data = request.json
    field = data.get('field')
    value = data.get('value')
   
    if field == 'name':
        user.name = value
    elif field == 'email':
        # Check if email already exists
        existing_user = UserAcc.query.filter_by(email=value).first()
        if existing_user and existing_user.user_id != user_id:
            return jsonify({'error': 'Email already in use'}), 400
        user.email = value
    else:
        return jsonify({'error': 'Invalid field'}), 400
   
    try:
        db.session.commit()
        return jsonify({'message': 'Profile updated successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = UserAcc.query.filter_by(email=form.email.data).first()
        if user and check_password_hash(user.password, form.password.data):
            
            
            # Update streak on login
            update_user_streak(user)
            
            # Store user info in session
            session['user_id'] = user.user_id
            session['username'] = user.name
            session['is_admin'] = user.is_admin  # Store admin status in session
            
            # Check if user is admin and redirect accordingly
            if user.is_admin:
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('dashboard'))
        else:
            flash("Invalid email or password.", "danger")
    return render_template('login.html', form=form)


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    form = SignupForm()
    if form.validate_on_submit():
        # Check if passwords match
        if form.password.data != form.confirm_password.data:
            flash("Passwords do not match.", "danger")
            return render_template('signup.html', form=form)


        # Check if email already exists
        existing_email = UserAcc.query.filter_by(email=form.email.data).first()
        if existing_email:
            flash("This email is already registered. Please log in.", "danger")
            return render_template('signup.html', form=form)


        # Check if username already exists
        existing_name = UserAcc.query.filter_by(name=form.username.data).first()
        if existing_name:
            flash("This username is already taken. Please choose a different one.", "danger")
            return render_template('signup.html', form=form)


        # Hash the password
        hashed_pw = generate_password_hash(form.password.data)


        # Create new user
        new_user = UserAcc(
            name=form.username.data,
            email=form.email.data,
            password=hashed_pw
        )
        db.session.add(new_user)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("This email or username is already registered. Please log in.", "warning")
            return redirect(url_for('login'))

        return redirect(url_for('login'))


    # If validation fails (e.g. empty fields), WTForms will handle it.
    if form.errors:
        flash("Please correct the errors in the form.", "danger")


    return render_template('signup.html', form=form)


@app.route('/logout')
def logout():
    # Clear all session data
    session.clear()
    # Optional: flash a message
    flash('You have been logged out.', 'info')
    return redirect(url_for('home'))


@app.route('/forgotpass', methods=['GET', 'POST'])
def forgotpass():
    form = ForgotPasswordForm()
    
    if form.validate_on_submit():
        email = form.email.data.strip()
        new_password = form.password.data
        confirm_password = form.confirm_password.data
        
        user = UserAcc.query.filter_by(email=email).first()
        
        if not user:
            flash('Email not found', 'danger')
            return render_template('forgotpass.html', form=form)
        
        # WTForms already validates password length and match
        # Update password
        user.password = generate_password_hash(new_password)
        db.session.commit()
        
        flash('Password updated successfully! You can now login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('forgotpass.html', form=form)


@app.route('/features')
def features():
    return render_template('features.html')


def get_word_of_the_day():
    today = date.today()


    # Check if a word was already shown today
    history = WordHistory.query.filter_by(date_shown=today).first()
   
    if history:
        chosen = Vocabulary.query.get(history.word_id)
        # Check if chosen exists (word might have been deleted)
        if not chosen:
            # If the word was deleted, remove the history entry and get a new word
            db.session.delete(history)
            db.session.commit()
            history = None
   
    if not history:
        # Exclude words shown in the last 7 days
        recent_ids = [h.word_id for h in WordHistory.query.filter(
            WordHistory.date_shown >= today - timedelta(days=7)
        ).all()]


        # Get all words
        all_words = Vocabulary.query.all()
       
        # If no words exist in the database, return a default response
        if not all_words:
            return {
                "word_id": 0,
                "word": "No words available",
                "pronunciation": "",
                "type": "",
                "definition": "Please add vocabulary words to your collection.",
                "example": ""
            }
       
        # Filter out recently shown words
        available_words = [word for word in all_words if word.word_id not in recent_ids]
       
        # If all words have been shown recently, use any word
        if not available_words:
            available_words = all_words
       
        # Choose a random word
        chosen = random.choice(available_words)


        # Save to history
        new_entry = WordHistory(word_id=chosen.word_id, date_shown=today)
        db.session.add(new_entry)
        db.session.commit()


    # Now chosen should definitely exist
    if not chosen:
        return {
            "word_id": 0,
            "word": "Error loading word",
            "pronunciation": "",
            "type": "",
            "definition": "Unable to load vocabulary word.",
            "example": ""
        }


    # Fetch details from Dictionary API
    try:
        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{chosen.word}"
        response = requests.get(url)
        if not response.ok:
            return {
                "word_id": chosen.word_id,
                "word": chosen.word,
                "pronunciation": "",
                "type": chosen.category or "",
                "definition": chosen.definition or "Definition not found",
                "example": chosen.example_sentence or ""
            }


        data = response.json()[0]


        pronunciation = ""
        if data.get("phonetics"):
            pronunciation = data["phonetics"][0].get("text", "")


        meaning_block = data["meanings"][0]
        definition_block = meaning_block["definitions"][0]


        # Example handling: loop through all definitions
        example = ""
        for d in meaning_block["definitions"]:
            if "example" in d:
                example = d["example"]
                break


        return {
            "word_id": chosen.word_id,
            "word": chosen.word,
            "pronunciation": pronunciation,
            "type": meaning_block.get("partOfSpeech", ""),
            "definition": definition_block.get("definition", ""),
            "example": example  # stays blank if none found
        }
    except Exception as e:
        print(f"Error fetching word details: {e}")
        # Fallback to database values
        return {
            "word_id": chosen.word_id,
            "word": chosen.word,
            "pronunciation": "",
            "type": chosen.category or "",
            "definition": chosen.definition or "Definition unavailable",
            "example": chosen.example_sentence or ""
        }
        
def create_daily_reminder_notification(user_id):
    """Create a single test notification - NO THREADING"""
    notification = Notification(
        user_id=user_id,
        title="⏰ Practice Time!",
        message="Test notification - Refresh to see!",
        notification_type='test',
        is_read=False,
        created_at=datetime.utcnow()  # Use UTC
    )
    
    db.session.add(notification)
    db.session.commit()
    
    return True

def start_auto_notifications(user_id):
    """Start auto notifications but prevent multiple threads"""
    # Check if auto notifications already exist today
    today = datetime.now(ph_timezone).date()
    today_start = datetime.combine(today, datetime.min.time())
    
    existing_auto = Notification.query.filter_by(
        user_id=user_id,
        notification_type='auto_reminder'
    ).filter(
        Notification.created_at >= today_start
    ).first()
    
    # Only start if no auto notifications exist today
    if not existing_auto:
        create_daily_reminder_notification(user_id)

def create_morning_motivation(user_id, streak_days):
    """Create morning motivation notification"""
    messages = [
        "Good morning! Ready to learn some new words today?",
        "Start your day right with a quick vocabulary session!",
        "Your Pokémon is waiting for you to learn new words!",
        "Keep your streak alive - learn something new today!"
    ]
    
    if streak_days > 0:
        message = f"You're on a {streak_days}-day streak! Keep it going with today's learning session!"
    else:
        message = random.choice(messages)
    
    notification = Notification(
        user_id=user_id,
        title="🌅 Daily Learning Reminder",
        message=message,
        notification_type='motivation',
        is_read=False,
        created_at=datetime.now(ph_timezone)
    )
    db.session.add(notification)
    db.session.commit()
    return notification

# ---------- NOTIFICATION ROUTES ----------
@app.route('/api/notifications')
@login_required
def get_notifications():
    """Get notifications for current user"""
    try:
        user_id = session.get('user_id')
        
        notifications = Notification.query.filter_by(
            user_id=user_id
        ).order_by(
            Notification.created_at.desc()
        ).limit(20).all()
        
        # Format for frontend
        notifications_data = []
        for notif in notifications:
            # Calculate time ago
            now = datetime.utcnow()
            
            if not notif.created_at:
                time_ago = "Just now"
            else:
                diff = now - notif.created_at
                
                if diff.days > 0:
                    time_ago = f"{diff.days}d ago"
                elif diff.seconds >= 3600:
                    hours = diff.seconds // 3600
                    time_ago = f"{hours}h ago"
                elif diff.seconds >= 60:
                    minutes = diff.seconds // 60
                    time_ago = f"{minutes}m ago"
                else:
                    time_ago = "Just now"
            
            notifications_data.append({
                'id': notif.notification_id,
                'title': notif.title,
                'message': notif.message,
                'time': time_ago,
                'unread': not notif.is_read,
                'type': notif.notification_type,
                'timestamp': notif.created_at.isoformat() if notif.created_at else None
            })
        
        # **FIX: Return proper JSON with UTF-8 charset**
        response = jsonify(notifications_data)
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
        
    except Exception as e:
        print(f"ERROR in get_notifications: {str(e)}")
        import traceback
        traceback.print_exc()
        # Return empty array with proper headers
        response = jsonify([])
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response

@app.route('/api/notifications/mark_read/<int:notification_id>', methods=['POST'])
@login_required
def mark_notification_read(notification_id):
    """Mark notification as read"""
    notification = Notification.query.get(notification_id)
    
    if not notification:
        response = jsonify({'success': False, 'error': 'Notification not found'})
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response, 404
    
    if notification.user_id != session.get('user_id'):
        response = jsonify({'success': False, 'error': 'Unauthorized'})
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response, 403
    
    notification.is_read = True
    db.session.commit()
    
    response = jsonify({'success': True})
    response.headers['Content-Type'] = 'application/json; charset=utf-8'
    return response

@app.route('/api/notifications/clear_all', methods=['POST'])
@login_required
def clear_all_notifications():
    """Clear all notifications for current user"""
    user_id = session.get('user_id')
    
    try:
        Notification.query.filter_by(user_id=user_id).delete()
        db.session.commit()
        response = jsonify({'success': True, 'message': 'All notifications cleared'})
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        db.session.rollback()
        response = jsonify({'success': False, 'error': str(e)})
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response, 500
    
@app.route('/api/create_auto_notification', methods=['POST'])
@login_required
def create_auto_notification():
    """Create an auto-notification from frontend"""
    user = get_current_user()
    
    data = request.json
    title = data.get('title', 'VocabuLearner Update')
    message = data.get('message', 'Time to learn!')
    
    notification = Notification(
        user_id=user.user_id,
        title=title,
        message=message,
        notification_type='auto',
        is_read=False,
        created_at=datetime.utcnow()
    )
    db.session.add(notification)
    db.session.commit()
    
    return jsonify({
        'success': True, 
        'message': 'Auto-notification created',
        'notification_id': notification.notification_id
    })

# ---------- UPDATE DASHBOARD ROUTE ----------
@app.route('/dashboard')
@login_required
def dashboard():
    user = get_current_user()
    showStarterModal = user.pokemon_id is None
    
    # Get Pokémon from database
    pokemons = Pokemon.query.all()
    pokemons_list = []
    for p in pokemons:
        pokemons_list.append({
            'id': p.pokemon_id,
            'name': p.name,
            'img': p.url or '',
            'rarity': p.rarity
        })
    
    # --- Progress preview stats ---
    today = datetime.utcnow().date()
    start_week = today - timedelta(days=6)
    
    weekly_counts = (
        db.session.query(func.date(UserWords.date_learned), func.count(UserWords.word_id))
        .filter(UserWords.user_id == user.user_id,
                UserWords.date_learned >= start_week)
        .group_by(func.date(UserWords.date_learned))
        .all()
    )
    weekly_total = sum(count for _, count in weekly_counts)
    streak = user.current_streak
    
    # Get word of the day - always show today's word (even if already claimed)
    # We'll use a daily word selection that's consistent for the whole day
    today_str = today.strftime('%Y-%m-%d')
    
    word_of_day = get_daily_word_of_day()
    if not word_of_day:
        word_of_day = Vocabulary.query.filter_by(is_word_of_day=True).order_by(func.random()).first()
    
    # If no Word of Day exists, get any word
    if not word_of_day:
        word_of_day = Vocabulary.query.order_by(func.random()).first()
    
    # Check if user has already learned this word
    user_has_word = False
    if word_of_day:
        existing_link = UserWords.query.filter_by(user_id=user.user_id, word_id=word_of_day.word_id).first()
        user_has_word = existing_link is not None
    
    if word_of_day:
        word_data = {
            'word_id': word_of_day.word_id,
            'word': word_of_day.word,
            'definition': word_of_day.definition,
            'example': word_of_day.example_sentence,
            'type': word_of_day.category if word_of_day.category else 'General',
            'pronunciation': 'N/A',
            'user_has_word': user_has_word
        }
    else:
        # If there are no words in the database
        word_data = {
            'word_id': 0,
            'word': 'No Words Available',
            'definition': 'Add some words to get started!',
            'example': 'Use the "Add New Word" feature.',
            'type': 'General',
            'pronunciation': '',
            'user_has_word': True
        }
    
    # --- Calculate user rank ---
    # Get all non-admin users ordered by total_points (descending)
    users = UserAcc.query.filter_by(is_admin=False).order_by(UserAcc.total_points.desc(), UserAcc.name).all()
    
    # Find user's rank
    user_rank = None
    for rank, u in enumerate(users, start=1):
        if u.user_id == user.user_id:
            user_rank = rank
            break
    
    # If user is admin or not found in ranking, show appropriate rank
    if user_rank is None:
        user_rank = len(users) + 1  # User is admin, so they're not in the ranking
    
    # --- CREATE ENGAGING NOTIFICATION ---
    # Create more engaging notifications with variety
    import random
    notification_messages = [
        "📚 Time to learn new words! Your vocabulary journey continues.",
        "🌟 Great work! Keep building your word collection.",
        "⏰ Daily practice makes perfect! Review your words today.",
        "🎯 New challenges await! Test your vocabulary skills.",
        "🔥 Your learning streak is impressive! Don't stop now.",
        "💡 Did you know? Learning 10 new words a week boosts language skills by 40%.",
        "✨ Your Pokémon partner is proud of your progress!",
        "📖 A new word of the day is waiting for you!",
        "🏆 You're climbing the leaderboard! Keep going!",
        "🧠 Strengthen your memory with a quick review session."
    ]
    
    # Create notification only once per hour to avoid spam
    last_notification = Notification.query.filter_by(
        user_id=user.user_id,
        notification_type='auto'
    ).order_by(Notification.created_at.desc()).first()
    
    should_create_notification = True
    if last_notification and last_notification.created_at:
        time_since_last = datetime.utcnow() - last_notification.created_at
        if time_since_last.total_seconds() < 3600:  # Less than 1 hour
            should_create_notification = False
    
    if should_create_notification:
        notification = Notification(
            user_id=user.user_id,
            title="VocabuLearner Reminder",
            message=random.choice(notification_messages),
            notification_type='auto',
            is_read=False,
            created_at=datetime.utcnow()
        )
        db.session.add(notification)
        db.session.commit()
        print(f"✅ Created auto notification for user {user.user_id}")
    
    # Check for flash messages to show claim notice
    # This will be handled by the add_to_collection route
    
    return render_template(
        'dashboard.html',
        showStarterModal=showStarterModal,
        starterPokemon=user.pokemon_id,
        pokemons=pokemons_list,
        weekly_total=weekly_total,
        streak=streak,
        total_points=user.total_points,
        word_data=word_data,
        current_user=user,
        user_rank=user_rank
    )

@app.route('/add_to_collection/<int:word_id>', methods=['POST'])
@login_required
def add_to_collection(word_id):
    user = get_current_user()
    
    # Check if word exists
    word = Vocabulary.query.get(word_id)
    if not word:
        flash('Invalid word!', 'danger')
        return redirect(url_for('dashboard'))
    
    # Check if user already has this word
    existing_link = UserWords.query.filter_by(user_id=user.user_id, word_id=word_id).first()
    if not existing_link:
        # Add word to user's collection
        user_word = UserWords(user_id=user.user_id, word_id=word_id)
        db.session.add(user_word)
        user.total_points = (user.total_points or 0) + word.points_value
        
        # Check if this is a Word of the Day
        if word.is_word_of_day:
            flash(f"✨ '{word.word}' has been added to your collection! Today's Word of the Day claimed! +{word.points_value} EXP", 'success')
        else:
            flash(f"Word '{word.word}' added to your collection! +{word.points_value} EXP", 'success')
        
        db.session.commit()
    else:
        flash(f"Word '{word.word}' is already in your collection!", 'info')
    
    return redirect(url_for('dashboard'))

def get_daily_word_of_day():
    """Get a consistent Word of the Day for the current day."""
    today = datetime.utcnow().date()
    today_str = today.strftime('%Y-%m-%d')
    
    # You could store daily word selection in a cache or database
    # For simplicity, we'll use a predictable method based on date
    import hashlib
    
    # Create a hash based on today's date
    date_hash = hashlib.md5(today_str.encode()).hexdigest()
    hash_int = int(date_hash, 16)
    
    # Get all Word of Day candidates
    word_of_day_candidates = Vocabulary.query.filter_by(is_word_of_day=True).all()
    
    if not word_of_day_candidates:
        return None
    
    # Select word based on hash (consistent for the day)
    word_index = hash_int % len(word_of_day_candidates)
    return word_of_day_candidates[word_index]

@app.route('/api/get_vocabulary_for_review')
@login_required
def get_vocabulary_for_review():
    user = get_current_user()
    
    try:
        # Get words that the user has already learned
        user_learned_word_ids = [word.word_id for word in UserWords.query.filter_by(user_id=user.user_id).all()]
        
        # If user has learned words, get words they haven't learned yet
        # Otherwise, get all words
        if user_learned_word_ids:
            words = Vocabulary.query.filter(~Vocabulary.word_id.in_(user_learned_word_ids)).all()
        else:
            words = Vocabulary.query.all()
        
        # Convert to list of dictionaries
        words_list = []
        for word in words:
            words_list.append({
                'word_id': word.word_id,
                'word': word.word,
                'definition': word.definition,
                'example_sentence': word.example_sentence,
                'category': word.category,
                'points_value': word.points_value
            })
        
        # Shuffle the words
        import random
        random.shuffle(words_list)
        
        # Limit to 10 words for the flashcard game
        words_list = words_list[:10]
        
        return jsonify({
            'success': True,
            'words': words_list,
            'total_words': len(words_list)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/add_review_exp', methods=['POST'])
@login_required
def add_review_exp():
    """Add EXP earned from flashcard review to user account."""
    user = get_current_user()
    
    try:
        data = request.get_json()
        exp_earned = data.get('exp_earned', 0)
        
        # Update user's total points
        user.total_points = (user.total_points or 0) + exp_earned
        
        # Check for Pokémon evolution (optional)
        check_and_update_pokemon_evolution(user)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'{exp_earned} EXP added to your account!',
            'new_total_points': user.total_points
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/choose_partner', methods=['POST'])
@login_required
def choose_partner():
    user = get_current_user()
   
    # Already has Pokémon? Redirect
    if user.pokemon_id is not None:
        flash("You already have a starter Pokémon.", "info")
        return redirect(url_for('dashboard'))
   
    # Get pokemon_id safely
    pokemon_id = request.form.get('pokemon_id', '').strip()
   
    # Debug
    print(f"DEBUG: Received pokemon_id: '{pokemon_id}'")
   
    # Validate
    if not pokemon_id:
        flash("Please select a Pokémon partner.", "danger")
        return redirect(url_for('dashboard'))
   
    try:
        chosen_id = int(pokemon_id)
    except ValueError:
        flash("Invalid Pokémon selection.", "danger")
        return redirect(url_for('dashboard'))
   
    # Save to database
    user.pokemon_id = chosen_id
    db.session.commit()
   
    flash(f"Starter Pokémon chosen successfully!", "success")
    return redirect(url_for('dashboard'))


@app.route('/profile')
@login_required
def profile():
    user = get_current_user()
    
    # Calculate words learned
    words_learned = UserWords.query.filter_by(user_id=user.user_id).count()
    
    # Get current Pokémon partner (including evolution based on points)
    pokemon = None
    pokemon_display_name = user.pokemon_name  # User's custom name for their Pokémon
    
    if user.pokemon_id:
        starter = Pokemon.query.get(user.pokemon_id)
        if starter:
            # Get all Pokémon in the same family
            evolution_line = (
                Pokemon.query
                .filter_by(family_id=starter.family_id)
                .order_by(Pokemon.min_points_required)
                .all()
            )
            
            # Find current Pokémon based on points (not just the starter)
            current_pokemon = None
            for evo in evolution_line:
                if user.total_points >= evo.min_points_required:
                    current_pokemon = evo
            
            # If no evolution qualifies yet, show the starter
            if not current_pokemon:
                current_pokemon = starter
            
            pokemon = current_pokemon
            
            # If user hasn't set a custom name, use Pokémon's name
            if not pokemon_display_name:
                pokemon_display_name = pokemon.name
    
    # Get all achievements (simplified without UserAchievements)
    all_achievements = Achievement.query.all() if hasattr(Achievement, 'query') else []
    
    # Get Pokémon for achievements
    achievement_pokemon = {}
    for achievement in all_achievements:
        if hasattr(achievement, 'pokemon_id') and achievement.pokemon_id:
            poke = Pokemon.query.get(achievement.pokemon_id)
            if poke:
                achievement_pokemon[achievement.achievement_id] = poke
    
    # Calculate achievements based on user stats (simplified)
    user_achievements = []
    
    # Example: Streak achievement
    if user.current_streak >= 7:
        user_achievements.append({'achievement_id': 1, 'name': '7-Day Streak', 'description': 'Maintain a 7-day learning streak'})
    if user.current_streak >= 30:
        user_achievements.append({'achievement_id': 2, 'name': '30-Day Streak', 'description': 'Maintain a 30-day learning streak'})
    
    # Words learned achievement
    if words_learned >= 10:
        user_achievements.append({'achievement_id': 3, 'name': 'Word Collector', 'description': 'Learn 10 words'})
    if words_learned >= 50:
        user_achievements.append({'achievement_id': 4, 'name': 'Vocabulary Master', 'description': 'Learn 50 words'})
    if words_learned >= 100:
        user_achievements.append({'achievement_id': 5, 'name': 'Word Wizard', 'description': 'Learn 100 words'})
    
    # Points/EXP achievement
    if user.total_points >= 100:
        user_achievements.append({'achievement_id': 6, 'name': 'EXP Expert', 'description': 'Earn 100 EXP points'})
    if user.total_points >= 500:
        user_achievements.append({'achievement_id': 7, 'name': 'EXP Master', 'description': 'Earn 500 EXP points'})
    
    return render_template(
        'profile.html',
        user=user,
        words_learned=words_learned,
        pokemon=pokemon,
        pokemon_display_name=pokemon_display_name,
        user_achievements=user_achievements,  # Now using calculated achievements
        all_achievements=all_achievements,
        achievement_pokemon=achievement_pokemon
    )


@app.route('/challenges')
def challenges():
    return render_template('challenges.html')

@app.route('/insert_vocabulary_word_of_day')
def insert_vocabulary_word_of_day():
    vocabulary_data = [
        # All words marked as Word of the Day (is_word_of_day=True)
        ('Ephemeral', 'Lasting for a very short time', 'The beauty of cherry blossoms is ephemeral.', 'Adjective', 15, True),
        ('Serendipity', 'The occurrence of events by chance in a happy or beneficial way', 'Finding this book was pure serendipity.', 'Noun', 15, True),
        ('Resilient', 'Able to withstand or recover quickly from difficult conditions', 'Children are remarkably resilient.', 'Adjective', 12, True),
        ('Ubiquitous', 'Present, appearing, or found everywhere', 'Mobile phones have become ubiquitous in modern society.', 'Adjective', 14, True),
        ('Eloquent', 'Fluent or persuasive in speaking or writing', 'Her eloquent speech moved the entire audience.', 'Adjective', 13, True),
        ('Meticulous', 'Showing great attention to detail; very careful and precise', 'She is meticulous in her research work.', 'Adjective', 12, True),
        ('Pragmatic', 'Dealing with things sensibly and realistically', 'His pragmatic approach solved the problem efficiently.', 'Adjective', 12, True),
        ('Quintessential', 'Representing the most perfect example of a quality or class', 'He is the quintessential gentleman.', 'Adjective', 16, True),
        ('Vocabulary', 'The body of words used in a particular language', 'Expanding your vocabulary improves communication.', 'Noun', 10, True),
        ('Grammar', 'The set of structural rules governing the composition of sentences', 'Good grammar is essential for clear writing.', 'Noun', 10, True),
        ('Syntax', 'The arrangement of words and phrases to create well-formed sentences', 'The syntax of this sentence is incorrect.', 'Noun', 12, True),
        ('Semantics', 'The meaning of words, phrases, and sentences', 'Word order affects the semantics of a sentence.', 'Noun', 13, True),
        ('Etymology', 'The study of the origin of words and how their meanings have changed', 'The etymology of "breakfast" is "breaking the fast".', 'Noun', 15, True),
        ('Phonetics', 'The study of the sounds of human speech', 'Phonetics helps with correct pronunciation.', 'Noun', 12, True),
        ('Morphology', 'The study of the forms of words', 'Morphology examines how words are formed.', 'Noun', 14, True),
        ('Lexicon', 'The vocabulary of a person, language, or branch of knowledge', 'The medical lexicon contains many specialized terms.', 'Noun', 13, True),
        ('Dialect', 'A particular form of a language peculiar to a specific region', 'They speak a northern dialect of the language.', 'Noun', 11, True),
        ('Idiom', 'A group of words established by usage as having a meaning not deducible from individual words', '"Break a leg" is an idiom meaning "good luck".', 'Noun', 14, True),
        ('Ambiguous', 'Open to more than one interpretation; not having one obvious meaning', 'His reply was ambiguous and confusing.', 'Adjective', 13, True),
        ('Benevolent', 'Well meaning and kindly', 'She was known for her benevolent nature.', 'Adjective', 14, True),
        ('Candor', 'The quality of being open and honest in expression; frankness', 'I appreciate your candor about the situation.', 'Noun', 12, True),
        ('Diligent', 'Having or showing care in one\'s work or duties', 'He is a diligent student who always completes his assignments.', 'Adjective', 11, True),
        ('Empathy', 'The ability to understand and share the feelings of another', 'Her empathy made her an excellent counselor.', 'Noun', 13, True),
        ('Fortitude', 'Courage in pain or adversity', 'She showed great fortitude during her recovery.', 'Noun', 14, True),
        ('Gregarious', 'Fond of company; sociable', 'He was a gregarious person who loved parties.', 'Adjective', 15, True),
        ('Humility', 'A modest or low view of one\'s own importance', 'Despite his success, he maintained his humility.', 'Noun', 12, True),
        ('Integrity', 'The quality of being honest and having strong moral principles', 'He is a man of great integrity.', 'Noun', 13, True),
        ('Juxtaposition', 'The fact of two things being seen or placed close together with contrasting effect', 'The juxtaposition of old and new architecture was striking.', 'Noun', 16, True),
        ('Kaleidoscope', 'A constantly changing pattern or sequence of elements', 'The market was a kaleidoscope of colors and sounds.', 'Noun', 15, True),
        ('Lucid', 'Expressed clearly; easy to understand', 'Her explanation was lucid and helpful.', 'Adjective', 12, True),
    ]

    inserted_count = 0
    
    for word, definition, example_sentence, category, points_value, is_word_of_day in vocabulary_data:
        # Check if word already exists
        existing = Vocabulary.query.filter_by(word=word.lower()).first()
        if not existing:
            vocabulary = Vocabulary(
                word=word.lower(),
                definition=definition,
                example_sentence=example_sentence,
                category=category,
                points_value=points_value,
                is_word_of_day=is_word_of_day  # All True
            )
            db.session.add(vocabulary)
            inserted_count += 1
        else:
            print(f"Word '{word}' already exists in database")

    db.session.commit()
    
    return f"Vocabulary Word of the Day data inserted successfully! Added {inserted_count} new words as Word of the Day candidates."

@app.route('/insert_pokemon_data')
def insert_pokemon_data():
    pokemon_data = [
        # Bulbasaur Evolution Line (family_id = 1)
        ('Bulbasaur', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/1.png', 0, 'starter', 1),
        ('Ivysaur', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/2.png', 100, 'common', 1),
        ('Venusaur', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/3.png', 300, 'rare', 1),


        # Charmander Evolution Line (family_id = 2)
        ('Charmander', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/4.png', 0, 'starter', 2),
        ('Charmeleon', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/5.png', 100, 'common', 2),
        ('Charizard', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/6.png', 300, 'rare', 2),


        # Squirtle Evolution Line (family_id = 3)
        ('Squirtle', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/7.png', 0, 'starter', 3),
        ('Wartortle', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/8.png', 100, 'common', 3),
        ('Blastoise', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/9.png', 300, 'rare', 3),


        # Chikorita Evolution Line (family_id = 4)
        ('Chikorita', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/152.png', 0, 'starter', 4),
        ('Bayleef', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/153.png', 100, 'common', 4),
        ('Meganium', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/154.png', 300, 'rare', 4),


        # Cyndaquil Evolution Line (family_id = 5)
        ('Cyndaquil', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/155.png', 0, 'starter', 5),
        ('Quilava', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/156.png', 100, 'common', 5),
        ('Typhlosion', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/157.png', 300, 'rare', 5),


        # Totodile Evolution Line (family_id = 6)
        ('Totodile', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/158.png', 0, 'starter', 6),
        ('Croconaw', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/159.png', 100, 'common', 6),
        ('Feraligatr', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/160.png', 300, 'rare', 6),
    ]


    for name, url, min_points, rarity, family_id in pokemon_data:
        pokemon = Pokemon(name=name, url=url, min_points_required=min_points, rarity=rarity, family_id=family_id)
        db.session.add(pokemon)


    db.session.commit()
    return "Pokémon data inserted successfully!"


@app.route("/wordbank")
@login_required
def wordbank():
    user = get_current_user()
    # Join UserWords with Vocabulary to get word details
    user_words = (
        db.session.query(UserWords, Vocabulary)
        .join(Vocabulary, UserWords.word_id == Vocabulary.word_id)
        .filter(UserWords.user_id == user.user_id)
        .all()
    )
    return render_template("wordbank.html", words=user_words)




@app.route('/review')
@login_required
def review():
    # Get ALL words from Vocabulary table
    words = Vocabulary.query.order_by(func.random()).limit(20).all()
   
    words_data = []
    for word in words:
        # Make sure all fields exist and are not None
        word_entry = {
            "word_id": word.word_id,
            "word": word.word or "",
            "type": word.category or "adjective",  # default to adjective
            "definition": word.definition or f"Definition of {word.word}",
            "example": word.example_sentence or f"Example for {word.word}"
        }
        words_data.append(word_entry)
   
    # Debug print
    print(f"DEBUG: Sending {len(words_data)} words to template")
   
    return render_template('review.html',
                         words=words_data,  # Pass the list
                         words_count=len(words_data))


@app.route("/progress")
@login_required
def progress():
    user = get_current_user()
    today = datetime.utcnow().date()


    # --- DAILY (today, grouped by hour) ---
    start_day = datetime.combine(today, datetime.min.time())
    daily_counts = (
        db.session.query(func.extract('hour', UserWords.date_learned), func.count(UserWords.word_id))
        .filter(UserWords.user_id == user.user_id,
                UserWords.date_learned >= start_day)
        .group_by(func.extract('hour', UserWords.date_learned))
        .all()
    )
    daily_data = {int(hour): count for hour, count in daily_counts}


    # --- WEEKLY (last 7 days, grouped by date) ---
    start_week = today - timedelta(days=6)
    weekly_counts = (
        db.session.query(func.date(UserWords.date_learned), func.count(UserWords.word_id))
        .filter(UserWords.user_id == user.user_id,
                UserWords.date_learned >= start_week)
        .group_by(func.date(UserWords.date_learned))
        .all()
    )
    weekly_data = {str(date): count for date, count in weekly_counts}


    # --- MONTHLY (last 4 weeks, grouped by week number) ---
    start_month = today - timedelta(days=28)
    monthly_counts = (
        db.session.query(func.extract('week', UserWords.date_learned), func.count(UserWords.word_id))
        .filter(UserWords.user_id == user.user_id,
                UserWords.date_learned >= start_month)
        .group_by(func.extract('week', UserWords.date_learned))
        .all()
    )
    monthly_data = {int(week): count for week, count in monthly_counts}


    # Totals + Pokémon evolutions
    weekly_total = sum(weekly_data.values())


    return render_template("progress.html",
                           daily_data=daily_data,
                           weekly_data=weekly_data,
                           monthly_data=monthly_data,
                           weekly_total=weekly_total)


@app.route('/leaderboard')
@login_required
def leaderboard():
    current_user = get_current_user()
    
    # Get all NON-ADMIN users ordered by total_points (descending)
    users = UserAcc.query.filter_by(is_admin=False).order_by(UserAcc.total_points.desc(), UserAcc.name).all()
    
    # Get word counts for all users in one query
    from sqlalchemy import func
    word_counts = db.session.query(
        UserWords.user_id,
        func.count(UserWords.word_id).label('word_count')
    ).group_by(UserWords.user_id).all()
    
    # Convert to dictionary for easy lookup
    word_count_dict = {user_id: count for user_id, count in word_counts}
    
    # Prepare leaderboard data
    leaderboard_data = []
    current_user_word_count = 0
    user_rank = None
    
    for rank, user in enumerate(users, start=1):
        word_count = word_count_dict.get(user.user_id, 0)
        
        # Store current user's word count
        if user.user_id == current_user.user_id:
            current_user_word_count = word_count
            user_rank = rank
        
        leaderboard_data.append({
            'rank': rank,
            'user_id': user.user_id,  # ADD THIS LINE
            'username': user.name,
            'profile_picture': user.profile_picture,
            'score': user.total_points or 0,
            'words': word_count,
            'is_current_user': user.user_id == current_user.user_id
        })
    
    # Get top 3 for podium
    podium_users = leaderboard_data[:3] if leaderboard_data else []
    
    return render_template('leaderboard.html',
                         current_user=current_user,
                         current_user_word_count=current_user_word_count,
                         user_rank=user_rank or len(users) + 1,
                         podium_users=podium_users,
                         leaderboard_data=leaderboard_data)
    
@app.route('/profile/<int:user_id>')
@login_required
def view_profile(user_id):
    # Get the user to view
    user = UserAcc.query.get_or_404(user_id)
    
    # Get current user (logged in user)
    current_user = get_current_user()
    
    # Check if it's the current user's own profile
    is_own_profile = (user.user_id == current_user.user_id)
    
    # Get user's word count
    word_count = UserWords.query.filter_by(user_id=user.user_id).count()
    
    # Get user's Pokémon (including evolution based on points)
    pokemon = None
    pokemon_display_name = None
    
    if user.pokemon_id:
        starter = Pokemon.query.get(user.pokemon_id)
        if starter:
            # Get all Pokémon in the same family
            evolution_line = (
                Pokemon.query
                .filter_by(family_id=starter.family_id)
                .order_by(Pokemon.min_points_required)
                .all()
            )
            
            # Find current Pokémon based on points (not just the starter)
            current_pokemon = None
            for evo in evolution_line:
                if user.total_points >= evo.min_points_required:
                    current_pokemon = evo
            
            # If no evolution qualifies yet, show the starter
            if not current_pokemon:
                current_pokemon = starter
            
            pokemon = current_pokemon
            pokemon_display_name = user.pokemon_name or pokemon.name
    
    # Get all achievements (simplified without UserAchievements)
    all_achievements = Achievement.query.all() if hasattr(Achievement, 'query') else []
    
    # Get Pokémon for achievements
    achievement_pokemon = {}
    for achievement in all_achievements:
        if hasattr(achievement, 'pokemon_id') and achievement.pokemon_id:
            poke = Pokemon.query.get(achievement.pokemon_id)
            if poke:
                achievement_pokemon[achievement.achievement_id] = poke
    
    # Calculate achievements based on user stats (simplified)
    user_achievements = []
    
    # Example: Streak achievement
    if user.current_streak >= 7:
        user_achievements.append({'achievement_id': 1, 'name': '7-Day Streak', 'description': 'Maintain a 7-day learning streak'})
    if user.current_streak >= 30:
        user_achievements.append({'achievement_id': 2, 'name': '30-Day Streak', 'description': 'Maintain a 30-day learning streak'})
    
    # Words learned achievement
    if word_count >= 10:
        user_achievements.append({'achievement_id': 3, 'name': 'Word Collector', 'description': 'Learn 10 words'})
    if word_count >= 50:
        user_achievements.append({'achievement_id': 4, 'name': 'Vocabulary Master', 'description': 'Learn 50 words'})
    if word_count >= 100:
        user_achievements.append({'achievement_id': 5, 'name': 'Word Wizard', 'description': 'Learn 100 words'})
    
    # Points/EXP achievement
    if user.total_points >= 100:
        user_achievements.append({'achievement_id': 6, 'name': 'EXP Expert', 'description': 'Earn 100 EXP points'})
    if user.total_points >= 500:
        user_achievements.append({'achievement_id': 7, 'name': 'EXP Master', 'description': 'Earn 500 EXP points'})
    
    return render_template('view_profile.html',
                         user=user,
                         words_learned=word_count,
                         pokemon=pokemon,
                         pokemon_display_name=pokemon_display_name,
                         user_achievements=user_achievements,
                         all_achievements=all_achievements,
                         achievement_pokemon=achievement_pokemon,
                         is_own_profile=is_own_profile,
                         current_user=current_user)


@app.route("/add_word", methods=["GET", "POST"])
@login_required
def add_word():
    form = AddWordForm()
    user = get_current_user()
    
    # Function to check and update Pokémon evolution
    def check_and_update_pokemon_evolution(user):
        """Check if user qualifies for Pokémon evolution and update if needed."""
        if not user.pokemon_id:
            return False, None, None
        
        current_pokemon = Pokemon.query.get(user.pokemon_id)
        if not current_pokemon:
            return False, None, None
        
        # Get all Pokémon in the same family
        evolution_line = (
            Pokemon.query
            .filter_by(family_id=current_pokemon.family_id)
            .order_by(Pokemon.min_points_required)
            .all()
        )
        
        # Find the highest evolution the user qualifies for
        highest_evolution = None
        for evo in evolution_line:
            if user.total_points >= evo.min_points_required:
                highest_evolution = evo
        
        # If we found a higher evolution than current
        if highest_evolution and highest_evolution.pokemon_id != current_pokemon.pokemon_id:
            # Update user's Pokémon
            user.pokemon_id = highest_evolution.pokemon_id
            
            # Keep the user's custom Pokémon name if they have one
            if not user.pokemon_name:
                # If no custom name, set to new Pokémon's name
                user.pokemon_name = highest_evolution.name
            
            return True, current_pokemon.name, highest_evolution.name
        
        return False, None, None
    
    # Function to calculate evolution progress
    def calculate_evolution_progress(user, current_pokemon, evolution_line):
        """Calculate evolution progress based on user's current points."""
        progress_data = {}
        
        if not current_pokemon or not evolution_line:
            return progress_data
        
        # Find current Pokémon index in evolution line
        current_index = -1
        for i, evo in enumerate(evolution_line):
            if evo.pokemon_id == current_pokemon.pokemon_id:
                current_index = i
                break
        
        if current_index < len(evolution_line) - 1:
            # There's a next evolution
            next_evo = evolution_line[current_index + 1]
            current_points = user.total_points or 0
            current_min = current_pokemon.min_points_required
            next_min = next_evo.min_points_required
            
            # Calculate progress
            progress_points = current_points - current_min
            total_needed = next_min - current_min
            progress_percentage = (progress_points / total_needed * 100) if total_needed > 0 else 100
            
            progress_data = {
                'current_points': current_points,
                'next_required': next_min,
                'progress_points': progress_points,
                'total_needed': total_needed,
                'progress_percentage': min(max(progress_percentage, 0), 100),
                'next_evolution': next_evo.name,
                'exp_to_next': max(next_min - current_points, 0),
                'is_max_evolution': False
            }
        else:
            # This is the final evolution
            progress_data = {
                'is_max_evolution': True
            }
        
        return progress_data
    
    # Get current Pokémon for display (initial state)
    current_pokemon = None
    evolution_line = []
    progress_data = {}
    
    if user.pokemon_id:
        starter = Pokemon.query.get(user.pokemon_id)
        if starter:
            # Get all Pokémon in the same family
            evolution_line = (
                Pokemon.query
                .filter_by(family_id=starter.family_id)
                .order_by(Pokemon.min_points_required)
                .all()
            )
            
            # Find current Pokémon based on points (before adding new word)
            for evo in evolution_line:
                if user.total_points >= evo.min_points_required:
                    current_pokemon = evo
            
            # If no evolution qualifies yet, show the starter
            if not current_pokemon:
                current_pokemon = starter
            
            # Calculate initial progress
            progress_data = calculate_evolution_progress(user, current_pokemon, evolution_line)
    
    if form.validate_on_submit():
        word_text = form.word.data.strip().lower()
        vocab = Vocabulary.query.filter_by(word=word_text).first()
        
        if not vocab:
            vocab = Vocabulary(
                word=word_text,
                definition=form.definition.data.strip(),
                example_sentence=form.sentence.data.strip(),
                category=form.category.data.strip()
            )
            db.session.add(vocab)
            db.session.flush()
        
        existing_link = UserWords.query.filter_by(user_id=user.user_id, word_id=vocab.word_id).first()
        
        if not existing_link:
            # Track old points before adding new word
            old_points = user.total_points or 0
            
            user_word = UserWords(user_id=user.user_id, word_id=vocab.word_id)
            db.session.add(user_word)
            user.total_points = old_points + vocab.points_value
            
            # Check for evolution after adding points
            evolved, evolved_from, evolved_to = check_and_update_pokemon_evolution(user)
            
            db.session.commit()
            
            # Recalculate current Pokémon and progress after evolution check
            if user.pokemon_id:
                starter = Pokemon.query.get(user.pokemon_id)
                if starter:
                    # Get evolution line again (in case it changed)
                    evolution_line = (
                        Pokemon.query
                        .filter_by(family_id=starter.family_id)
                        .order_by(Pokemon.min_points_required)
                        .all()
                    )
                    
                    # Find current Pokémon based on NEW points
                    current_pokemon = None
                    for evo in evolution_line:
                        if user.total_points >= evo.min_points_required:
                            current_pokemon = evo
                    
                    if not current_pokemon:
                        current_pokemon = starter
                    
                    # Recalculate progress with updated points
                    progress_data = calculate_evolution_progress(user, current_pokemon, evolution_line)
            
            # Show appropriate flash message
            if evolved:
                flash(f"Word '{form.word.data}' added successfully! 🎉 Your {evolved_from} evolved into {evolved_to}!", "success")
            else:
                flash(f"Word '{form.word.data}' added successfully! +{vocab.points_value} EXP", "success")
        else:
            flash(f"Word '{form.word.data}' is already in your collection!", "info")
            db.session.commit()
    
    return render_template(
        "addword.html", 
        form=form, 
        current_pokemon=current_pokemon, 
        user=user,
        progress_data=progress_data,
        evolution_line=evolution_line
    )



@app.route('/flashcard')
@login_required
def flashcard():
    # Get words from database for flashcard game
    words = Vocabulary.query.order_by(func.random()).limit(20).all()
   
    words_data = []
    for word in words:
        words_data.append({
            "word": word.word,
            "definition": word.definition or f"Definition of {word.word}",
            "example": word.example_sentence or f"Example for {word.word}",
            "type": word.category or "noun"
        })
   
    return render_template('flashcard.html',
                         words=words_data,
                         words_count=len(words_data))
   

@app.route('/multichoi')
def multichoi():
    # Check if user is logged in
    if 'user_id' not in session:
        flash('Please login first', 'warning')
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    
    try:
        # Get words that the user has already learned
        user_learned_word_ids = [word.word_id for word in UserWords.query.filter_by(user_id=user_id).all()]
        
        # If user has learned words, get words they haven't learned yet
        # Otherwise, get all words
        if user_learned_word_ids:
            words = Vocabulary.query.filter(~Vocabulary.word_id.in_(user_learned_word_ids)).all()
        else:
            words = Vocabulary.query.all()
        
        # Shuffle and limit to 20 words for multiple choice
        import random
        random.shuffle(words)
        words = words[:20]
        
        # Convert to list of dictionaries
        words_data = []
        for word in words:
            words_data.append({
                "word": word.word,
                "definition": word.definition or f"Definition of {word.word}",
                "example_sentence": word.example_sentence or f"Example using {word.word}",
                "category": word.category or "noun"
            })
        
        return render_template('multichoi.html',
                             words=words_data,
                             words_count=len(words_data))
        
    except Exception as e:
        flash(f'Error loading words: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))


@app.route('/matchingtype')
def matchingtype():
    # Check if user is logged in
    if 'user_id' not in session:
        flash('Please login first', 'warning')
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    
    try:
        # Get words that the user has already learned
        user_learned_word_ids = [word.word_id for word in UserWords.query.filter_by(user_id=user_id).all()]
        
        # If user has learned words, get words they haven't learned yet
        # Otherwise, get all words
        if user_learned_word_ids:
            words = Vocabulary.query.filter(~Vocabulary.word_id.in_(user_learned_word_ids)).all()
        else:
            words = Vocabulary.query.all()
        
        # Shuffle and limit to 12 words for matching game
        import random
        random.shuffle(words)
        words = words[:12]
        
        word_pairs = []
        for word in words:
            word_pairs.append({
                "word": word.word,
                "definition": word.definition or f"Definition of {word.word}",
                "example_sentence": word.example_sentence or f"Example using {word.word}",
                "category": word.category or "noun"
            })
        
        return render_template('matchingtype.html',
                             word_pairs=word_pairs[:6],  # Limit to 6 pairs for matching
                             words_count=len(word_pairs))
        
    except Exception as e:
        flash(f'Error loading words: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    # Get statistics for the dashboard
    total_users = UserAcc.query.count()
    
    # Get total words stored (sum of words learned by all users)
    total_words = db.session.query(db.func.count(UserWords.user_word_id)).scalar() or 0
    
    # Get active users (users with last login in the last 7 days)
    week_ago = datetime.now(ph_timezone) - timedelta(days=7)
    active_users = UserAcc.query.filter(UserAcc.last_login >= week_ago).count()
    
    # Get today's new registrations
    today = datetime.now(ph_timezone).date()
    today_registrations = UserAcc.query.filter(
        db.func.date(UserAcc.date_created) == today
    ).count()
    
    # Get recent users (last 5 registrations)
    recent_users = UserAcc.query.order_by(UserAcc.date_created.desc()).limit(5).all()
    
    # Get recent activities (you can create an ActivityLog model later)
    recent_activities = [
        {"text": f"New user registered: {recent_users[0].name if recent_users else 'N/A'}", "time": "Recently"},
        {"text": "System maintenance completed", "time": "2 hours ago"},
        {"text": "Database backup successful", "time": "Yesterday"},
    ]
    
    return render_template(
        'admin_dashboard.html',
        total_users=total_users,
        total_words=total_words,
        active_users=active_users,
        today_registrations=today_registrations,
        recent_users=recent_users,
        recent_activities=recent_activities
    )


@app.route('/admin/users')
@admin_required
def admin_users():
    """User management page"""
    # Get all users
    all_users = UserAcc.query.order_by(UserAcc.date_created.desc()).all()
    
    # Get statistics
    total_users = UserAcc.query.count()
    active_users = UserAcc.query.filter(UserAcc.last_login >= datetime.now(ph_timezone) - timedelta(days=7)).count()
    
    return render_template(
        'user_management.html',  # Save the above HTML as user_management.html
        all_users=all_users,
        total_users=total_users,
        active_users=active_users
    )

@app.route('/admin/achievements')
@admin_required
def admin_achievements():
    """Achievements management page"""
    # Get all achievements with their Pokémon
    achievements = Achievement.query.all()
    
    # Get Pokémon for each achievement
    for achievement in achievements:
        achievement.pokemon = Pokemon.query.get(achievement.pokemon_id)
    
    # Get total achievements count
    total_achievements = Achievement.query.count()
    
    return render_template(
        'achievement_management.html',  # Save the above HTML as achievements_management.html
        achievements=achievements,
        total_achievements=total_achievements
    )
    
@app.route('/admin/analytics')
@admin_required
def admin_analytics():
    """Analytics dashboard page"""
    
    # Get current date range (default to current month)
    today = datetime.now(ph_timezone).date()
    first_day = today.replace(day=1)
    
    # Get statistics
    total_users = UserAcc.query.count()
    total_words = db.session.query(db.func.count(UserWords.user_word_id)).scalar() or 0
    
    # Active users (last 7 days)
    week_ago = datetime.now(ph_timezone) - timedelta(days=7)
    active_users = UserAcc.query.filter(UserAcc.last_login >= week_ago).count()
    
    # Calculate growth percentages (placeholder - in real app, compare with previous period)
    user_growth = 10  # Example growth percentage
    word_growth = 8   # Example growth percentage
    
    # Get top performing users (based on points and words learned)
    top_users = UserAcc.query.order_by(
        UserAcc.total_points.desc(), 
        db.func.coalesce(
            db.session.query(db.func.count(UserWords.user_word_id))
            .filter(UserWords.user_id == UserAcc.user_id)
            .scalar(), 0
        ).desc()
    ).limit(10).all()
    
    # Add words count to each user
    for user in top_users:
        user.words_count = db.session.query(db.func.count(UserWords.user_word_id))\
            .filter_by(user_id=user.user_id).scalar() or 0
        # Calculate accuracy (placeholder - in real app, track actual accuracy)
        user.accuracy = min(95 + user.user_id % 5, 99)  # Random accuracy for demo
    
    # Get recent activities (placeholder - in real app, create ActivityLog model)
    recent_activities = [
        {"date": today.strftime('%Y-%m-%d'), "type": "User Registration", "user": "New User", "details": "Created account"},
        {"date": (today - timedelta(days=1)).strftime('%Y-%m-%d'), "type": "Words Learned", "user": "TrainerAsh", "details": "50 new words"},
        {"date": (today - timedelta(days=2)).strftime('%Y-%m-%d'), "type": "Achievement Unlocked", "user": "BrockRock", "details": "Word Master"},
        {"date": (today - timedelta(days=3)).strftime('%Y-%m-%d'), "type": "Login Streak", "user": "ProfessorOak", "details": "90 days streak"},
        {"date": (today - timedelta(days=4)).strftime('%Y-%m-%d'), "type": "Pokémon Evolved", "user": "MistyWater", "details": "Squirtle evolved"},
    ]
    
    return render_template(
        'analytics_dashboard.html',  # Save the above HTML as analytics_dashboard.html
        total_users=total_users,
        total_words=total_words,
        active_users=active_users,
        user_growth=user_growth,
        word_growth=word_growth,
        top_users=top_users,
        recent_activities=recent_activities
    )
    
@app.route('/admin/pokemon-config')
def pokemon_config():
    """Render the Pokémon configuration page"""
    return render_template('pokemon_config.html')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)

