from flask import Flask, render_template, session, redirect, url_for, flash, request, jsonify, make_response
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash
from forms import LoginForm, PaginationForm, PokemonAddForm, PokemonDeleteForm, PokemonEditForm, PokemonSearchForm, SignupForm, AddWordForm, ForgotPasswordForm, UserActionForm, UserSearchForm, ViewUserForm
from models import db,UserAcc, UserAchievement, UserWords, Pokemon, Achievement, Vocabulary, Notification, UserPokemon
from functools import wraps
import os
from sqlalchemy import or_, and_  
from datetime import datetime, date, timedelta
import pytz
from sqlalchemy.sql import func
import random, requests
import smtplib, hashlib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
import traceback


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



@app.route('/api/get_user_points')
@login_required
def get_user_points():
    """Get current user's total points"""
    user = get_current_user()
    return jsonify({
        'success': True,
        'total_points': user.total_points or 0
    })

def check_and_update_achievements(user):
    """Check all achievements and award them if user qualifies."""
    all_achievements = Achievement.query.all()
    
    for achievement in all_achievements:
        # Get or create UserAchievement record
        user_achievement = UserAchievement.query.filter_by(
            user_id=user.user_id,
            achievement_id=achievement.achievement_id
        ).first()
        
        if not user_achievement:
            # Create new UserAchievement record
            user_achievement = UserAchievement(
                user_id=user.user_id,
                achievement_id=achievement.achievement_id,
                current_progress=0,
                date_earned=None  # Explicitly set to None
            )
            db.session.add(user_achievement)
        
        # Only update if not already earned
        if not user_achievement.date_earned:
            # Calculate current progress based on achievement
            current_progress = 0
            
            # WORD COLLECTOR ACHIEVEMENT - Learn 10 different words
            if "Word Collector" in achievement.name:
                current_progress = UserWords.query.filter_by(user_id=user.user_id).count()
                
            # ZZZ ACHIEVEMENT - Logout for the first time
            elif "Zzz" in achievement.name:
                current_progress = 1 if user.last_logout else 0
                
            # SOLO LEVELING ACHIEVEMENT - Reach 500 points
            elif "Solo Leveling" in achievement.name:
                current_progress = user.total_points or 0
                
            # JOURNEY BEGINS ACHIEVEMENT - Welcome to VocabuLearner!
            elif "Journey Begins" in achievement.name:
                current_progress = 1  # Always earned when account is created
            
            # Update progress
            user_achievement.current_progress = current_progress

        db.session.commit()

def update_user_streak(user):
    
    # Skip streak updates for admin users
    if hasattr(user, 'is_admin') and user.is_admin:
        return
    
    today = datetime.now(ph_timezone).date()
    
    # ALWAYS set streak to 1 if it's 0 (from default)
    if user.current_streak == 0:
        user.current_streak = 1
        user.longest_streak = 1
        user.last_login = datetime.now(ph_timezone)
        return
    
    # If first login ever
    if not user.last_login:
        user.current_streak = 1
        user.longest_streak = 1
        user.last_login = datetime.now(ph_timezone)
        return
    
    # Convert last_login to Philippine timezone
    if user.last_login.tzinfo is None:
        last_login_ph = pytz.utc.localize(user.last_login).astimezone(ph_timezone)
    else:
        last_login_ph = user.last_login.astimezone(ph_timezone)
    
    last_login_date = last_login_ph.date()
    days_difference = (today - last_login_date).days
    
    if days_difference == 1:
        # Consecutive day
        user.current_streak += 1
        if user.current_streak > user.longest_streak:
            user.longest_streak = user.current_streak
        user.last_login = datetime.now(ph_timezone)
    elif days_difference > 1:
        # Streak broken
        user.current_streak = 1
        user.last_login = datetime.now(ph_timezone)
    # If days_difference == 0: Already logged in today - do nothing

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
    """Update the name of the user's current partner Pokémon"""
    try:
        user_id = session['user_id']
        data = request.get_json()
        
        if not data or 'pokemon_name' not in data:
            return jsonify({'success': False, 'error': 'Pokémon name required'}), 400
        
        new_name = data['pokemon_name'].strip()
        
        if not new_name:
            return jsonify({'success': False, 'error': 'Pokémon name cannot be empty'}), 400
        
        if len(new_name) > 20:
            return jsonify({'success': False, 'error': 'Pokémon name cannot be more than 20 characters'}), 400
        
        # Get the user
        user = UserAcc.query.get(user_id)
        if not user or not user.pokemon_id:
            return jsonify({'success': False, 'error': 'No active partner Pokémon'}), 400
        
        # Update the name in UserAcc
        user.pokemon_name = new_name
        
        # Also update the custom name in UserPokemon
        user_pokemon_entry = UserPokemon.query.filter_by(
            user_id=user_id, 
            pokemon_id=user.pokemon_id
        ).first()
        
        if user_pokemon_entry:
            user_pokemon_entry.custom_name = new_name
        
        # Create notification
        notification = Notification(
            user_id=user_id,
            title='Pokémon Renamed!',
            message=f'Your partner is now called {new_name}! ✨',
            notification_type='pokemon'
        )
        db.session.add(notification)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Partner renamed to {new_name}! ✨',
            'pokemon_name': new_name
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error updating Pokémon name: {str(e)}")
        return jsonify({'success': False, 'error': 'Database error'}), 500


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
        
        if user:
            if not user.is_active:
                flash("Your account has been deactivated.", "danger")
                return render_template('login.html', form=form)
            
            if check_password_hash(user.password, form.password.data):
                # Update streak FIRST
                update_user_streak(user)
                
                # UPDATE LAST LOGIN in Philippine Time
                pht = pytz.timezone('Asia/Manila')
                user.last_login = datetime.now(pht)
                
                # Store user info
                session['user_id'] = user.user_id
                session['username'] = user.name
                session['is_admin'] = user.is_admin
                
                # Commit ALL changes
                db.session.commit()
                
                # CHECK ACHIEVEMENTS AFTER LOGIN (Journey Begins if not already)
                check_and_update_achievements(user)
                
                # Log success
                print(f"LOGIN: User {user.user_id} ({user.name}) logged in")
                print(f"LAST_LOGIN (PHT): Updated to {user.last_login}")
                print(f"STREAK: Current streak: {user.current_streak}")
                
                if user.is_admin:
                    return redirect(url_for('admin_dashboard'))
                else:
                    return redirect(url_for('dashboard'))
            else:
                flash("The password you entered is incorrect.", "danger")
        else:
            flash("No account found with this email address.", "danger")
            
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
            # CREATE USERACHIEVEMENT ENTRIES FOR NEW USER
            all_achievements = Achievement.query.all()
            for achievement in all_achievements:
                user_achievement = UserAchievement(
                    user_id=new_user.user_id,  # This will work because user_id is auto-increment
                    achievement_id=achievement.achievement_id,
                    current_progress=0,
                    date_earned=None
                )
                db.session.add(user_achievement)
            
            db.session.commit()
            
            # CHECK ACHIEVEMENTS AFTER ACCOUNT CREATION (Journey Begins)
            check_and_update_achievements(new_user)
            
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
    user_id = session.get('user_id')
    username = session.get('username')
    
    if user_id:
        try:
            user = UserAcc.query.get(user_id)
            
            if user:
                # Get current timestamp in Philippine Time
                pht = pytz.timezone('Asia/Manila')
                current_time = datetime.now(pht)
                
                # Update last_logout timestamp in PHT
                user.last_logout = current_time
                
                # Also update other fields if needed
                # For example, if you want to calculate session duration:
                if user.last_login:
                    # Convert both times to UTC for accurate duration calculation
                    utc = pytz.UTC
                    login_utc = user.last_login.astimezone(utc)
                    logout_utc = current_time.astimezone(utc)
                
                # Commit to database
                db.session.commit()
                
                # CHECK ACHIEVEMENTS AFTER LOGOUT (for Zzz achievement)
                check_and_update_achievements(user)
                
            else:
                print(f"WARNING: User with user_id {user_id} not found in database")
            
        except Exception as e:
            # Log error but still allow logout
            print(f"ERROR updating last_logout: {str(e)}")
            traceback.print_exc()
            db.session.rollback()
    else:
        print(f"DEBUG: No user_id found in session")
    
    # Clear all session data
    session.clear()

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


