import os
import sys
from flask import Flask, redirect, url_for, session, render_template, request, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import requests
from urllib.parse import urlencode
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Configuration - ADD CHECKS HERE
SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-me')
GITHUB_CLIENT_ID = os.getenv('GITHUB_CLIENT_ID')
GITHUB_CLIENT_SECRET = os.getenv('GITHUB_CLIENT_SECRET')
BASE_URL = "http://192.168.56.101:5000"

# PRINT CONFIG AT STARTUP
print("=" * 50, file=sys.stderr, flush=True)
print(f"DEBUG STARTUP:", file=sys.stderr, flush=True)
print(f"  GITHUB_CLIENT_ID: '{GITHUB_CLIENT_ID}'", file=sys.stderr, flush=True)
print(f"  GITHUB_CLIENT_SECRET: '{GITHUB_CLIENT_SECRET}'", file=sys.stderr, flush=True)
print(f"  SECRET_KEY: '{SECRET_KEY}'", file=sys.stderr, flush=True)
print(f"  BASE_URL: '{BASE_URL}'", file=sys.stderr, flush=True)
print("=" * 50, file=sys.stderr, flush=True)

# VALIDATE CONFIG
if not GITHUB_CLIENT_ID or GITHUB_CLIENT_ID.strip() == "":
    print("CRITICAL ERROR: GITHUB_CLIENT_ID is empty or not set!", file=sys.stderr, flush=True)
    print("Please check your .env file", file=sys.stderr, flush=True)

if not GITHUB_CLIENT_SECRET or GITHUB_CLIENT_SECRET.strip() == "":
    print("CRITICAL ERROR: GITHUB_CLIENT_SECRET is empty or not set!", file=sys.stderr, flush=True)
    print("Please check your .env file", file=sys.stderr, flush=True)

app.secret_key = SECRET_KEY

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id_, name, email, avatar, provider, access_token):
        self.id = id_
        self.name = name
        self.email = email
        self.avatar = avatar
        self.provider = provider
        self.access_token = access_token
    
    def get_id(self):
        return f"{self.provider}_{self.id}"

users = {}

@login_manager.user_loader
def load_user(user_id):
    return users.get(user_id)

@app.route('/')
def index():
    return render_template('index.html', user=current_user)

@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.route('/login')
def login():
    """Redirect to GitHub OAuth"""
    print(f"DEBUG /login: GITHUB_CLIENT_ID = '{GITHUB_CLIENT_ID}'", file=sys.stderr, flush=True)
    
    if not GITHUB_CLIENT_ID or GITHUB_CLIENT_ID.strip() == "":
        flash("GitHub OAuth is not configured properly. Missing Client ID.", "danger")
        return redirect(url_for('index'))
    
    params = {
        'client_id': GITHUB_CLIENT_ID,
        'redirect_uri': f"{BASE_URL}/auth/github/callback",
        'scope': 'user:email',
        'allow_signup': 'true'
    }
    
    auth_url = f"https://github.com/login/oauth/authorize?{urlencode(params)}"
    print(f"DEBUG /login: Redirecting to {auth_url}", file=sys.stderr, flush=True)
    return redirect(auth_url)

