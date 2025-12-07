from flask import Flask, render_template
from werkzeug.security import generate_password_hash, check_password_hash
from forms import LoginForm, SignupForm, AddWordForm

app = Flask(__name__)
app.config['SECRET_KEY'] = 'FinalProjectACP'

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/login')
def login():
    form = LoginForm()
    return render_template('login.html',form=form)

@app.route('/signup')
def  signup():
    form = SignupForm()
    return render_template('signup.html',form=form)

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
def profile():
    return render_template('profile.html')

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
    app.run(debug=True)