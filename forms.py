from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, TextAreaField, SelectField, IntegerField, BooleanField
from wtforms.validators import DataRequired, NumberRange, Length, Email

class LoginForm(FlaskForm):
    username = StringField(
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
    terms = BooleanField(
        'I agree to the Terms of Service and Privacy Policy and accept that my data will be used as described.',
        validators=[DataRequired(message="You must agree to the terms and conditions.")],
    )
    submit = SubmitField(
        'Create Account',
        render_kw={"class": "btn-primary"}
        )

class AddWordForm(FlaskForm):
    word = StringField(
        validators=[DataRequired()],
        render_kw={"placeholder": "New Word"}
    )
    definition = TextAreaField(
        validators=[DataRequired()],
        render_kw={"rows" : 3, "placeholder": "Definition"}
    )
    sentence = TextAreaField(
        validators=[DataRequired()],
        render_kw={"rows" : 3, "placeholder": "Example Sentence"}
    )
    submit = SubmitField(
        'Add Word',
        render_kw={"class": "btn-primary"}
    )