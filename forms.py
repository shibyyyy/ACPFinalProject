from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, TextAreaField, SelectField, IntegerField, BooleanField, DateField, SelectMultipleField, HiddenField
from wtforms.validators import DataRequired, NumberRange, Length, Email, Optional, ValidationError, EqualTo
from datetime import datetime
import re




class LoginForm(FlaskForm):
    email = StringField(
        'Username',
        validators=[DataRequired()],
        render_kw={"placeholder": "Enter your email"}
        )
    password = PasswordField(
        'Password',
        validators=[DataRequired()],
        render_kw={"placeholder": "Enter your password"}
        )
    submit = SubmitField(
        'Login',
        render_kw={"class": "btn-primary"}
        )
   
class SignupForm(FlaskForm):
    username = StringField(
        validators=[DataRequired(),Length(min=4, max=25, message="Invalid username.")],
        render_kw={"placeholder": "Username"}
        )
    email = StringField(
        validators=[DataRequired(),Email(message="Invalid email address.")],
        render_kw={"placeholder": "Email"}
        )
    password = PasswordField(
        validators=[DataRequired(),Length(min=8, message="Password must be at least 8 characters long.")],
        render_kw={"placeholder": "Password"}
        )
    confirm_password = PasswordField(
        validators=[DataRequired(),Length(min=8, message="Password must be at least 8 characters long.")],
        render_kw={"placeholder": "Confirm Password"}
        )
    submit = SubmitField(
        'Create Account',
        render_kw={"class": "btn-primary"}
        )


class ForgotPasswordForm(FlaskForm):
    email = StringField(
        'Email',
        validators=[DataRequired(), Email(message="Invalid email address.")],
        render_kw={"placeholder": "Enter your email"}
    )
    password = PasswordField(
        'New Password',
        validators=[DataRequired(), Length(min=8, message="Password must be at least 8 characters long.")],
        render_kw={"placeholder": "New Password"}
    )
    confirm_password = PasswordField(
        'Confirm Password',
        validators=[DataRequired(), Length(min=8, message="Password must be at least 8 characters long.")],
        render_kw={"placeholder": "Confirm Password"}
    )
    submit = SubmitField(
        'Reset Password',
        render_kw={"class": "btn-primary"}
    )

class AddWordForm(FlaskForm):
    word = StringField(
        validators=[DataRequired()],
        render_kw={"placeholder": "New Word"}
    )
    definition = TextAreaField(
        validators=[DataRequired()],
        render_kw={"rows" : 3, "placeholder": "Definition", "readonly": True}
    )
    sentence = TextAreaField(
        validators=[DataRequired()],
        render_kw={"rows" : 3, "placeholder": "Example Sentence"}
    )
    submit = SubmitField(
        'Add Word',
        render_kw={"class": "btn-primary"}
    )
    
    def validate_sentence(self, field):
        """
        Custom validation for the sentence field.
        Validates that the sentence is a proper English sentence.
        """
        sentence = field.data.strip()
        
        if not sentence:
            return  # DataRequired validator will handle empty fields
        
        # Check if sentence is at least 3 words
        words = sentence.split()
        if len(words) < 3:
            raise ValidationError('Example sentence should be at least 3 words long.')
        
        # Check if sentence starts with a capital letter
        if not sentence[0].isupper():
            raise ValidationError('Example sentence must start with a capital letter.')
        
        # Check if sentence ends with proper punctuation
        valid_endings = ['.', '!', '?']
        if not any(sentence.endswith(punct) for punct in valid_endings):
            raise ValidationError('Example sentence must end with proper punctuation (. ! or ?).')
        
        # Check for consecutive spaces
        if '  ' in sentence:
            raise ValidationError('Sentence contains multiple consecutive spaces.')
        
        # Check for proper spacing after punctuation (optional)
        # This is a more advanced check
        import re
        if re.search(r'[.!?][a-zA-Z]', sentence):
            raise ValidationError('There should be a space after punctuation marks.')

class UserSearchForm(FlaskForm):
    """Form for searching users - matches your HTML inputs"""
    search = StringField(
        'Search',
        validators=[Optional()],
        render_kw={
            "placeholder": "Search users by name or email...",
            "class": "search-input",
            "id": "searchInput"
        }
    )
   
    status = SelectField(
        'Status',
        choices=[
            ('all', 'All Status'),
            ('active', 'Active'),
            ('inactive', 'Inactive')
        ],
        validators=[Optional()],
        default='all',
        render_kw={
            "class": "filter-select",
            "id": "statusFilter"
        }
    )
   
    date_from = DateField(
        'Date From',
        format='%Y-%m-%d',
        validators=[Optional()],
        render_kw={
            "class": "date-input",
            "id": "dateFrom"
        }
    )
   
    date_to = DateField(
        'Date To',
        format='%Y-%m-%d',
        validators=[Optional()],
        render_kw={
            "class": "date-input",
            "id": "dateTo"
        }
    )
   
    submit = SubmitField(
        'Search',
        render_kw={"class": "action-btn"}
    )
   
    filter_btn = SubmitField(
        'Apply Filters',
        render_kw={"class": "action-btn"}
    )
    
    def validate(self, extra_validators=None):
        """Custom validation for date range"""
        # Run standard validation first
        initial_validation = super().validate(extra_validators=extra_validators)
        if not initial_validation:
            return False
            
        # Custom validation for date range
        if self.date_from.data and self.date_to.data:
            if self.date_from.data > self.date_to.data:
                self.date_from.errors.append('"From" date cannot be later than "To" date')
                return False
                
        return True

