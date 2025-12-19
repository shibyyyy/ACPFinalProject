from datetime import datetime
from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


# ---------------- POKEMON TABLE ----------------
class Pokemon(db.Model):
    pokemon_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    url = db.Column(db.String(200))
    min_points_required = db.Column(db.Integer, default=0)
    rarity = db.Column(db.String(20), default="common")
    family_id = db.Column(db.Integer, nullable=False)


# ---------------- ACHIEVEMENTS TABLE ----------------
class Achievement(db.Model):
    achievement_id = db.Column(db.Integer, primary_key=True)
    pokemon_id = db.Column(db.Integer, db.ForeignKey('pokemon.pokemon_id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    points_reward = db.Column(db.Integer, default=0)
    requirement = db.Column(db.Integer,default=0)


# ---------------- USER TABLE ----------------
class UserAcc(db.Model):
    user_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    date_created = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    last_logout = db.Column(db.DateTime)
    pokemon_name = db.Column(db.String(100))
    pokemon_id = db.Column(db.Integer, db.ForeignKey('pokemon.pokemon_id'))
    profile_picture = db.Column(db.String(200))
    current_streak = db.Column(db.Integer, default=0)
    longest_streak = db.Column(db.Integer, default=0)
    total_points = db.Column(db.Integer, default=0)  # Pokémon EXP
    collected_pokemon = db.relationship('UserPokemon', backref='owner', lazy=True, cascade='all, delete-orphan')
    
class UserPokemon(db.Model):
    user_pokemon_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user_acc.user_id'), nullable=False)
    pokemon_id = db.Column(db.Integer, db.ForeignKey('pokemon.pokemon_id'), nullable=False)
    date_obtained = db.Column(db.DateTime, nullable=False)
    custom_name = db.Column(db.String(100))
    
    # Optional: Add unique constraint to prevent duplicate entries
    __table_args__ = (db.UniqueConstraint('user_id', 'pokemon_id', name='unique_user_pokemon'),)


# ---------------- VOCABULARY TABLE ----------------
class Vocabulary(db.Model):
    word_id = db.Column(db.Integer, primary_key=True)
    word = db.Column(db.String(100), nullable=False)
    definition = db.Column(db.Text)
    example_sentence = db.Column(db.Text)
    category = db.Column(db.String(50))
    points_value = db.Column(db.Integer, default=10)
    is_word_of_day = db.Column(db.Boolean, default=False)


# ---------------- USER WORDS TABLE ----------------
class UserWords(db.Model):
    user_word_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user_acc.user_id'), nullable=False)
    word_id = db.Column(db.Integer, db.ForeignKey('vocabulary.word_id'), nullable=False)
    date_learned = db.Column(db.DateTime, default=datetime.utcnow)


# ---------------- USER ACHIEVEMENTS TABLE ----------------
class UserAchievement(db.Model):
    user_achievement_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user_acc.user_id'), nullable=False)
    achievement_id = db.Column(db.Integer, db.ForeignKey('achievement.achievement_id'), nullable=False)
    current_progress = db.Column(db.Integer, default=0)
    date_earned = db.Column(db.DateTime)


# ---------------- NOTIFICATION TABLE ----------------  
class Notification(db.Model):
    notification_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user_acc.user_id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(50), nullable=False)  # e.g., 'achievement', 'streak', 'level_up', 'pokemon', 'reminder'
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)