def get_word_of_the_day(user_id=None):
    today = date.today()

    # Get all words marked as Word of the Day
    word_of_day_candidates = Vocabulary.query.filter_by(is_word_of_day=True).all()
    
    # If no Word of Day candidates at all
    if not word_of_day_candidates:
        # If no words marked as Word of Day, get any random word
        all_words = Vocabulary.query.all()
        
        # If no words exist in the database, return a default response
        if not all_words:
            return {
                "word_id": 0,
                "word": "No words available",
                "pronunciation": "",
                "type": "",
                "definition": "Please add vocabulary words to your collection.",
                "example": "",
                "points_value": 0
            }
        
        word_of_day_candidates = all_words
    
    # If user_id is provided, exclude words they already have
    if user_id:
        # Get word IDs that the user already has
        user_word_ids = db.session.query(UserWords.word_id).filter_by(user_id=user_id).all()
        user_word_ids = [word_id for (word_id,) in user_word_ids]
        
        # Filter out words the user already has
        if user_word_ids:
            word_of_day_candidates = [
                word for word in word_of_day_candidates 
                if word.word_id not in user_word_ids
            ]
    
    # If no Word of Day candidates remain after filtering
    if not word_of_day_candidates:
        return {
            "word_id": 0,
            "word": "All Words Learned",
            "pronunciation": "",
            "type": "",
            "definition": "You've already learned all available words!",
            "example": "Check back tomorrow or add more words.",
            "points_value": 0
        }
    
    # Create a hash based on today's date for consistent selection
    today_str = today.strftime('%Y-%m-%d')
    date_hash = hashlib.md5(today_str.encode()).hexdigest()
    hash_int = int(date_hash, 16)
    
    # Select word based on hash (consistent for the day)
    word_index = hash_int % len(word_of_day_candidates)
    chosen = word_of_day_candidates[word_index]

    # Now chosen should definitely exist
    if not chosen:
        return {
            "word_id": 0,
            "word": "Error loading word",
            "pronunciation": "",
            "type": "",
            "definition": "Unable to load vocabulary word.",
            "example": "",
            "points_value": 0
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
                "example": chosen.example_sentence or "",
                "points_value": chosen.points_value
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
            "example": example or chosen.example_sentence or "",
            "points_value": chosen.points_value
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
            "example": chosen.example_sentence or "",
            "points_value": chosen.points_value
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
    
    # Get Pokémon from database - CHANGED: Get common Pokémon for starters
    pokemons = Pokemon.query.filter_by(rarity='starter').all()
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
    
    # In your dashboard function, update the word_data dictionary:
    if word_of_day:
        word_data = {
            'word_id': word_of_day.word_id,
            'word': word_of_day.word,
            'definition': word_of_day.definition,
            'example': word_of_day.example_sentence,
            'type': word_of_day.category if word_of_day.category else 'General',
            'user_has_word': user_has_word,
            'points_value': word_of_day.points_value  # Add this line
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
            'user_has_word': True,
            'points_value': 10  # Default value
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
        # Get Philippine Time
        ph_tz = pytz.timezone('Asia/Manila')
        ph_time = datetime.now(ph_tz)
        
        # Add word to user's collection with Philippine time
        user_word = UserWords(user_id=user.user_id, word_id=word_id, date_learned=ph_time)
        db.session.add(user_word)
        user.total_points = (user.total_points or 0) + word.points_value
        
        # Check if this is a Word of the Day
        if word.is_word_of_day:
            flash(f"✨ '{word.word}' has been added to your collection! Today's Word of the Day claimed! +{word.points_value} EXP", 'success')
        else:
            flash(f"Word '{word.word}' added to your collection! +{word.points_value} EXP", 'success')
        
        db.session.commit()
        
        # CHECK ACHIEVEMENTS AFTER LEARNING A WORD
        check_and_update_achievements(user)
        
    else:
        flash(f"Word '{word.word}' is already in your collection!", 'info')
    
    return redirect(url_for('dashboard'))

def get_daily_word_of_day():
    """Get a consistent Word of the Day for the current day in Philippine Time."""
    # Get Philippine Time
    ph_tz = pytz.timezone('Asia/Manila')
    ph_time = datetime.now(ph_tz)
    today_ph = ph_time.date()
    
    today_str = today_ph.strftime('%Y-%m-%d')

    
    # Create a hash based on today's Philippine date
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
        
        # CHECK ACHIEVEMENTS AFTER EARNING POINTS (for Solo Leveling)
        check_and_update_achievements(user)
        
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
   
    # Validate
    if not pokemon_id:
        flash("Please select a Pokémon partner.", "danger")
        return redirect(url_for('dashboard'))
   
    try:
        chosen_id = int(pokemon_id)
    except ValueError:
        flash("Invalid Pokémon selection.", "danger")
        return redirect(url_for('dashboard'))
   
    # Get Pokémon details
    pokemon = Pokemon.query.get(chosen_id)
    if not pokemon:
        flash("Invalid Pokémon selection.", "danger")
        return redirect(url_for('dashboard'))
   
    # 1. Add to UserPokemon collection
    user_pokemon = UserPokemon(
        user_id=user.user_id,
        pokemon_id=chosen_id,
        date_obtained=datetime.utcnow(),
        custom_name=None  # No custom name initially
    )
    db.session.add(user_pokemon)
    
    # 2. Set as active partner in UserAcc
    user.pokemon_id = chosen_id
    user.pokemon_name = pokemon.name  # Default name
    
    # Create notification
    notification = Notification(
        user_id=user.user_id,
        title='New Partner!',
        message=f'{pokemon.name} is now your learning partner! ⚡',
        notification_type='pokemon'
    )
    db.session.add(notification)
    
    db.session.commit()
   
    flash(f"{pokemon.name} is now your starter Pokémon! ⚡", "success")
    return redirect(url_for('dashboard'))


def check_and_update_achievements(user):
    """Check all achievements and update progress ONLY - do not auto-claim."""
    all_achievements = Achievement.query.all()
    
    for achievement in all_achievements:
        # Get or create UserAchievement record
        user_achievement = UserAchievement.query.filter_by(
            user_id=user.user_id,
            achievement_id=achievement.achievement_id
        ).first()
        
        if not user_achievement:
            # Create new UserAchievement record
            user_achievement = UserAchievement(
                user_id=user.user_id,
                achievement_id=achievement.achievement_id,
                current_progress=0,
                date_earned=None
            )
            db.session.add(user_achievement)
        
        # Calculate current progress based on achievement
        current_progress = 0
        
        # WORD COLLECTOR ACHIEVEMENT - Learn 10 different words
        if "Word Collector" in achievement.name:
            current_progress = UserWords.query.filter_by(user_id=user.user_id).count()
            
        # ZZZ ACHIEVEMENT - Logout for the first time
        elif "Zzz" in achievement.name:
            current_progress = 1 if user.last_logout else 0
            
        # SOLO LEVELING ACHIEVEMENT - Reach 500 points
        elif "Solo Leveling" in achievement.name:
            current_progress = user.total_points or 0
            
        # JOURNEY BEGINS ACHIEVEMENT - Welcome to VocabuLearner!
        elif "Journey Begins" in achievement.name:
            current_progress = 1  # Always earned when account is created
        
        # Other achievement types
        elif "Vocabulary Novice" in achievement.name:
            current_progress = UserWords.query.filter_by(user_id=user.user_id).count()
        elif "Flashcard Champion" in achievement.name:
            # You'll need to track flashcard sessions separately
            current_progress = 0  # TODO: Add flashcard session tracking

        user_achievement.current_progress = current_progress

    db.session.commit()

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
        # FIXED: Check if evolved form already in collection
        existing_evolved = UserPokemon.query.filter_by(
            user_id=user.user_id,
            pokemon_id=highest_evolution.pokemon_id
        ).first()
        
        # Only add to collection if not already there
        if not existing_evolved:
            evolved_pokemon_entry = UserPokemon(
                user_id=user.user_id,
                pokemon_id=highest_evolution.pokemon_id,
                date_obtained=datetime.now(ph_timezone),
                custom_name=None
            )
            db.session.add(evolved_pokemon_entry)
            print(f"✅ Added evolved {highest_evolution.name} to user {user.user_id}'s collection")
        
        # Update user's current partner
        user.pokemon_id = highest_evolution.pokemon_id
        
        # Keep the user's custom Pokémon name if they have one
        if not user.pokemon_name:
            user.pokemon_name = highest_evolution.name
        
        db.session.commit()
        return True, current_pokemon.name, highest_evolution.name
    
    return False, None, None

@app.route('/api/claim_achievement/<int:achievement_id>', methods=['POST'])
@login_required
def claim_achievement(achievement_id):
    """Claim an achievement that has been unlocked"""
    try:
        user = get_current_user()
        
        # Get the UserAchievement record
        user_achievement = UserAchievement.query.filter_by(
            user_id=user.user_id,
            achievement_id=achievement_id
        ).first()
        
        if not user_achievement:
            return jsonify({'success': False, 'error': 'Achievement not found for user'}), 404
        
        # Get the achievement details
        achievement = Achievement.query.get(achievement_id)
        if not achievement:
            return jsonify({'success': False, 'error': 'Achievement not found'}), 404
        
        # Check if achievement is already claimed
        if user_achievement.date_earned:
            return jsonify({'success': False, 'error': 'Achievement already claimed'}), 400
        
        # Check if user meets the requirements
        if user_achievement.current_progress >= achievement.requirement:
            # 1. Award the achievement
            user_achievement.date_earned = datetime.now(ph_timezone)
            
            # 2. Add points reward to user
            user.total_points = (user.total_points or 0) + achievement.points_reward
            
            # 3. Check if achievement gives a Pokémon reward
            pokemon_reward_data = None
            if achievement.pokemon_id:
                reward_pokemon = Pokemon.query.get(achievement.pokemon_id)
                if reward_pokemon:
                    # Check if user already has this Pokémon
                    existing = UserPokemon.query.filter_by(
                        user_id=user.user_id,
                        pokemon_id=achievement.pokemon_id
                    ).first()
                    
                    if existing:
                        # User already has this Pokémon
                        pokemon_reward_data = {
                            'awarded': False,
                            'name': reward_pokemon.name,
                            'message': f'Already have {reward_pokemon.name}!'
                        }
                    else:
                        # Add Pokémon to user's collection
                        user_pokemon = UserPokemon(
                            user_id=user.user_id,
                            pokemon_id=achievement.pokemon_id,
                            date_obtained=datetime.now(ph_timezone)
                        )
                        db.session.add(user_pokemon)
                        pokemon_reward_data = {
                            'awarded': True,
                            'pokemon_id': reward_pokemon.pokemon_id,
                            'name': reward_pokemon.name,
                            'image_url': reward_pokemon.url,
                            'message': f'🎁 {reward_pokemon.name} added to collection!'
                        }
            
            # 4. Create notification
            notification_message = f"You claimed: {achievement.name}! +{achievement.points_reward} EXP"
            if pokemon_reward_data:
                notification_message += f" {pokemon_reward_data['message']}"
            
            notification = Notification(
                user_id=user.user_id,
                title="🏆 Achievement Claimed!",
                message=notification_message,
                notification_type='achievement',
                is_read=False,
                created_at=datetime.now(ph_timezone)
            )
            db.session.add(notification)
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Achievement claimed! +{achievement.points_reward} EXP',
                'points_awarded': achievement.points_reward,
                'new_total_points': user.total_points,
                'pokemon_reward': pokemon_reward_data
            })
        else:
            return jsonify({
                'success': False,
                'error': f'Requirements not met. Progress: {user_achievement.current_progress}/{achievement.requirement}'
            }), 400
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    user = UserAcc.query.get(user_id)
    
    if not user:
        return redirect(url_for('logout'))
    
    # Get words learned count
    words_learned = UserWords.query.filter_by(user_id=user_id).count()
    
    # Get Pokémon data
    pokemon = None
    pokemon_display_name = "No Pokémon Yet"
    
    if user.pokemon_id:
        pokemon = Pokemon.query.get(user.pokemon_id)
        pokemon_display_name = user.pokemon_name if user.pokemon_name else (pokemon.name if pokemon else "No Pokémon")
    
    # Get achievements data
    achievements = Achievement.query.all()
    achievements_data = []
    
    for achievement in achievements:
        user_achievement = UserAchievement.query.filter_by(
            user_id=user_id, 
            achievement_id=achievement.achievement_id
        ).first()
        
        is_earned = user_achievement and user_achievement.date_earned is not None
        user_progress = user_achievement.current_progress if user_achievement else 0
        
        # CORRECTED: Calculate can_claim based on progress vs requirement
        can_claim = not is_earned and user_progress >= achievement.requirement
        
        achievements_data.append({
            'achievement_id': achievement.achievement_id,
            'name': achievement.name,
            'description': achievement.description,
            'points_reward': achievement.points_reward,
            'requirement': achievement.requirement,
            'is_earned': is_earned,
            'can_claim': can_claim,  # This was the bug!
            'user_progress': user_progress
        })
    
    # Get Pokémon images for achievements
    achievement_pokemon = {}
    for achievement in achievements:
        pokemon_for_achievement = Pokemon.query.get(achievement.pokemon_id)
        achievement_pokemon[achievement.achievement_id] = {
            'url': pokemon_for_achievement.url if pokemon_for_achievement else None,
            'name': pokemon_for_achievement.name if pokemon_for_achievement else None
        }
    
    # Get Pokémon collection count
    collected_pokemon_count = UserPokemon.query.filter_by(user_id=user_id).count()
    
    # Get unique Pokémon species count
    unique_pokemon_species = db.session.query(UserPokemon.pokemon_id).filter_by(user_id=user_id).distinct().count()
    
    # Get current partner name
    current_partner_name = pokemon_display_name
    
    return render_template('profile.html',
                         user=user,
                         words_learned=words_learned,
                         pokemon=pokemon,
                         pokemon_display_name=pokemon_display_name,
                         achievements_data=achievements_data,
                         achievement_pokemon=achievement_pokemon,
                         collected_pokemon_count=collected_pokemon_count,
                         unique_pokemon_count=unique_pokemon_species,
                         current_partner_name=current_partner_name)


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
    
    # Get Philippine Timezone
    ph_tz = pytz.timezone('Asia/Manila')
    
    # Join UserWords with Vocabulary to get word details
    user_words = (
        db.session.query(UserWords, Vocabulary)
        .join(Vocabulary, UserWords.word_id == Vocabulary.word_id)
        .filter(UserWords.user_id == user.user_id)
        .order_by(UserWords.date_learned.desc())  # Sort by most recent
        .all()
    )
    
    # Convert dates to Philippine Time
    words_with_ph_time = []
    for user_word, vocab in user_words:
        # Convert date_learned to Philippine Time
        if user_word.date_learned:
            # If date_learned is naive (no timezone), assume UTC
            if user_word.date_learned.tzinfo is None:
                date_utc = pytz.utc.localize(user_word.date_learned)
            else:
                date_utc = user_word.date_learned
                
            # Convert to Philippine Time
            date_ph = date_utc.astimezone(ph_tz)
            date_str = date_ph.strftime('%Y-%m-%d')
        else:
            date_str = "Unknown"
        
        words_with_ph_time.append((user_word, vocab, date_str))
    
    return render_template("wordbank.html", words=words_with_ph_time)




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
def view_profile(user_id):
    viewed_user = UserAcc.query.get_or_404(user_id)
    
    current_user_id = session.get('user_id')
    is_own_profile = current_user_id == user_id
    
    viewed_collected_count = UserPokemon.query.filter_by(user_id=user_id).count()
    
    viewed_unique_count = db.session.query(UserPokemon.pokemon_id)\
        .filter_by(user_id=user_id)\
        .distinct().count()
    
    viewed_partner = None
    if viewed_user.pokemon_id:
        viewed_partner = Pokemon.query.get(viewed_user.pokemon_id)
    
    viewed_words_learned = UserWords.query.filter_by(user_id=user_id).count()
    
    viewed_achievements = UserAchievement.query\
        .filter_by(user_id=user_id)\
        .join(Achievement, UserAchievement.achievement_id == Achievement.achievement_id)\
        .all()
    
    viewed_achievements_dict = {ua.achievement_id: ua for ua in viewed_achievements}
    
    all_achievements = Achievement.query.all()
    
    achievement_pokemon = {}
    for achievement in all_achievements:
        if achievement.pokemon_id:
            pokemon = Pokemon.query.get(achievement.pokemon_id)
            if pokemon:
                achievement_pokemon[achievement.achievement_id] = {
                    'name': pokemon.name,
                    'url': pokemon.url
                }
    
    return render_template('view_profile.html',
        user=viewed_user,
        is_own_profile=is_own_profile,
        collected_pokemon_count=viewed_collected_count,
        unique_pokemon_count=viewed_unique_count,
        words_learned=viewed_words_learned,
        pokemon=viewed_partner,
        pokemon_display_name=viewed_user.pokemon_name if viewed_user.pokemon_name else (viewed_partner.name if viewed_partner else "No Pokémon"),
        user_achievements_dict=viewed_achievements_dict,
        all_achievements=all_achievements,
        achievement_pokemon=achievement_pokemon
    )


