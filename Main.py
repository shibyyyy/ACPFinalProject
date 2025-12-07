from flask import Flask, render_template, session, redirect, url_for, flash, request, jsonify
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash
from forms import LoginForm, SignupForm, AddWordForm
from models import db,UserAcc, UserAchievement, UserWords, Pokemon, Achievement
from functools import wraps
import os
from datetime import datetime
import pytz
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

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

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
            # Update last_login before saving to session
            user.last_login = datetime.now(ph_timezone)
            db.session.commit()  # Save the update to database
            
            session['user_id'] = user.user_id
            session['username'] = user.name
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

        flash("Account created successfully! Please log in.", "success")
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

@app.route('/forgotpass')
def forgotpass():
    return render_template('forgotpass.html')

@app.route('/features')
def features():
    return render_template('features.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')


@app.route('/profile')
@login_required
def profile():
    user_id = session.get('user_id') 
    
    if not user_id:
        return redirect(url_for('login'))
    
    # Get user data
    user = UserAcc.query.get(user_id)
    if not user:
        return redirect(url_for('login'))
    
    # Get user's Pokémon
    pokemon = Pokemon.query.get(user.pokemon_id) if user.pokemon_id else None
    
    # Get Pokémon display name - NOW pokemon is defined
    pokemon_display_name = "No Pokémon"
    if pokemon:
        pokemon_display_name = pokemon.name
        if hasattr(user, 'pokemon_name') and user.pokemon_name:
            pokemon_display_name = user.pokemon_name
    
    # Count words learned by user
    words_learned = UserWords.query.filter_by(user_id=user_id).count()
    
    # Get user achievements with progress
    user_achievements = UserAchievement.query.filter_by(user_id=user_id).all()
    
    # Get all achievements to show locked ones too
    all_achievements = Achievement.query.all()
    
    # Get Pokémon for achievements
    achievement_pokemon = {}
    for ach in all_achievements:
        pokemon_data = Pokemon.query.get(ach.pokemon_id)
        if pokemon_data:
            achievement_pokemon[ach.achievement_id] = pokemon_data
    
    return render_template('profile.html', 
                         user=user,
                         pokemon=pokemon,
                         words_learned=words_learned,
                         pokemon_display_name=pokemon_display_name,
                         user_achievements=user_achievements,
                         all_achievements=all_achievements,
                         achievement_pokemon=achievement_pokemon)

@app.route('/challenges')
def challenges():
    return render_template('challenges.html')

@app.route('/wordbank')
def wordbank():
    return render_template('wordbank.html')

@app.route('/review')
def review():
    return render_template('review.html')

@app.route('/progress')
def progress():
    return render_template('progress.html')

@app.route('/leaderboard')
def leaderboard():
    return render_template('leaderboard.html')

@app.route('/addword')
def addword():
    form = AddWordForm()
    return render_template('addword.html',form=form)

@app.route('/flashcard')
def flashcard():
    return render_template('flashcard.html')

@app.route('/multichoi')
def multichoi():
    return render_template('multichoi.html')

@app.route('/matchingtype')
def matchingtype():
    return render_template('matchingtype.html') 

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)