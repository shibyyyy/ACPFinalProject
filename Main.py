from flask import Flask, render_template, session, redirect, url_for, flash, request, jsonify
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash
from forms import LoginForm, SignupForm, AddWordForm
from models import db,UserAcc, UserAchievement, UserWords, Pokemon, Achievement, Vocabulary
from functools import wraps
import os
from datetime import datetime
import pytz
from sqlalchemy.sql import func
from datetime import datetime, timedelta

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

@app.route('/add_to_collection/<int:word_id>', methods=['POST'])
@login_required
def add_to_collection(word_id):
    user = get_current_user()
    existing = UserWords.query.filter_by(user_id=user.user_id, word_id=word_id).first()
    if not existing:
        vocab = Vocabulary.query.get(word_id)

        # Always initialize
        definition = vocab.definition or ""
        example = vocab.example_sentence or ""

        # If missing, try fetching from API
        if not definition or not example:
            url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{vocab.word}"
            response = request.get(url)
            if response.ok:
                data = response.json()[0]
                for meaning in data["meanings"]:
                    if not vocab.category and "partOfSpeech" in meaning:
                        vocab.category = meaning.get("partOfSpeech", "")
                    for d in meaning["definitions"]:
                        if not definition and "definition" in d:
                            definition = d["definition"]
                        if not example and "example" in d:
                            example = d["example"]
                        if definition and example:
                            break

        vocab.definition = definition
        vocab.example_sentence = example
        db.session.commit()

        new_entry = UserWords(user_id=user.user_id, word_id=word_id)
        db.session.add(new_entry)
        db.session.commit()

    return redirect(url_for('dashboard'))

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
            'img': p.url or ''
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
    evolutions = user.total_points // 50  # evolve every 50 EXP
    streak = user.current_streak
    accuracy = 95  # placeholder until you compute review accuracy


    return render_template(
        'dashboard.html',
        showStarterModal=showStarterModal,
        starterPokemon=user.pokemon_id,
        pokemons=pokemons_list,
        weekly_total=weekly_total,
        evolutions=evolutions,
        streak=streak,
        accuracy=accuracy,
        total_points=user.total_points
    )


   
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
def review():
    return render_template('review.html')

@app.route("/progress")
@login_required
def progress():
    user = get_current_user()
    today = datetime.utcnow().date()

    # Get user's current Pokémon
    user_pokemon = None
    if user.pokemon_id:
        user_pokemon = Pokemon.query.get(user.pokemon_id)
    
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

    # Totals
    weekly_total = sum(weekly_data.values())
    
    # Calculate evolution progress properly
    evolutions = 0
    if user_pokemon:
        # Count how many Pokémon user has unlocked based on min_points_required
        unlocked_pokemon = Pokemon.query.filter(
            Pokemon.min_points_required <= user.total_points
        ).count()
        evolutions = unlocked_pokemon - 1  # Subtract the starter Pokémon
    
    # Get next evolution requirements
    next_evolution = None
    progress_percentage = 0
    if user_pokemon:
        # Find next Pokémon that requires more points
        next_evolution = Pokemon.query.filter(
            Pokemon.min_points_required > user_pokemon.min_points_required
        ).order_by(Pokemon.min_points_required).first()
        
        if next_evolution:
            # Calculate progress percentage
            points_needed = next_evolution.min_points_required - user_pokemon.min_points_required
            points_progress = user.total_points - user_pokemon.min_points_required
            if points_needed > 0:
                progress_percentage = min(100, (points_progress / points_needed) * 100)
            else:
                progress_percentage = 100

    return render_template("progress.html",
                           daily_data=daily_data,
                           weekly_data=weekly_data,
                           monthly_data=monthly_data,
                           weekly_total=weekly_total,
                           evolutions=evolutions,
                           user_pokemon=user_pokemon,
                           next_evolution=next_evolution,
                           progress_percentage=progress_percentage,
                           current_user=user)