@app.route("/add_word", methods=["GET", "POST"])
@login_required
def add_word():
    form = AddWordForm()
    user = get_current_user()
    
    if form.validate_on_submit():
        # Get the word data from the form
        word_text = form.word.data.strip().lower()
        definition = form.definition.data.strip()
        sentence = form.sentence.data.strip()
        
        # First, check if word already exists in Vocabulary table
        existing_vocab = Vocabulary.query.filter_by(word=word_text).first()
        
        # Get Philippine Time
        ph_tz = pytz.timezone('Asia/Manila')
        ph_time = datetime.now(ph_tz)
        
        if existing_vocab:
            # Check if user already has this word
            existing_user_word = UserWords.query.filter_by(
                user_id=user.user_id, 
                word_id=existing_vocab.word_id
            ).first()
            
            if existing_user_word:
                flash(f'"{word_text}" is already in your vocabulary!', 'danger')
                return redirect(url_for('add_word'))
            
            # User doesn't have this word yet, so create UserWords entry
            new_user_word = UserWords(
                user_id=user.user_id,
                word_id=existing_vocab.word_id,
                date_learned=ph_time  # Use Philippine time
            )
            db.session.add(new_user_word)
            
        else:
            # Word doesn't exist in Vocabulary table, so create both
            new_vocab = Vocabulary(
                word=word_text,
                definition=definition,
                example_sentence=sentence,
                # category field exists but we're not using it
                category=None,
                points_value=10,
                is_word_of_day=False
            )
            db.session.add(new_vocab)
            db.session.flush()  # Get the ID of the new vocab word
            
            # Create UserWords entry
            new_user_word = UserWords(
                user_id=user.user_id,
                word_id=new_vocab.word_id,
                date_learned=ph_time  # Use Philippine time
            )
            db.session.add(new_user_word)
        
        # Update user's total points (10 points per word)
        user.total_points += 10
        db.session.commit()
        
        # CHECK ACHIEVEMENTS AFTER ADDING A WORD
        check_and_update_achievements(user)
        
        # Check for Pokémon evolution
        evolved, old_pokemon, new_pokemon = check_and_update_pokemon_evolution(user)
        
        if evolved:
            flash(f'Word added successfully! {old_pokemon} evolved into {new_pokemon}! 🎉', 'success')
        else:
            flash(f'Word added successfully! +10 EXP', 'success')
        
        return redirect(url_for('add_word'))
    
    # Get current Pokémon for display
    current_pokemon = None
    if user.pokemon_id:
        current_pokemon = Pokemon.query.get(user.pokemon_id)
    
    # Calculate progress data
    progress_data = None
    if current_pokemon:
        # Get next evolution
        next_evolution = (
            Pokemon.query
            .filter_by(family_id=current_pokemon.family_id)
            .filter(Pokemon.min_points_required > current_pokemon.min_points_required)
            .order_by(Pokemon.min_points_required)
            .first()
        )
        
        if next_evolution:
            total_needed = next_evolution.min_points_required - current_pokemon.min_points_required
            current_progress = user.total_points - current_pokemon.min_points_required
            exp_to_next = max(0, next_evolution.min_points_required - user.total_points)
            
            progress_data = {
                'progress_points': current_progress,
                'total_needed': total_needed,
                'progress_percentage': (current_progress / total_needed) * 100 if total_needed > 0 else 0,
                'exp_to_next': exp_to_next,
                'next_evolution': next_evolution.name,
                'is_max_evolution': False
            }
        else:
            progress_data = {
                'is_max_evolution': True
            }
    
    return render_template(
        'addword.html',
        form=form,
        user=user,
        current_pokemon=current_pokemon,
        progress_data=progress_data
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

    ph_tz = pytz.timezone('Asia/Manila')
    ph_now = datetime.now(ph_tz)
    
    # Get statistics for the dashboard
    total_users = UserAcc.query.filter_by(is_admin=False).count()
    
    # Get total words stored (sum of words learned by all users)
    total_words_stored = db.session.query(db.func.count(UserWords.user_word_id)).scalar() or 0
    
    # Get today's new registrations - EXCLUDE ADMIN
    today = ph_now.date()
    today_start = ph_tz.localize(datetime.combine(today, datetime.min.time()))
    today_end = ph_tz.localize(datetime.combine(today, datetime.max.time()))
    
    today_registrations = UserAcc.query.filter(
        UserAcc.date_created >= today_start,
        UserAcc.date_created <= today_end,
        UserAcc.is_admin == False  # Exclude admin
    ).count()
    
    # Get active sessions (users where last_login is later than last_logout) - EXCLUDE ADMIN
    active_sessions = 0
    all_non_admin_users = UserAcc.query.filter_by(is_admin=False).all()
    
    for user in all_non_admin_users:
        if user.last_login:
            # Convert last_login and last_logout to Philippine timezone for comparison
            last_login_ph = user.last_login.replace(tzinfo=pytz.UTC).astimezone(ph_tz)
            
            if user.last_logout:
                last_logout_ph = user.last_logout.replace(tzinfo=pytz.UTC).astimezone(ph_tz)
                if last_login_ph > last_logout_ph:
                    active_sessions += 1
            else:
                # If user has never logged out (last_logout is None), they are active
                active_sessions += 1
    
    # Get recent users (last 5 registrations)
    recent_users = UserAcc.query.filter_by(is_admin=False).order_by(
        UserAcc.date_created.desc()
    ).limit(5).all()
    
    # Get recent activities from various sources
    recent_activities = []
    
    # 1. Recent user registrations
    for user in recent_users:
        if user.date_created:
            # Convert user.date_created to Philippine timezone for comparison
            user_date_ph = user.date_created.replace(tzinfo=pytz.UTC).astimezone(ph_tz)
            time_diff = ph_now - user_date_ph
            if time_diff.total_seconds() < 60:
                time_ago = "Just now"
            elif time_diff.total_seconds() < 3600:
                minutes = int(time_diff.total_seconds() // 60)
                time_ago = f"{minutes} minutes ago"
            elif time_diff.total_seconds() < 86400:
                hours = int(time_diff.total_seconds() // 3600)
                time_ago = f"{hours} hours ago"
            elif time_diff.days == 1:
                time_ago = "1 day ago"
            else:
                time_ago = f"{time_diff.days} days ago"
        else:
            time_ago = "Recently"
        
        recent_activities.append({
            "text": f"New user registered: {user.name}",
            "time": time_ago
        })
    
    # 2. Recent word additions - use UserWords with date_learned
    recent_words_learned = UserWords.query.order_by(
        UserWords.date_learned.desc()
    ).limit(5).all()
    
    for user_word in recent_words_learned:
        user = UserAcc.query.get(user_word.user_id)
        word = Vocabulary.query.get(user_word.word_id)
        if user and word:
            recent_activities.append({
                "text": f"User {user.name} learned word '{word.word}'",
                "time": "Recently"
            })
    
    # 3. Recent achievements unlocked
    recent_achievements = UserAchievement.query.order_by(
        UserAchievement.date_earned.desc()
    ).limit(5).all()
    
    for user_achievement in recent_achievements:
        user = UserAcc.query.get(user_achievement.user_id)
        ach = Achievement.query.get(user_achievement.achievement_id)
        if user and ach:
            recent_activities.append({
                "text": f"User {user.name} unlocked achievement '{ach.name}'",
                "time": "Recently"
            })
    
    # 4. Recent notifications (excluding auto/system ones)
    recent_notifications = Notification.query.filter(
        Notification.notification_type != 'auto'
    ).order_by(
        Notification.created_at.desc()
    ).limit(3).all()
    
    for notification in recent_notifications:
        user = UserAcc.query.get(notification.user_id)
        if user:
            recent_activities.append({
                "text": f"Notification sent to {user.name}: {notification.title}",
                "time": "Recently"
            })
    
    # 5. Pokémon evolutions based on total_points
    evolved_users = UserAcc.query.filter(
        UserAcc.pokemon_id.isnot(None),
        UserAcc.total_points > 0
    ).order_by(
        UserAcc.date_created.desc()
    ).limit(3).all()
    
    for user in evolved_users:
        pokemon = Pokemon.query.get(user.pokemon_id)
        if pokemon:
            evolutions = user.total_points // 50  # evolve every 50 EXP
            if evolutions > 0:
                recent_activities.append({
                    "text": f"User {user.name}'s {pokemon.name} reached level {evolutions}",
                    "time": "Recently"
                })
    
    # Limit to 5 most recent activities
    recent_activities = recent_activities[:5]
    
    # Format the numbers for display
    return render_template(
        'admin_dashboard.html',
        total_users=total_users,
        total_words=total_words_stored,
        active_sessions=active_sessions,
        today_registrations=today_registrations,
        recent_users=recent_users,
        recent_activities=recent_activities
    )

@app.route('/admin/users', methods=['GET', 'POST'])
@admin_required
def admin_users():
    """Main user management page - FILTERS NON-ADMIN USERS ONLY"""
    # Get query parameters from URL
    search_term = request.args.get('search', '')
    status_filter = request.args.get('status', 'all')
    date_from_str = request.args.get('date_from', '')
    date_to_str = request.args.get('date_to', '')
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    # Handle POST request (form submission)
    if request.method == 'POST':
        # Create form with POST data
        search_form = UserSearchForm(request.form)
        
        if search_form.validate():
            # Get data from validated form
            search_term = search_form.search.data or ''
            status_filter = search_form.status.data or 'all'
            
            # Handle dates
            date_from = search_form.date_from.data
            date_to = search_form.date_to.data
            
            date_from_str = date_from.strftime('%Y-%m-%d') if date_from else ''
            date_to_str = date_to.strftime('%Y-%m-%d') if date_to else ''
            
            page = 1  # Reset to first page when searching/filtering
            
            # Build redirect parameters
            params = {
                'search': search_term,
                'status': status_filter,
                'page': page
            }
            
            # Only add date params if they exist
            if date_from_str:
                params['date_from'] = date_from_str
            if date_to_str:
                params['date_to'] = date_to_str
                
            # Redirect to GET with parameters (PRG pattern)
            return redirect(url_for('admin_users', **params))
        else:
            # Form validation failed - reset filter parameters
            search_term = ''
            status_filter = 'all'
            date_from_str = ''
            date_to_str = ''
            page = 1
            
            # Keep the form with errors to display them
            # Continue to render template below
    else:
        # GET request - create form with query parameters
        form_data = {
            'search': search_term,
            'status': status_filter
        }
        
        # Parse dates for form
        if date_from_str:
            try:
                form_data['date_from'] = datetime.strptime(date_from_str, '%Y-%m-%d').date()
            except (ValueError, AttributeError):
                form_data['date_from'] = None
        
        if date_to_str:
            try:
                form_data['date_to'] = datetime.strptime(date_to_str, '%Y-%m-%d').date()
            except (ValueError, AttributeError):
                form_data['date_to'] = None
        
        # Create form with the data
        search_form = UserSearchForm(**form_data)
    
    # Parse dates for database querying
    date_from = None
    date_to = None
    try:
        if date_from_str:
            date_from = datetime.strptime(date_from_str, '%Y-%m-%d')
        if date_to_str:
            date_to = datetime.strptime(date_to_str, '%Y-%m-%d')
    except ValueError:
        pass
    
    # Build query - FILTER NON-ADMIN USERS ONLY
    query = UserAcc.query.filter_by(is_admin=False)
    
    # Apply search filter
    if search_term:
        search_like = f"%{search_term}%"
        query = query.filter(
            (UserAcc.name.ilike(search_like)) | 
            (UserAcc.email.ilike(search_like))
        )
    
    # Apply status filter (based on is_active column)
    status_filters = {
        'active': lambda q: q.filter_by(is_active=True),
        'inactive': lambda q: q.filter_by(is_active=False),
        'all': lambda q: q
    }
    
    # Apply status filter using lambda
    if status_filter in status_filters:
        query = status_filters[status_filter](query)
    
    # Apply date filters (on date_created)
    if date_from:
        query = query.filter(UserAcc.date_created >= date_from)
    if date_to:
        # Add 1 day to include the entire end date
        date_to_end = date_to + timedelta(days=1)
        query = query.filter(UserAcc.date_created < date_to_end)
    
    # Get total count for pagination
    total_users = query.count()
    total_pages = (total_users + per_page - 1) // per_page if total_users > 0 else 1
    offset = (page - 1) * per_page
    
    # Get users for current page
    users = query.order_by(UserAcc.date_created.desc())\
                .offset(offset)\
                .limit(per_page)\
                .all()
    
    # Prepare user data for template
    users_data = []
    for user in users:
        # Get word count from UserWords table
        word_count = UserWords.query.filter_by(user_id=user.user_id).count()
        
        # Get achievement count
        achievement_count = UserAchievement.query.filter_by(user_id=user.user_id).count()
        
        # Determine status based on is_active column
        user_status = "Active" if user.is_active else "Inactive"
        
        # Get Pokémon name if exists
        pokemon_name = None
        if user.pokemon_id:
            pokemon = Pokemon.query.get(user.pokemon_id)
            pokemon_name = pokemon.name if pokemon else None
        if user.pokemon_name:
            pokemon_name = user.pokemon_name
        
        users_data.append({
            'user_id': user.user_id,
            'username': user.name,
            'email': user.email,
            'joined_date': user.date_created.strftime('%Y-%m-%d') if user.date_created else 'Unknown',
            'words_mastered': word_count,
            'status': user_status,
            'streak': user.current_streak or 0,
            'total_points': user.total_points or 0,
            'pokemon_name': pokemon_name or 'None',
            'achievement_count': achievement_count,
            'last_login': user.last_login.strftime('%Y-%m-%d %H:%M') if user.last_login else 'Never',
            'is_active': user.is_active  # Add this for template use
        })
    
    # Check if we need to show view modal
    view_user_id = request.args.get('view_user', type=int)
    view_form = None
    
    if view_user_id:
        user = UserAcc.query.get(view_user_id)
        if user and not user.is_admin:
            # Create view form with user data
            view_form = ViewUserForm()
            view_form.username.data = user.name
            view_form.email.data = user.email
            view_form.joined_date.data = user.date_created.strftime('%Y-%m-%d') if user.date_created else 'Unknown'
            
            # Find this user's word count from users_data
            user_word_count = next((u['words_mastered'] for u in users_data if u['user_id'] == user.user_id), 0)
            view_form.words_mastered.data = str(user_word_count)
            
            view_form.daily_streak.data = str(user.current_streak or 0)
            view_form.total_points.data = str(user.total_points or 0)
            
            # Determine status based on is_active column
            view_form.status.data = "Active" if user.is_active else "Inactive"
            
            # Get Pokémon name
            pokemon_name = 'None'
            if user.pokemon_id:
                pokemon = Pokemon.query.get(user.pokemon_id)
                pokemon_name = pokemon.name if pokemon else 'None'
            if user.pokemon_name:
                pokemon_name = user.pokemon_name
            view_form.pokemon_name.data = pokemon_name
            
            # Get achievement count
            achievement_count = UserAchievement.query.filter_by(user_id=user.user_id).count()
            view_form.achievement_count.data = str(achievement_count)
            
            view_form.last_login.data = user.last_login.strftime('%Y-%m-%d %H:%M') if user.last_login else 'Never'
    
    # Create other forms
    action_form = UserActionForm()
    pagination_form = PaginationForm()
    
    return render_template(
        'user_management.html',
        users=users_data,
        search_form=search_form,  # This will now include error messages
        action_form=action_form,
        pagination_form=pagination_form,
        view_form=view_form,
        current_page=page,
        total_pages=total_pages,
        total_users=total_users,
        search_term=search_term,
        status_filter=status_filter,
        date_from=date_from_str,
        date_to=date_to_str,
        show_view_modal=bool(view_user_id)
    )


@app.route('/admin/users/view/<int:user_id>')
@admin_required
def view_user(user_id):
    """Redirect to user management with view parameter"""
    return redirect(url_for('admin_users', 
                          view_user=user_id,
                          search=request.args.get('search', ''),
                          status=request.args.get('status', 'all'),
                          date_from=request.args.get('date_from', ''),
                          date_to=request.args.get('date_to', ''),
                          page=request.args.get('page', 1)))


@app.route('/admin/users/action/<int:user_id>/<action>')
@admin_required
def user_action_redirect(user_id, action):
    """Redirect to user management after action"""
    if action in ['activate', 'deactivate']:
        user = UserAcc.query.get(user_id)
        
        if user and not user.is_admin:
            if action == 'activate':
                user.is_active = True
                db.session.commit()
                flash(f"User {user.name} has been activated", "success")
            else:  # deactivate
                user.is_active = False
                db.session.commit()
                flash(f"User {user.name} has been deactivated", "warning")
        elif user and user.is_admin:
            flash("Cannot modify admin users", "error")
    
    return redirect(url_for('admin_users',
                          search=request.args.get('search', ''),
                          status=request.args.get('status', 'all'),
                          date_from=request.args.get('date_from', ''),
                          date_to=request.args.get('date_to', ''),
                          page=request.args.get('page', 1)))


@app.route('/admin/users/reset_filters')
@admin_required
def reset_user_filters():
    """Reset all search filters"""
    return redirect(url_for('admin_users'))

   
@app.route('/admin/achievements/add', methods=['POST'])
@admin_required
def add_achievement():
    """Add a new achievement"""
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data or not all(key in data for key in ['name', 'pokemon_id', 'description', 'requirement']):
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400
        
        # Check if Pokémon exists
        pokemon = Pokemon.query.get(data['pokemon_id'])
        if not pokemon:
            return jsonify({'success': False, 'error': 'Pokémon not found'}), 404
        
        # Check for duplicate achievement (same name)
        existing_achievement = Achievement.query.filter_by(name=data['name']).first()
        if existing_achievement:
            return jsonify({'success': False, 'error': 'Achievement with this name already exists'}), 409
        
        # Check for duplicate with same Pokémon reward
        existing_pokemon_achievement = Achievement.query.filter_by(pokemon_id=data['pokemon_id']).first()
        if existing_pokemon_achievement:
            return jsonify({'success': False, 'error': 'An achievement with this Pokémon reward already exists'}), 409
        
        # Create new achievement
        new_achievement = Achievement(
            name=data['name'],
            pokemon_id=data['pokemon_id'],
            description=data['description'],
            requirement=data['requirement'],
            points_reward=data.get('points_reward', 0)
        )
        
        db.session.add(new_achievement)
        db.session.flush()  # Get the achievement_id without committing
        
        # Get all non-admin users
        all_users = UserAcc.query.filter_by(is_admin=False).all()
        
        # Create UserAchievement entries for each user
        for user in all_users:
            user_achievement = UserAchievement(
                user_id=user.user_id,
                achievement_id=new_achievement.achievement_id,
                current_progress=0,
                date_earned=None  # Not earned yet
            )
            db.session.add(user_achievement)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Achievement added successfully. Created progress entries for {len(all_users)} users.',
            'achievement_id': new_achievement.achievement_id
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/admin/achievements/delete/<int:achievement_id>', methods=['DELETE'])
@admin_required
def delete_achievement(achievement_id):
    """Delete an achievement"""
    try:
        achievement = Achievement.query.get_or_404(achievement_id)
        
        # Delete all UserAchievement records associated with this achievement
        deleted_count = UserAchievement.query.filter_by(achievement_id=achievement_id).delete()
        
        # Delete the achievement itself
        db.session.delete(achievement)
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': f'Achievement deleted successfully. Removed {deleted_count} user progress records.'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/admin/insert_sample_pokemon')
@admin_required
def insert_sample_pokemon():
    """Insert sample Pokémon data into the database"""
    try:
        sample_pokemon = [
            # Generation 1 Starters
            (1, 'Bulbasaur', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/1.png', 0, 'common', 1),  # Changed from starter to common
            (2, 'Ivysaur', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/2.png', 100, 'uncommon', 1),  # Changed from common to uncommon
            (3, 'Venusaur', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/3.png', 300, 'rare', 1),
            
            (4, 'Charmander', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/4.png', 0, 'common', 2),  # Changed from starter to common
            (5, 'Charmeleon', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/5.png', 100, 'uncommon', 2),  # Changed from common to uncommon
            (6, 'Charizard', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/6.png', 300, 'rare', 2),
            
            (7, 'Squirtle', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/7.png', 0, 'common', 3),  # Changed from starter to common
            (8, 'Wartortle', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/8.png', 100, 'uncommon', 3),  # Changed from common to uncommon
            (9, 'Blastoise', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/9.png', 300, 'rare', 3),
            
            # Generation 2 Starters
            (152, 'Chikorita', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/152.png', 0, 'common', 4),  # Changed from starter to common
            (153, 'Bayleef', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/153.png', 100, 'uncommon', 4),  # Changed from common to uncommon
            (154, 'Meganium', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/154.png', 300, 'rare', 4),
            
            (155, 'Cyndaquil', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/155.png', 0, 'common', 5),  # Changed from starter to common
            (156, 'Quilava', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/156.png', 100, 'uncommon', 5),  # Changed from common to uncommon
            (157, 'Typhlosion', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/157.png', 300, 'rare', 5),
            
            (158, 'Totodile', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/158.png', 0, 'common', 6),  # Changed from starter to common
            (159, 'Croconaw', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/159.png', 100, 'uncommon', 6),  # Changed from common to uncommon
            (160, 'Feraligatr', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/160.png', 300, 'rare', 6),
            
            # Generation 3 Starters
            (252, 'Treecko', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/252.png', 0, 'common', 7),  # Changed from starter to common
            (253, 'Grovyle', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/253.png', 100, 'uncommon', 7),  # Changed from common to uncommon
            (254, 'Sceptile', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/254.png', 300, 'rare', 7),
            
            (255, 'Torchic', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/255.png', 0, 'common', 8),  # Changed from starter to common
            (256, 'Combusken', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/256.png', 100, 'uncommon', 8),  # Changed from common to uncommon
            (257, 'Blaziken', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/257.png', 300, 'rare', 8),
            
            (258, 'Mudkip', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/258.png', 0, 'common', 9),  # Changed from starter to common
            (259, 'Marshtomp', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/259.png', 100, 'uncommon', 9),  # Changed from common to uncommon
            (260, 'Swampert', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/260.png', 300, 'rare', 9),
            
            # Generation 4 Starters
            (387, 'Turtwig', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/387.png', 0, 'common', 10),  # Changed from starter to common
            (388, 'Grotle', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/388.png', 100, 'uncommon', 10),  # Changed from common to uncommon
            (389, 'Torterra', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/389.png', 300, 'rare', 10),
            
            (390, 'Chimchar', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/390.png', 0, 'common', 11),  # Changed from starter to common
            (391, 'Monferno', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/391.png', 100, 'uncommon', 11),  # Changed from common to uncommon
            (392, 'Infernape', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/392.png', 300, 'rare', 11),
            
            (393, 'Piplup', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/393.png', 0, 'common', 12),  # Changed from starter to common
            (394, 'Prinplup', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/394.png', 100, 'uncommon', 12),  # Changed from common to uncommon
            (395, 'Empoleon', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/395.png', 300, 'rare', 12),
            
            # Popular Pokémon (UNCHANGED)
            (25, 'Pikachu', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/25.png', 50, 'rare', 25),
            (26, 'Raichu', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/26.png', 200, 'epic', 26),
            
            (133, 'Eevee', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/133.png', 100, 'achievement', 133),
            (134, 'Vaporeon', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/134.png', 250, 'epic', 134),
            (135, 'Jolteon', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/135.png', 250, 'epic', 135),
            (136, 'Flareon', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/136.png', 250, 'epic', 136),
            
            # Legendary Pokémon (UNCHANGED)
            (144, 'Articuno', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/144.png', 500, 'legendary', 144),
            (145, 'Zapdos', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/145.png', 500, 'legendary', 145),
            (146, 'Moltres', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/146.png', 500, 'legendary', 146),
            
            (150, 'Mewtwo', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/150.png', 1000, 'achievement', 150),
            (151, 'Mew', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/151.png', 1000, 'legendary', 151),
            
            # Additional achievement Pokémon (UNCHANGED)
            (94, 'Gengar', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/94.png', 200, 'achievement', 94),
            (149, 'Dragonite', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/149.png', 300, 'achievement', 149),
            (130, 'Gyarados', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/130.png', 250, 'achievement', 130),
            (143, 'Snorlax', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/143.png', 150, 'achievement', 143),
            
            # More rare Pokémon (UNCHANGED)
            (248, 'Tyranitar', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/248.png', 400, 'epic', 248),
            (249, 'Lugia', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/249.png', 600, 'legendary', 249),
            (250, 'Ho-Oh', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/250.png', 600, 'legendary', 250),
            
            # Generation 5 Starters
            (495, 'Snivy', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/495.png', 0, 'common', 13),  # Changed from starter to common
            (496, 'Servine', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/496.png', 100, 'uncommon', 13),  # Changed from common to uncommon
            (497, 'Serperior', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/497.png', 300, 'rare', 13),
            
            (498, 'Tepig', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/498.png', 0, 'common', 14),  # Changed from starter to common
            (499, 'Pignite', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/499.png', 100, 'uncommon', 14),  # Changed from common to uncommon
            (500, 'Emboar', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/500.png', 300, 'rare', 14),
            
            (501, 'Oshawott', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/501.png', 0, 'common', 15),  # Changed from starter to common
            (502, 'Dewott', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/502.png', 100, 'uncommon', 15),  # Changed from common to uncommon
            (503, 'Samurott', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/503.png', 300, 'rare', 15),
        ]
        
        inserted_count = 0
        skipped_count = 0
        
        for pokemon_id, name, url, min_points, rarity, family_id in sample_pokemon:
            # Check if Pokémon already exists
            existing = Pokemon.query.filter_by(pokemon_id=pokemon_id).first()
            if not existing:
                pokemon = Pokemon(
                    pokemon_id=pokemon_id,
                    name=name,
                    url=url,
                    min_points_required=min_points,
                    rarity=rarity,
                    family_id=family_id
                )
                db.session.add(pokemon)
                inserted_count += 1
            else:
                # Update existing Pokémon
                existing.name = name
                existing.url = url
                existing.min_points_required = min_points
                existing.rarity = rarity
                existing.family_id = family_id
                db.session.add(existing)
                skipped_count += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Sample Pokémon data inserted successfully!',
            'inserted': inserted_count,
            'updated': skipped_count,
            'total': inserted_count + skipped_count
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
        
@app.route('/api/get_pokemon/<int:pokemon_id>')
@admin_required
def get_pokemon_details(pokemon_id):
    """Get details for a specific Pokémon"""
    try:
        pokemon = Pokemon.query.get(pokemon_id)
        
        if not pokemon:
            return jsonify({'success': False, 'error': 'Pokémon not found'}), 404
        
        return jsonify({
            'success': True,
            'pokemon': {
                'id': pokemon.pokemon_id,
                'name': pokemon.name,
                'img': pokemon.url or f'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{pokemon.pokemon_id}.png'
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    
@app.route('/admin/achievements/api/used-pokemon')
@admin_required
def get_used_pokemon():
    """Get list of Pokémon IDs already used in achievements"""
    try:
        # Query all achievements and get their Pokémon IDs
        used_pokemon_ids = [a.pokemon_id for a in Achievement.query.with_entities(Achievement.pokemon_id).all()]
        
        return jsonify({
            'success': True,
            'used_pokemon_ids': used_pokemon_ids
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/achievements/update/<int:achievement_id>', methods=['PUT'])
@admin_required
def update_achievement(achievement_id):
    """Update an existing achievement"""
    try:
        data = request.get_json()
        achievement = Achievement.query.get(achievement_id)
        
        if not achievement:
            return jsonify({'success': False, 'error': 'Achievement not found'}), 404
        
        # Check for duplicate name (excluding current achievement)
        if 'name' in data and data['name'] != achievement.name:
            existing_achievement = Achievement.query.filter_by(name=data['name']).first()
            if existing_achievement and existing_achievement.achievement_id != achievement_id:
                return jsonify({'success': False, 'error': 'Achievement with this name already exists'}), 409
        
        # Check for duplicate Pokémon reward (excluding current achievement)
        if 'pokemon_id' in data and data['pokemon_id'] != achievement.pokemon_id:
            existing_pokemon_achievement = Achievement.query.filter_by(pokemon_id=data['pokemon_id']).first()
            if existing_pokemon_achievement and existing_pokemon_achievement.achievement_id != achievement_id:
                return jsonify({'success': False, 'error': 'An achievement with this Pokémon reward already exists'}), 409
        
        # Update fields
        if 'name' in data:
            achievement.name = data['name']
        if 'pokemon_id' in data:
            achievement.pokemon_id = data['pokemon_id']
        if 'description' in data:
            achievement.description = data['description']
        if 'requirement' in data:
            # If requirement changes, reset all user progress
            old_requirement = achievement.requirement
            new_requirement = data['requirement']
            
            if new_requirement != old_requirement:
                achievement.requirement = new_requirement
                # Reset progress for all users (optional - you may want to keep their progress)
                UserAchievement.query.filter_by(achievement_id=achievement_id).update({'current_progress': 0})
        
        if 'points_reward' in data:
            achievement.points_reward = data['points_reward']
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Achievement updated successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    
@app.route('/admin/achievements/<int:achievement_id>')
@admin_required
def get_achievement(achievement_id):
    """Get achievement details for editing"""
    achievement = Achievement.query.get_or_404(achievement_id)
    
    return jsonify({
        'success': True,
        'achievement': {
            'achievement_id': achievement.achievement_id,
            'name': achievement.name,
            'description': achievement.description,
            'requirement': achievement.requirement,
            'pokemon_id': achievement.pokemon_id,
            'points_reward': achievement.points_reward
        }
    })
   
   
@app.route('/admin/achievements')
@admin_required
def admin_achievements():
    """Achievements management page"""
    # Get all achievements with their Pokémon
    achievements = Achievement.query.all()
    
    # Get Pokémon for each achievement
    for achievement in achievements:
        achievement.pokemon = Pokemon.query.get(achievement.pokemon_id)
        # Count how many users have this achievement
        achievement.user_count = UserAchievement.query.filter_by(
            achievement_id=achievement.achievement_id
        ).count()
    
    # Get ONLY achievement Pokémon for the selector (rarity='achievement')
    achievement_pokemon = Pokemon.query.filter_by(rarity='achievement').all()
    
    # Get total achievements count
    total_achievements = len(achievements)
    
    return render_template(
        'achievement_management.html',
        achievements=achievements,
        total_achievements=total_achievements,
        all_pokemon=achievement_pokemon  # Pass only achievement Pokémon
    )
    
@app.route('/api/get_user_pokemon', methods=['GET'])
def get_user_pokemon():
    requested_user_id = request.args.get('user_id', type=int)
    
    if not requested_user_id:
        if 'user_id' not in session:
            return jsonify({'success': False, 'error': 'Not logged in'}), 401
        requested_user_id = session['user_id']
    
    user_pokemon = UserPokemon.query.filter_by(user_id=requested_user_id).all()
    
    pokemon_list = []
    for up in user_pokemon:
        pokemon = Pokemon.query.get(up.pokemon_id)
        if pokemon:
            pokemon_data = {
                'pokemon_id': up.pokemon_id,
                'name': pokemon.name,
                'custom_name': up.custom_name,
                'url': pokemon.url,
                'rarity': pokemon.rarity,
                'min_points_required': pokemon.min_points_required,
                'date_obtained': up.date_obtained.strftime('%Y-%m-%d') if up.date_obtained else None
            }
            pokemon_list.append(pokemon_data)
    
    unique_species = len(set([p['pokemon_id'] for p in pokemon_list]))
    
    return jsonify({
        'success': True,
        'pokemon': pokemon_list,
        'total_collected': len(pokemon_list),
        'unique_species': unique_species
    })

@app.route('/api/set_pokemon_partner', methods=['POST'])
@login_required
def set_pokemon_partner():
    """Set a Pokémon from user's collection as their active partner"""
    try:
        user_id = session['user_id']
        data = request.get_json()
        
        if not data or 'pokemon_id' not in data:
            return jsonify({'success': False, 'error': 'Pokémon ID required'}), 400
        
        pokemon_id = data['pokemon_id']
        
        # Check if the user has collected this Pokémon
        user_has_pokemon = UserPokemon.query.filter_by(
            user_id=user_id, 
            pokemon_id=pokemon_id
        ).first()
        
        if not user_has_pokemon:
            return jsonify({'success': False, 'error': 'Pokémon not in your collection'}), 400
        
        # Get the Pokémon details
        pokemon = Pokemon.query.get(pokemon_id)
        if not pokemon:
            return jsonify({'success': False, 'error': 'Pokémon not found'}), 404
        
        # Get the user
        user = UserAcc.query.get(user_id)
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        # Check if this is already the current partner
        if user.pokemon_id == pokemon_id:
            return jsonify({
                'success': True, 
                'message': 'This Pokémon is already your partner!'
            })
        
        # Store the old partner info before changing
        old_partner_info = None
        if user.pokemon_id:
            old_partner_pokemon = Pokemon.query.get(user.pokemon_id)
            old_partner_user_entry = UserPokemon.query.filter_by(
                user_id=user_id, 
                pokemon_id=user.pokemon_id
            ).first()
            
            # Save the current custom name to UserPokemon before switching away
            if user.pokemon_name and old_partner_user_entry:
                # Only save if it's different from the Pokémon's default name
                pokemon_default_name = old_partner_pokemon.name if old_partner_pokemon else ""
                if user.pokemon_name != pokemon_default_name:
                    old_partner_user_entry.custom_name = user.pokemon_name
            
            old_partner_info = {
                'name': old_partner_pokemon.name if old_partner_pokemon else "Unknown",
                'custom_name': user.pokemon_name
            }
        
        # Get the custom name for the new partner from UserPokemon
        new_partner_user_entry = UserPokemon.query.filter_by(
            user_id=user_id, 
            pokemon_id=pokemon_id
        ).first()
        
        # Update the partner in UserAcc
        user.pokemon_id = pokemon_id
        
        # Set the name: Use custom name from UserPokemon if available, otherwise use Pokémon name
        if new_partner_user_entry and new_partner_user_entry.custom_name:
            user.pokemon_name = new_partner_user_entry.custom_name
        else:
            user.pokemon_name = pokemon.name
        
        # Create notification about partner change
        old_partner_display = old_partner_info['custom_name'] if old_partner_info and old_partner_info['custom_name'] else (old_partner_info['name'] if old_partner_info else "None")
        new_partner_display = user.pokemon_name
        
        notification = Notification(
            user_id=user_id,
            title='Partner Changed!',
            message=f'You switched from {old_partner_display} to {new_partner_display}! ⚡',
            notification_type='pokemon'
        )
        db.session.add(notification)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Switched partner to {user.pokemon_name}! ⚡',
            'pokemon_name': user.pokemon_name,
            'pokemon_url': pokemon.url,
            'old_partner_name': old_partner_display
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error setting Pokémon partner: {str(e)}")
        return jsonify({'success': False, 'error': 'Database error'}), 500

@app.route('/admin/achievements/api/pokemon')
@admin_required
def get_achievement_pokemon():
    """Get achievement Pokémon for the selector"""
    try:
        # Get only achievement Pokémon (rarity='achievement')
        achievement_pokemon = Pokemon.query.filter_by(rarity='achievement').all()
        
        # Format for frontend
        pokemon_list = []
        for pokemon in achievement_pokemon:
            pokemon_list.append({
                'id': pokemon.pokemon_id,
                'name': pokemon.name,
                'img': pokemon.url or f'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{pokemon.pokemon_id}.png'
            })
        
        return jsonify({
            'success': True,
            'pokemon': pokemon_list
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
  
  
@app.route('/insert_achievement_pokemon_data')
def insert_achievement_pokemon_data():
    """Insert Pokémon specifically for achievements"""
    achievement_pokemon_data = [
        # Rare Pokémon for achievements
        ('Pikachu', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/25.png', 0, 'achievement', 25),
        ('Eevee', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/133.png', 0, 'achievement', 133),
        ('Snorlax', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/143.png', 0, 'achievement', 143),
        ('Mew', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/151.png', 0, 'achievement', 151),
        ('Mewtwo', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/150.png', 0, 'achievement', 150),
        ('Dragonite', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/149.png', 0, 'achievement', 149),
        ('Charizard', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/6.png', 0, 'achievement', 6),
        ('Blastoise', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/9.png', 0, 'achievement', 9),
        ('Venusaur', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/3.png', 0, 'achievement', 3),
        ('Gyarados', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/130.png', 0, 'achievement', 130),
        ('Alakazam', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/65.png', 0, 'achievement', 65),
        ('Gengar', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/94.png', 0, 'achievement', 94),
        ('Machamp', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/68.png', 0, 'achievement', 68),
        ('Typhlosion', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/157.png', 0, 'achievement', 157),
        ('Feraligatr', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/160.png', 0, 'achievement', 160),
        ('Meganium', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/154.png', 0, 'achievement', 154),
        ('Tyranitar', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/248.png', 0, 'achievement', 248),
        ('Lugia', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/249.png', 0, 'achievement', 249),
        ('Ho-Oh', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/250.png', 0, 'achievement', 250),
        ('Celebi', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/251.png', 0, 'achievement', 251),
    ]

    inserted_count = 0
    for name, url, min_points, rarity, family_id in achievement_pokemon_data:
        # Check if Pokémon already exists
        existing = Pokemon.query.filter_by(name=name).first()
        if not existing:
            pokemon = Pokemon(
                name=name, 
                url=url, 
                min_points_required=min_points, 
                rarity=rarity, 
                family_id=family_id
            )
            db.session.add(pokemon)
            inserted_count += 1
        else:
            # Update existing Pokémon to achievement rarity
            existing.rarity = 'achievement'
            db.session.add(existing)

    db.session.commit()
    return f"Achievement Pokémon data inserted/updated successfully! {inserted_count} new Pokémon added."


@app.route('/insert_sample_achievements')
def insert_sample_achievements():
    """Insert sample achievements with achievement Pokémon"""
    # First make sure we have achievement Pokémon
    achievement_pokemon = [
        # Word Master achievements
        ('Word Novice', 'Learn your first 10 words', 10, 50),
        ('Word Apprentice', 'Master 50 vocabulary words', 50, 100),
        ('Word Scholar', 'Master 100 vocabulary words', 100, 200),
        ('Word Master', 'Master 250 vocabulary words', 250, 500),
        ('Vocabulary King', 'Master 500 vocabulary words', 500, 1000),
        
        # Streak achievements
        ('Streak Starter', 'Maintain a 3-day learning streak', 3, 50),
        ('Weekly Warrior', 'Maintain a 7-day learning streak', 7, 100),
        ('Monthly Master', 'Maintain a 30-day learning streak', 30, 500),
        ('Dedicated Learner', 'Maintain a 90-day learning streak', 90, 1000),
        
        # Pokémon evolution achievements
        ('First Evolution', 'Evolve your Pokémon for the first time', 1, 100),
        ('Evolution Expert', 'Evolve your Pokémon 5 times', 5, 500),
        ('Master Evolver', 'Evolve your Pokémon 10 times', 10, 1000),
        
        # Points achievements
        ('Point Collector', 'Earn 100 total points', 100, 50),
        ('Point Accumulator', 'Earn 500 total points', 500, 200),
        ('Point Master', 'Earn 1000 total points', 1000, 500),
        
        # Special achievements
        ('Daily Learner', 'Learn at least one word every day for a week', 7, 100),
        ('Quick Learner', 'Learn 10 words in a single day', 10, 150),
        ('Vocabulary Explorer', 'Learn words from 5 different categories', 5, 200),
    ]

    # Get achievement Pokémon from database
    achievement_pokemon_list = Pokemon.query.filter_by(rarity='achievement').all()
    
    if not achievement_pokemon_list:
        return "No achievement Pokémon found. Please run /insert_achievement_pokemon_data first."

    inserted_count = 0
    for i, (name, description, requirement, points_reward) in enumerate(achievement_pokemon):
        # Check if achievement already exists
        existing = Achievement.query.filter_by(name=name).first()
        if not existing:
            # Assign Pokémon from the list (cycling through them)
            pokemon_index = i % len(achievement_pokemon_list)
            pokemon = achievement_pokemon_list[pokemon_index]
            
            achievement = Achievement(
                name=name,
                description=description,
                requirement=requirement,
                points_reward=points_reward,
                pokemon_id=pokemon.pokemon_id
            )
            db.session.add(achievement)
            inserted_count += 1

    db.session.commit()
    return f"Sample achievements inserted successfully! {inserted_count} new achievements added."

    
@app.route('/admin/analytics', methods=['GET', 'POST'])
@admin_required
def admin_analytics():
    """Analytics dashboard page with date filtering"""
    # Default to current month
    today = datetime.now(ph_timezone).date()
    first_day = today.replace(day=1)
    
    # Get date parameters from form or use defaults
    if request.method == 'POST':
        # Handle form submission (non-AJAX)
        date_from_str = request.form.get('date_from')
        date_to_str = request.form.get('date_to')
        
        if date_from_str and date_to_str:
            try:
                date_from = datetime.strptime(date_from_str, '%Y-%m-%d').date()
                date_to = datetime.strptime(date_to_str, '%Y-%m-%d').date()
            except ValueError:
                date_from = first_day
                date_to = today
        else:
            date_from = first_day
            date_to = today
    else:
        # GET request - use default current month
        date_from = first_day
        date_to = today
    
    # Get statistics for the date range
    return render_template(
        'analytics_dashboard.html',
        date_from=date_from,
        date_to=date_to,
        **get_analytics_data(date_from, date_to)  # Create a helper function
    )
   
   
def get_analytics_data(date_from, date_to):
    """Helper function to get analytics data for a date range"""
    # Convert dates to datetime for queries
    date_from_dt = datetime.combine(date_from, datetime.min.time())
    date_to_dt = datetime.combine(date_to, datetime.max.time())
    
    # FIXED: Total users within the date range (NOT all time)
    total_users = UserAcc.query.filter(
        UserAcc.date_created >= date_from_dt,
        UserAcc.date_created <= date_to_dt,
        UserAcc.is_admin == False
    ).count()
    
    # Words stored in date range
    total_words = db.session.query(db.func.count(UserWords.user_word_id)).filter(
        UserWords.date_learned >= date_from_dt,
        UserWords.date_learned <= date_to_dt
    ).scalar() or 0
    
    # Active sessions (users logged in within the last 30 minutes) - EXCLUDE ADMIN
    thirty_minutes_ago = datetime.now(ph_timezone) - timedelta(minutes=30)
    active_sessions = UserAcc.query.filter(
        UserAcc.last_login >= thirty_minutes_ago,
        UserAcc.is_admin == False
    ).count()
    
    # Calculate growth vs previous period of same length
    period_days = (date_to - date_from).days + 1
    prev_date_from = date_from - timedelta(days=period_days)
    prev_date_to = date_from - timedelta(days=1)
    
    # User growth (users created in current period)
    current_users = total_users  # Already calculated above
    
    # Users in previous period
    prev_users = UserAcc.query.filter(
        UserAcc.date_created >= prev_date_from,
        UserAcc.date_created <= prev_date_to,
        UserAcc.is_admin == False
    ).count()
    
    user_growth = calculate_growth(current_users, prev_users)
    
    # Words growth
    prev_words = db.session.query(db.func.count(UserWords.user_word_id)).filter(
        UserWords.date_learned >= prev_date_from,
        UserWords.date_learned <= prev_date_to
    ).scalar() or 0
    
    words_growth = calculate_growth(total_words, prev_words)
    
    # Get top performing users for the date range
    top_users = get_top_users(date_from_dt, date_to_dt, limit=10)
    
    # Get learning hours estimate
    learning_hours = round(total_words * 2 / 60, 0)
    
    return {
        'total_users': total_users,  # Now within date range
        'total_words': total_words,
        'active_sessions': active_sessions,
        'learning_hours': int(learning_hours),
        'user_growth': round(user_growth, 1),
        'words_growth': round(words_growth, 1),
        'sessions_growth': 0,  # Not calculated for date ranges
        'current_month_users': current_users,
        'current_month_words': total_words,
        'current_month_logins': 0,  # Not needed for date ranges
        'top_users': top_users
    }

def calculate_growth(current, previous):
    """Calculate percentage growth"""
    if previous == 0:
        return 100 if current > 0 else 0
    return ((current - previous) / previous) * 100

def get_top_users(date_from, date_to, limit=10):
    """Get top users for a date range"""
    top_users_query = db.session.query(
        UserAcc.name,
        db.func.count(UserWords.user_word_id).label('word_count'),
        UserAcc.current_streak,
        UserAcc.total_points
    ).join(UserWords, UserAcc.user_id == UserWords.user_id).filter(
        UserWords.date_learned >= date_from,
        UserWords.date_learned <= date_to,
        UserAcc.is_admin == False
    ).group_by(UserAcc.user_id).order_by(
        db.desc('word_count')
    ).limit(limit).all()
    
    top_users = []
    for user in top_users_query:
        top_users.append({
            'username': user[0],
            'words_stored': user[1],
            'streak': user[2] or 0,
            'points': user[3] or 0
        })
    
    return top_users 
  
   
@app.route('/admin/api/analytics/filter', methods=['POST'])
@admin_required
def admin_api_analytics_filter():
    """API endpoint to filter analytics data"""
    try:
        data = request.get_json()
        
        # Get date parameters
        date_from_str = data.get('date_from')
        date_to_str = data.get('date_to')
        
        # Parse dates with error handling
        try:
            # Parse as naive datetime first
            date_from_naive = datetime.strptime(date_from_str, '%Y-%m-%d')
            date_to_naive = datetime.strptime(date_to_str, '%Y-%m-%d')
            
            # Convert to Philippine Time
            pht = pytz.timezone('Asia/Manila')
            date_from = pht.localize(date_from_naive)
            date_to = pht.localize(date_to_naive)
            
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid date format'}), 400
        
        # Ensure date_to is at the end of the day (23:59:59 in PHT)
        date_to = date_to.replace(hour=23, minute=59, second=59)
        
        # Calculate statistics for the date range
        # Total users (all users registered)
        total_users = UserAcc.query.count()
        
        # Total words stored (within date range) - using date_learned column
        # Note: date_learned is stored in database time (UTC), need to compare properly
        total_words = UserWords.query.filter(
            UserWords.date_learned >= date_from,
            UserWords.date_learned <= date_to
        ).count()
        
        # Active sessions (users with activity in date range)
        # Note: UserAcc doesn't have last_active field, using last_login instead
        active_users = UserAcc.query.filter(
            UserAcc.last_login >= date_from,
            UserAcc.last_login <= date_to
        ).count()
        
        # Top performing users
        top_users_query = db.session.query(
            UserAcc.name.label('username'),  # UserAcc has 'name' not 'username'
            db.func.count(UserWords.user_word_id).label('words_stored'),
            UserAcc.current_streak.label('streak'),  # UserAcc has 'current_streak' not 'streak'
            UserAcc.total_points.label('points')  # UserAcc has 'total_points' not 'points'
        ).join(UserWords, UserAcc.user_id == UserWords.user_id)\
         .filter(
            UserWords.date_learned >= date_from,
            UserWords.date_learned <= date_to
         )\
         .group_by(UserAcc.user_id)\
         .order_by(db.func.count(UserWords.user_word_id).desc())\
         .limit(10)\
         .all()
        
        top_users = []
        for user in top_users_query:
            top_users.append({
                'username': user.username,
                'words_stored': user.words_stored,
                'streak': user.streak,
                'points': user.points
            })
        
        return jsonify({
            'success': True,
            'data': {
                'total_users': total_users,
                'total_words': total_words,
                'active_sessions': active_users,
                'top_users': top_users,
                'date_from': date_from_str,
                'date_to': date_to_str
            }
        })
        
    except Exception as e:
        print(f"Error filtering analytics: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

    
@app.route('/admin/pokemon-config')
@admin_required
def pokemon_config():
    """Render the Pokémon configuration page"""
    search_form = PokemonSearchForm()
    add_form = PokemonAddForm()
    edit_form = PokemonEditForm()
    delete_form = PokemonDeleteForm()
    
    return render_template('pokemon_config.html',
                         form=search_form,
                         add_form=add_form,
                         edit_form=edit_form,
                         delete_form=delete_form)


@app.route('/admin/api/pokemon')
@admin_required
def admin_get_pokemon():
    """Get all Pokémon from database for admin configuration"""
    try:
        # Get all Pokémon from database
        all_pokemon = Pokemon.query.order_by(Pokemon.pokemon_id).all()
        
        # Format the data
        pokemon_list = []
        for pokemon in all_pokemon:
            pokemon_list.append({
                'pokemon_id': pokemon.pokemon_id,
                'name': pokemon.name,
                'url': pokemon.url or '',
                'min_points_required': pokemon.min_points_required,
                'rarity': pokemon.rarity,
                'family_id': pokemon.family_id
            })
        
        return jsonify({
            'success': True,
            'pokemon': pokemon_list
        })
        
    except Exception as e:
        print(f"Error getting Pokémon: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/admin/api/pokemon/add', methods=['POST'])
@admin_required
def admin_add_pokemon():
    """Add a new Pokémon to the database"""
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        # Check if Pokémon already exists (by name)
        existing_name = Pokemon.query.filter_by(name=data.get('name')).first()
        if existing_name:
            return jsonify({'success': False, 'error': 'Pokémon with this name already exists'}), 400
        
        # If ID is provided, check if it exists
        pokemon_id = data.get('pokemon_id')
        if pokemon_id:
            existing_id = Pokemon.query.filter_by(pokemon_id=pokemon_id).first()
            if existing_id:
                return jsonify({'success': False, 'error': 'Pokémon ID already exists'}), 400
        else:
            # Auto-generate ID
            last_pokemon = Pokemon.query.order_by(Pokemon.pokemon_id.desc()).first()
            pokemon_id = (last_pokemon.pokemon_id + 1) if last_pokemon else 1
        
        # Validate required fields
        required_fields = ['name', 'url', 'family_id']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'error': f'Missing required field: {field}'}), 400
        
        # Create new Pokémon
        new_pokemon = Pokemon(
            pokemon_id=pokemon_id,
            name=data['name'],
            url=data['url'],
            min_points_required=data.get('min_points_required', 0),
            rarity=data.get('rarity', 'common'),
            family_id=data['family_id']
        )
        
        db.session.add(new_pokemon)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Pokémon added successfully',
            'pokemon_id': new_pokemon.pokemon_id
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error adding Pokémon: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/admin/api/pokemon/update/<int:pokemon_id>', methods=['PUT'])
@admin_required
def admin_update_pokemon(pokemon_id):
    """Update an existing Pokémon"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        # Find the Pokémon
        pokemon = Pokemon.query.filter_by(pokemon_id=pokemon_id).first()
        if not pokemon:
            return jsonify({'success': False, 'error': 'Pokémon not found'}), 404
        
        # Update fields
        if 'rarity' in data:
            pokemon.rarity = data['rarity']
        
        if 'min_points_required' in data:
            pokemon.min_points_required = data['min_points_required']
        
        if 'family_id' in data:
            pokemon.family_id = data['family_id']
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Pokémon updated successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error updating Pokémon: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/admin/api/pokemon/delete/<int:pokemon_id>', methods=['DELETE'])
@admin_required
def admin_delete_pokemon(pokemon_id):
    """Delete a Pokémon from the database"""
    try:
        pokemon = Pokemon.query.get(pokemon_id)
        if not pokemon:
            return jsonify({'success': False, 'error': 'Pokémon not found'}), 404
        
        # Check if Pokémon is being used by users
        users_with_pokemon = UserAcc.query.filter_by(pokemon_id=pokemon_id).count()
        if users_with_pokemon > 0:
            return jsonify({
                'success': False, 
                'error': f'Cannot delete Pokémon. {users_with_pokemon} user(s) have this Pokémon.'
            }), 400
        
        # Check if Pokémon is being used by achievements
        achievements_with_pokemon = Achievement.query.filter_by(pokemon_id=pokemon_id).count()
        if achievements_with_pokemon > 0:
            return jsonify({
                'success': False, 
                'error': f'Cannot delete Pokémon. {achievements_with_pokemon} achievement(s) use this Pokémon.'
            }), 400
        
        # Delete the Pokémon
        db.session.delete(pokemon)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Pokémon deleted successfully'})
        
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting Pokémon: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/admin/api/pokemon/external')
@admin_required
def get_external_pokemon():
    """Get Pokémon list from external API (for adding new Pokémon)"""
    try:
        # Extended list of popular Pokémon
        popular_pokemon = [
            # Generation 1
            {"id": 1, "name": "Bulbasaur", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/1.png"},
            {"id": 4, "name": "Charmander", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/4.png"},
            {"id": 7, "name": "Squirtle", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/7.png"},
            {"id": 25, "name": "Pikachu", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/25.png"},
            {"id": 133, "name": "Eevee", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/133.png"},
            {"id": 143, "name": "Snorlax", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/143.png"},
            {"id": 150, "name": "Mewtwo", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/150.png"},
            {"id": 151, "name": "Mew", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/151.png"},
            
            # Generation 2
            {"id": 152, "name": "Chikorita", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/152.png"},
            {"id": 155, "name": "Cyndaquil", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/155.png"},
            {"id": 158, "name": "Totodile", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/158.png"},
            {"id": 249, "name": "Lugia", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/249.png"},
            {"id": 250, "name": "Ho-Oh", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/250.png"},
            
            # Generation 3
            {"id": 252, "name": "Treecko", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/252.png"},
            {"id": 255, "name": "Torchic", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/255.png"},
            {"id": 258, "name": "Mudkip", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/258.png"},
            {"id": 384, "name": "Rayquaza", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/384.png"},
            
            # Generation 4
            {"id": 387, "name": "Turtwig", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/387.png"},
            {"id": 390, "name": "Chimchar", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/390.png"},
            {"id": 393, "name": "Piplup", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/393.png"},
            {"id": 483, "name": "Dialga", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/483.png"},
            {"id": 484, "name": "Palkia", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/484.png"},
            
            # Generation 5
            {"id": 495, "name": "Snivy", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/495.png"},
            {"id": 498, "name": "Tepig", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/498.png"},
            {"id": 501, "name": "Oshawott", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/501.png"},
            {"id": 643, "name": "Reshiram", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/643.png"},
            {"id": 644, "name": "Zekrom", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/644.png"},
            
            # Generation 6
            {"id": 650, "name": "Chespin", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/650.png"},
            {"id": 653, "name": "Fennekin", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/653.png"},
            {"id": 656, "name": "Froakie", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/656.png"},
            
            # Generation 7
            {"id": 722, "name": "Rowlet", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/722.png"},
            {"id": 725, "name": "Litten", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/725.png"},
            {"id": 728, "name": "Popplio", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/728.png"},
            
            # Generation 8
            {"id": 810, "name": "Grookey", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/810.png"},
            {"id": 813, "name": "Scorbunny", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/813.png"},
            {"id": 816, "name": "Sobble", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/816.png"},
            
            # Generation 9
            {"id": 906, "name": "Sprigatito", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/906.png"},
            {"id": 909, "name": "Fuecoco", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/909.png"},
            {"id": 912, "name": "Quaxly", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/912.png"},
            
            # Popular evolutions and others
            {"id": 2, "name": "Ivysaur", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/2.png"},
            {"id": 3, "name": "Venusaur", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/3.png"},
            {"id": 5, "name": "Charmeleon", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/5.png"},
            {"id": 6, "name": "Charizard", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/6.png"},
            {"id": 8, "name": "Wartortle", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/8.png"},
            {"id": 9, "name": "Blastoise", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/9.png"},
            {"id": 94, "name": "Gengar", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/94.png"},
            {"id": 130, "name": "Gyarados", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/130.png"},
            {"id": 149, "name": "Dragonite", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/149.png"},
            {"id": 248, "name": "Tyranitar", "url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/248.png"},
        ]
        
        return jsonify({
            'success': True,
            'pokemon': popular_pokemon
        })
        
    except Exception as e:
        print(f"Error getting external Pokémon: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/api/pokemon/common')
@admin_required
def get_common_pokemon_for_starter():
    """Get Pokémon with rarity 'common' for starter selection"""
    try:
        common_pokemon = Pokemon.query.filter_by(rarity='common').order_by(Pokemon.pokemon_id).all()
        
        pokemon_list = []
        for pokemon in common_pokemon:
            pokemon_list.append({
                'pokemon_id': pokemon.pokemon_id,
                'name': pokemon.name,
                'url': pokemon.url or '',
                'rarity': pokemon.rarity,
                'family_id': pokemon.family_id
            })
        
        return jsonify({
            'success': True,
            'pokemon': pokemon_list
        })
        
    except Exception as e:
        print(f"Error getting common Pokémon: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/admin/api/pokemon/starters')
@admin_required
def get_starter_pokemon():
    """Get starter Pokémon (rarity: starter) and their family members"""
    try:
        # Get all starter Pokémon
        starter_pokemon = Pokemon.query.filter_by(rarity='starter').all()
        
        if not starter_pokemon:
            return jsonify({'success': True, 'pokemon': []})
        
        # Get all Pokémon that share family IDs with starters
        starter_family_ids = [pokemon.family_id for pokemon in starter_pokemon]
        
        # Get all Pokémon in those families
        family_pokemon = Pokemon.query.filter(
            Pokemon.family_id.in_(starter_family_ids)
        ).order_by(Pokemon.family_id, Pokemon.min_points_required).all()
        
        # Format the data
        pokemon_list = []
        for pokemon in family_pokemon:
            pokemon_list.append({
                'pokemon_id': pokemon.pokemon_id,
                'name': pokemon.name,
                'url': pokemon.url or '',
                'min_points_required': pokemon.min_points_required,
                'rarity': pokemon.rarity,
                'family_id': pokemon.family_id
            })
        
        return jsonify({
            'success': True,
            'pokemon': pokemon_list
        })
        
    except Exception as e:
        print(f"Error getting starter Pokémon: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    
    
@app.route('/admin/api/pokemon/family/<int:family_id>')
@admin_required
def get_pokemon_by_family(family_id):
    """Get all Pokémon in a specific family, ordered by evolution"""
    try:
        family_pokemon = Pokemon.query.filter_by(family_id=family_id)\
                                      .order_by(Pokemon.min_points_required)\
                                      .all()
        
        pokemon_list = []
        for pokemon in family_pokemon:
            pokemon_list.append({
                'pokemon_id': pokemon.pokemon_id,
                'name': pokemon.name,
                'url': pokemon.url or '',
                'min_points_required': pokemon.min_points_required,
                'rarity': pokemon.rarity,
                'family_id': pokemon.family_id
            })
        
        return jsonify({
            'success': True,
            'pokemon': pokemon_list
        })
        
    except Exception as e:
        print(f"Error getting Pokémon by family: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    
    
    
@app.route('/admin/analytics/export', methods=['POST'])
@admin_required
def export_analytics():
    """Export analytics data as TXT"""
    try:
        data = request.get_json()
        date_from_str = data.get('date_from')
        date_to_str = data.get('date_to')
        
        # Parse dates
        date_from = datetime.strptime(date_from_str, '%Y-%m-%d').date()
        date_to = datetime.strptime(date_to_str, '%Y-%m-%d').date()
        
        # Get analytics data
        analytics_data = get_analytics_data(date_from, date_to)
        
        # Create TXT content with simple format
        txt_content = []
        
        # Add header
        txt_content.append("Analytics Dashboard Export")
        txt_content.append(f"Date Range: {date_from_str} to {date_to_str}")
        txt_content.append(f"Exported on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        txt_content.append("")
        
        # Platform Statistics
        txt_content.append(f"Total Users: {analytics_data['total_users']}")
        txt_content.append(f"Words Stored: {analytics_data['total_words']}")
        txt_content.append(f"Active Sessions: {analytics_data['active_sessions']}")
        txt_content.append("")
        
        # Top Performing Users
        txt_content.append("Top Performing")
        txt_content.append("Names:")
        
        if analytics_data['top_users']:
            for i, user in enumerate(analytics_data['top_users'], 1):
                txt_content.append(f"{i}. {user['username']}")
        else:
            txt_content.append("No users found")
        
        # Convert to TXT string
        txt_output = "\n".join(txt_content)
        
        # Create response
        response = make_response(txt_output)
        response.headers['Content-Type'] = 'text/plain'
        response.headers['Content-Disposition'] = f'attachment; filename=analytics_{date_from_str}_to_{date_to_str}.txt'
        
        return response
        
    except Exception as e:
        print(f"Export error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)