@app.route('/auth/github/callback')
def github_callback():
    """Handle GitHub OAuth callback"""
    code = request.args.get('code')
    error = request.args.get('error')
    
    print(f"DEBUG /callback: START", file=sys.stderr, flush=True)
    print(f"DEBUG /callback: Code = {code}", file=sys.stderr, flush=True)
    print(f"DEBUG /callback: Error = {error}", file=sys.stderr, flush=True)
    print(f"DEBUG /callback: GITHUB_CLIENT_ID = '{GITHUB_CLIENT_ID}'", file=sys.stderr, flush=True)
    print(f"DEBUG /callback: GITHUB_CLIENT_SECRET = '{GITHUB_CLIENT_SECRET}'", file=sys.stderr, flush=True)
    
    if error:
        flash(f"GitHub authorization error: {error}", "danger")
        return redirect(url_for('index'))
    
    if not code:
        flash("No authorization code received from GitHub", "danger")
        return redirect(url_for('index'))
    
    # Check if credentials are set
    if not GITHUB_CLIENT_ID or not GITHUB_CLIENT_SECRET:
        print(f"DEBUG /callback: CREDENTIALS MISSING!", file=sys.stderr, flush=True)
        flash("GitHub OAuth credentials are not configured. Please check .env file.", "danger")
        return redirect(url_for('index'))
    
    try:
        print(f"DEBUG /callback: Step 1 - Requesting access token...", file=sys.stderr, flush=True)
        
        # Exchange code for access token
        token_url = "https://github.com/login/oauth/access_token"
        token_data = {
            'client_id': GITHUB_CLIENT_ID,
            'client_secret': GITHUB_CLIENT_SECRET,
            'code': code,
            'redirect_uri': f"{BASE_URL}/auth/github/callback"
        }
        
        token_headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        
        print(f"DEBUG /callback: Sending POST to {token_url}", file=sys.stderr, flush=True)
        print(f"DEBUG /callback: Data: {token_data}", file=sys.stderr, flush=True)
        
        response = requests.post(token_url, json=token_data, headers=token_headers, timeout=10)
        print(f"DEBUG /callback: Response status: {response.status_code}", file=sys.stderr, flush=True)
        print(f"DEBUG /callback: Response text: {response.text}", file=sys.stderr, flush=True)
        
        if response.status_code != 200:
            print(f"DEBUG /callback: Bad status code: {response.status_code}", file=sys.stderr, flush=True)
            flash(f"GitHub returned error {response.status_code}", "danger")
            return redirect(url_for('index'))
        
        response_data = response.json()
        print(f"DEBUG /callback: Response JSON: {response_data}", file=sys.stderr, flush=True)
        
        if 'error' in response_data:
            error_msg = response_data.get('error_description', response_data['error'])
            print(f"DEBUG /callback: GitHub API error: {error_msg}", file=sys.stderr, flush=True)
            flash(f"GitHub error: {error_msg}", "danger")
            return redirect(url_for('index'))
        
        access_token = response_data.get('access_token')
        
        if not access_token:
            print(f"DEBUG /callback: No access_token in response!", file=sys.stderr, flush=True)
            flash("Failed to get access token from GitHub", "danger")
            return redirect(url_for('index'))
        
        print(f"DEBUG /callback: Success! Got access token: {access_token[:20]}...", file=sys.stderr, flush=True)
        
        # Get user info
        print(f"DEBUG /callback: Step 2 - Getting user info...", file=sys.stderr, flush=True)
        user_headers = {
            'Authorization': f'token {access_token}',
            'Accept': 'application/json'
        }
        
        user_response = requests.get('https://api.github.com/user', headers=user_headers, timeout=10)
        print(f"DEBUG /callback: User response status: {user_response.status_code}", file=sys.stderr, flush=True)
        
        if user_response.status_code != 200:
            print(f"DEBUG /callback: Failed to get user info: {user_response.text}", file=sys.stderr, flush=True)
            flash("Failed to get user information from GitHub", "danger")
            return redirect(url_for('index'))
        
        user_data = user_response.json()
        print(f"DEBUG /callback: User data: {user_data}", file=sys.stderr, flush=True)
        
        # Get email
        email_response = requests.get('https://api.github.com/user/emails', headers=user_headers, timeout=10)
        email_data = email_response.json() if email_response.status_code == 200 else []
        
        primary_email = None
        for email in email_data:
            if email.get('primary') and email.get('verified'):
                primary_email = email.get('email')
                break
        
        if not primary_email:
            primary_email = user_data.get('email') or f"{user_data.get('login')}@github.com"
        
        # Create user
        user_id = str(user_data['id'])
        user_key = f"github_{user_id}"
        
        user = User(
            id_=user_id,
            name=user_data.get('name') or user_data.get('login'),
            email=primary_email,
            avatar=user_data.get('avatar_url'),
            provider='github',
            access_token=access_token
        )
        
        users[user_key] = user
        login_user(user, remember=True)
        
        print(f"DEBUG /callback: User logged in successfully: {user.name}", file=sys.stderr, flush=True)
        flash(f"Welcome {user.name}!", "success")
        return redirect(url_for('dashboard'))
        
    except requests.exceptions.RequestException as e:
        print(f"DEBUG /callback: Network error: {str(e)}", file=sys.stderr, flush=True)
        flash(f"Network error: {str(e)}", "danger")
        return redirect(url_for('index'))
    except Exception as e:
        print(f"DEBUG /callback: Unexpected error: {str(e)}", file=sys.stderr, flush=True)
        import traceback
        traceback.print_exc(file=sys.stderr)
        flash(f"Authentication error: {str(e)}", "danger")
        return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', user=current_user)

@app.route('/logout')
@login_required
def logout():
    user_key = f"{current_user.provider}_{current_user.id}"
    if user_key in users:
        del users[user_key]
    
    logout_user()
    flash("Logged out successfully", "info")
    return redirect(url_for('index'))

if __name__ == '__main__':
    print("Starting Flask app...", file=sys.stderr, flush=True)
    app.run(host='0.0.0.0', port=5000, debug=True)