@app.route('/leaderboard')
@login_required
def leaderboard():
    user = get_current_user()
    
    # Get all users ordered by total_points
    all_users = UserAcc.query.order_by(UserAcc.total_points.desc()).all()
    
    # Prepare leaderboard data with ranks and word counts
    leaderboard_data = []
    for i, user_acc in enumerate(all_users, 1):
        # Count words for this user
        word_count = UserWords.query.filter_by(user_id=user_acc.user_id).count()
        
        leaderboard_data.append({
            'rank': i,
            'username': user_acc.name,
            'score': user_acc.total_points,
            'words': word_count,
            'is_current_user': user_acc.user_id == user.user_id
        })
    
    # Find current user's data
    current_user_data = None
    for entry in leaderboard_data:
        if entry['is_current_user']:
            current_user_data = entry
            break
    
    # Get top 3 for podium (even if empty, we'll handle it in template)
    podium_users = leaderboard_data[:3] if len(leaderboard_data) >= 3 else leaderboard_data
    
    # Calculate current user's word count
    current_user_word_count = UserWords.query.filter_by(user_id=user.user_id).count()
    
    return render_template('leaderboard.html', 
                         leaderboard_data=leaderboard_data[:50],  # Show top 50
                         podium_users=podium_users,
                         current_user_data=current_user_data,
                         user_rank=current_user_data['rank'] if current_user_data else len(leaderboard_data) + 1,
                         current_user=user,
                         current_user_word_count=current_user_word_count)
    

@app.route("/add_word", methods=["GET", "POST"])
@login_required
def add_word():
    form = AddWordForm()
    user = get_current_user()


    current_pokemon = None
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
            # Pick the highest evolution the user qualifies for
            for evo in evolution_line:
                if user.total_points >= evo.min_points_required:
                    current_pokemon = evo


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
            user_word = UserWords(user_id=user.user_id, word_id=vocab.word_id)
            db.session.add(user_word)
            user.total_points = (user.total_points or 0) + vocab.points_value


        db.session.commit()
        flash(f"Word '{form.word.data}' added successfully!", "success")


    return render_template("addword.html", form=form, current_pokemon=current_pokemon, user=user)


@app.route('/save_word_of_day', methods=['POST'])
@login_required
def save_word_of_day():
    user = get_current_user()
    
    word = request.form.get('word', '').strip()
    pronunciation = request.form.get('pronunciation', '').strip()
    word_type = request.form.get('word_type', '').strip()
    meaning = request.form.get('meaning', '').strip()
    example_sentence = request.form.get('example_sentence', '').strip()
    
    if not all([word, pronunciation, word_type, meaning, example_sentence]):
        return jsonify({'success': False, 'message': 'Missing word details'})
    
    try:
        # Check if word already exists in Words table
        existing_word = Words.query.filter_by(word=word, pronunciation=pronunciation).first()
        
        if existing_word:
            word_id = existing_word.word_id
        else:
            # Create new word
            new_word = Words(
                word=word,
                pronunciation=pronunciation,
                word_type=word_type,
                meaning=meaning,
                example_sentence=example_sentence
            )
            db.session.add(new_word)
            db.session.flush()  # Get the ID without committing
            word_id = new_word.word_id
        
        # Check if user already has this word
        existing_user_word = UserWords.query.filter_by(
            user_id=user.user_id,
            word_id=word_id
        ).first()
        
        if existing_user_word:
            return jsonify({'success': False, 'message': 'Word already in your collection'})
        
        # Add to user's collection
        user_word = UserWords(
            user_id=user.user_id,
            word_id=word_id,
            date_learned=datetime.utcnow().date(),
            next_review_date=datetime.utcnow().date() + timedelta(days=1),
            review_count=0,
            confidence_level=1
        )
        db.session.add(user_word)
        
        # Update user points
        user.total_points += 5  # Award 5 points for saving word of the day
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Word saved successfully!'})
        
    except Exception as e:
        db.session.rollback()
        print(f"Error saving word: {str(e)}")
        return jsonify({'success': False, 'message': 'Database error occurred'})



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