class UserActionForm(FlaskForm):
    """Form for individual user actions - JUST DATA COLLECTION"""
    user_id = HiddenField('User ID', validators=[DataRequired()])
    action = HiddenField('Action', validators=[DataRequired()])  # 'activate', 'deactivate', 'view'
    submit = SubmitField('Confirm')

class PaginationForm(FlaskForm):
    """Form for pagination"""
    page = HiddenField('Page', validators=[Optional()], default=1)
    submit = SubmitField('Go')


class ViewUserForm(FlaskForm):
    """Form for displaying user details in modal"""
    username = StringField('Username')
    email = StringField('Email')
    joined_date = StringField('Joined Date')
    words_mastered = StringField('Words Mastered')
    daily_streak = StringField('Daily Streak')
    status = StringField('Status')
    total_points = StringField('Total Points')
    pokemon_name = StringField('Pokémon')
    achievement_count = StringField('Achievements')
    last_login = StringField('Last Login')
   
   
class PokemonSearchForm(FlaskForm):
    """Form for searching Pokémon"""
    search = StringField(
        'Search',
        validators=[Optional()],
        render_kw={
            "placeholder": "Search Pokémon by name, ID, or rarity...",
            "class": "search-input",
            "id": "searchInput"
        }
    )
    submit = SubmitField(
        'Search',
        render_kw={"class": "search-btn"}
    )

class PokemonAddForm(FlaskForm):
    """Form for adding a new Pokémon"""
    name = StringField(
        'Pokémon Name',
        validators=[DataRequired()],
        render_kw={
            "class": "form-input",
            "readonly": True
        }
    )
    pokemon_id = IntegerField(
        'Pokémon ID',
        validators=[DataRequired()],
        render_kw={
            "class": "form-input",
            "readonly": True
        }
    )
    url = StringField(
        'Image URL',
        validators=[DataRequired(), Length(max=500)],
        render_kw={
            "class": "form-input",
            "placeholder": "Enter image URL"
        }
    )
    min_points_required = IntegerField(
        'Min Points Required',
        validators=[DataRequired(), NumberRange(min=0)],
        default=0,
        render_kw={
            "class": "form-input",
            "placeholder": "0",
            "min": "0"
        }
    )
    family_id = IntegerField(
        'Family ID',
        validators=[DataRequired(), NumberRange(min=1)],
        render_kw={
            "class": "form-input",
            "placeholder": "1",
            "min": "1"
        }
    )
    rarity = SelectField(
        'Rarity',
        choices=[
            ('common', 'Common'),
            ('uncommon', 'Uncommon'),
            ('rare', 'Rare'),
            ('epic', 'Epic'),
            ('legendary', 'Legendary'),
            ('starter', 'Starter'),
            ('achievement', 'Achievement')
        ],
        validators=[DataRequired()],
        default='common',
        render_kw={"class": "form-select"}
    )
    submit = SubmitField(
        'Add Pokémon',
        render_kw={"class": "btn-confirm"}
    )

class PokemonEditForm(FlaskForm):
    """Form for editing an existing Pokémon"""
    name = StringField(
        'Pokémon Name',
        validators=[DataRequired(), Length(max=50)],
        render_kw={"class": "form-input"}
    )
    pokemon_id = IntegerField(
        'Pokémon ID',
        validators=[DataRequired()],
        render_kw={
            "class": "form-input",
            "readonly": True
        }
    )
    url = StringField(
        'Image URL',
        validators=[DataRequired(), Length(max=500)],
        render_kw={
            "class": "form-input",
            "placeholder": "Enter image URL"
        }
    )
    min_points_required = IntegerField(
        'Min Points Required',
        validators=[DataRequired(), NumberRange(min=0)],
        render_kw={
            "class": "form-input",
            "placeholder": "0",
            "min": "0"
        }
    )
    family_id = IntegerField(
        'Family ID',
        validators=[DataRequired(), NumberRange(min=1)],
        render_kw={
            "class": "form-input",
            "placeholder": "1",
            "min": "1"
        }
    )
    rarity = SelectField(
        'Rarity',
        choices=[
            ('common', 'Common'),
            ('uncommon', 'Uncommon'),
            ('rare', 'Rare'),
            ('epic', 'Epic'),
            ('legendary', 'Legendary'),
            ('starter', 'Starter'),
            ('achievement', 'Achievement')
        ],
        validators=[DataRequired()],
        render_kw={"class": "form-select"}
    )
    submit = SubmitField(
        'Save Changes',
        render_kw={"class": "btn-confirm"}
    )

class PokemonDeleteForm(FlaskForm):
    """Form for deleting a Pokémon"""
    pokemon_id = HiddenField('Pokémon ID', validators=[DataRequired()])
    pokemon_name = HiddenField('Pokémon Name')
    confirm = SubmitField(
        'Delete',
        render_kw={"class": "btn-confirm red"}
    )
    cancel = SubmitField(
        'Cancel',
        render_kw={"class": "btn-cancel"}
    )
