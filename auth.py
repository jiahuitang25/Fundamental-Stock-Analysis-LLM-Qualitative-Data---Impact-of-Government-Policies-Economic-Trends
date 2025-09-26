"""
Authentication Blueprint for Stock Analysis Application
Handles user registration, login, logout, and session management
"""

import logging
import os
import requests
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, redirect, url_for, session, current_app
from flask import render_template_string
from flask_login import login_user, logout_user, login_required, current_user
from models import User
from flask_mail import Mail, Message

# Create authentication blueprint
auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

# Email configuration
mail = Mail()

# Google OAuth configuration
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')
GOOGLE_REDIRECT_URI = os.getenv('GOOGLE_REDIRECT_URI', 'http://localhost:5000/auth/google/callback')

def send_verification_email(user):
    """Send verification email to user"""
    try:
        token = user.generate_verification_token()
        if not token:
            return False
        
        verification_url = f"{request.host_url.rstrip('/')}/auth/verify-email?token={token}"
        
        msg = Message(
            'Verify Your Email - Stock Analysis Chatbot',
            sender=os.getenv('MAIL_DEFAULT_SENDER', 'noreply@stockanalysis.com'),
            recipients=[user.email]
        )
        
        msg.html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #2563eb;">Welcome to Stock Analysis Chatbot!</h2>
            <p>Hi {user.first_name or 'there'},</p>
            <p>Thank you for signing up! Please verify your email address by clicking the button below:</p>
            <div style="text-align: center; margin: 30px 0;">
                <a href="{verification_url}" 
                   style="background-color: #2563eb; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; display: inline-block;">
                    Verify Email Address
                </a>
            </div>
            <p>Or copy and paste this link into your browser:</p>
            <p style="word-break: break-all; color: #6b7280;">{verification_url}</p>
            <p>This link will expire in 24 hours.</p>
            <p>If you didn't create an account, you can safely ignore this email.</p>
            <br>
            <p>Best regards,<br>Stock Analysis Team</p>
        </div>
        """
        
        mail.send(msg)
        return True
    except Exception as e:
        logging.error(f"Error sending verification email: {e}")
        return False

@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    """User registration endpoint"""
    if request.method == 'GET':
        # Return signup form
        return render_template_string(SIGNUP_TEMPLATE)
    
    try:
        # Get form data
        data = request.get_json() if request.is_json else request.form
        
        email = data.get('email', '').strip()
        password = data.get('password', '')
        confirm_password = data.get('confirm_password', '')
        first_name = data.get('first_name', '').strip()
        last_name = data.get('last_name', '').strip()
        
        # Validation
        errors = []
        
        if not email:
            errors.append('Email is required')
        
        if not password:
            errors.append('Password is required')
        
        if password != confirm_password:
            errors.append('Passwords do not match')
        
        if errors:
            if request.is_json:
                return jsonify({'success': False, 'errors': errors}), 400
            else:
                return render_template_string(SIGNUP_TEMPLATE, 
                                            errors=errors, 
                                            email=email, 
                                            first_name=first_name, 
                                            last_name=last_name)
        
        # Create user
        result = User.create_user(email, password, first_name, last_name)
        
        if result['success']:
            user = result['user']
            
            # Send verification email
            if send_verification_email(user):
                logging.info(f"Verification email sent to: {email}")
                message = 'Account created successfully! Please check your email to verify your account.'
            else:
                logging.warning(f"Failed to send verification email to: {email}")
                message = 'Account created successfully! However, verification email could not be sent. Please contact support.'
            
            # Don't log in user until email is verified
            if request.is_json:
                return jsonify({
                    'success': True,
                    'message': message,
                    'user': user.to_dict(),
                    'redirect': '/auth/verify-email-sent'
                }), 201
            else:
                return redirect('/auth/verify-email-sent')
        else:
            if request.is_json:
                return jsonify({'success': False, 'errors': result['errors']}), 400
            else:
                return render_template_string(SIGNUP_TEMPLATE, 
                                            errors=result['errors'], 
                                            email=email, 
                                            first_name=first_name, 
                                            last_name=last_name)
                
    except Exception as e:
        logging.error(f"Signup error: {e}", exc_info=True)
        error_msg = 'An error occurred during registration'
        
        if request.is_json:
            return jsonify({'success': False, 'errors': [error_msg]}), 500
        else:
                            return render_template_string(SIGNUP_TEMPLATE, errors=[error_msg])

@auth_bp.route('/verify-email-sent', methods=['GET'])
def verify_email_sent():
    """Show email verification sent page"""
    return render_template_string(VERIFY_EMAIL_SENT_TEMPLATE)

@auth_bp.route('/verify-email', methods=['GET'])
def verify_email():
    """Verify email with token"""
    token = request.args.get('token')
    
    if not token:
        return render_template_string(VERIFY_EMAIL_ERROR_TEMPLATE, 
                                    error="Invalid verification link")
    
    try:
        # Find user by token
        from models import User
        user = User.get_by_verification_token(token)
        
        if not user:
            return render_template_string(VERIFY_EMAIL_ERROR_TEMPLATE, 
                                        error="Invalid or expired verification link")
        
        # Verify email
        if user.verify_email(token):
            # Log in user after successful verification
            login_user(user, remember=True)
            user.update_last_login()
            
            logging.info(f"Email verified for user: {user.email}")
            
            return render_template_string(VERIFY_EMAIL_SUCCESS_TEMPLATE, 
                                        user=user)
        else:
            return render_template_string(VERIFY_EMAIL_ERROR_TEMPLATE, 
                                        error="Verification failed. Please try again or contact support.")
    
    except Exception as e:
        logging.error(f"Email verification error: {e}")
        return render_template_string(VERIFY_EMAIL_ERROR_TEMPLATE, 
                                    error="An error occurred during verification")

@auth_bp.route('/resend-verification', methods=['POST'])
def resend_verification():
    """Resend verification email"""
    try:
        data = request.get_json()
        email = data.get('email', '').strip()
        
        if not email:
            return jsonify({'success': False, 'error': 'Email is required'}), 400
        
        user = User.get_by_email(email)
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        if user.email_verified:
            return jsonify({'success': False, 'error': 'Email already verified'}), 400
        
        # Send new verification email
        if send_verification_email(user):
            return jsonify({'success': True, 'message': 'Verification email sent'}), 200
        else:
            return jsonify({'success': False, 'error': 'Failed to send verification email'}), 500
    
    except Exception as e:
        logging.error(f"Resend verification error: {e}")
        return jsonify({'success': False, 'error': 'An error occurred'}), 500

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """User login endpoint"""
    if request.method == 'GET':
        # Return login form
        return render_template_string(LOGIN_TEMPLATE)
    
    try:
        # Get form data
        data = request.get_json() if request.is_json else request.form
        
        email = data.get('email', '').strip()
        password = data.get('password', '')
        remember = data.get('remember', False)
        
        # Validation
        if not email or not password:
            error_msg = 'Email and password are required'
            if request.is_json:
                return jsonify({'success': False, 'error': error_msg}), 400
            else:
                return render_template_string(LOGIN_TEMPLATE, error=error_msg, email=email)
        
        # Authenticate user
        user = User.authenticate(email, password)
        
        if user:
            login_user(user, remember=remember)
            
            logging.info(f"User logged in: {email}")
            
            # Get redirect URL from session or default to chatbot
            next_page = session.pop('next_page', '/chatbot')
            
            if request.is_json:
                return jsonify({
                    'success': True,
                    'message': 'Login successful',
                    'user': user.to_dict(),
                    'redirect': next_page
                }), 200
            else:
                return redirect(next_page)
        else:
            error_msg = 'Invalid email or password'
            if request.is_json:
                return jsonify({'success': False, 'error': error_msg}), 401
            else:
                return render_template_string(LOGIN_TEMPLATE, error=error_msg, email=email)
                
    except Exception as e:
        logging.error(f"Login error: {e}", exc_info=True)
        error_msg = 'An error occurred during login'
        
        if request.is_json:
            return jsonify({'success': False, 'error': error_msg}), 500
        else:
            return render_template_string(LOGIN_TEMPLATE, error=error_msg)

@auth_bp.route('/google/login', methods=['GET'])
def google_login():
    """Initiate Google OAuth login"""
    if not GOOGLE_CLIENT_ID:
        return jsonify({'error': 'Google OAuth not configured'}), 500
    
    # Store the intent in session to differentiate login vs signup
    session['oauth_intent'] = 'login'
    
    # Google OAuth URL
    google_auth_url = f"https://accounts.google.com/o/oauth2/v2/auth"
    params = {
        'client_id': GOOGLE_CLIENT_ID,
        'redirect_uri': GOOGLE_REDIRECT_URI,
        'scope': 'openid email profile',
        'response_type': 'code',
        'access_type': 'offline',
        'state': 'login'  # Add state parameter to track intent
    }
    
    auth_url = f"{google_auth_url}?{'&'.join([f'{k}={v}' for k, v in params.items()])}"
    return redirect(auth_url)

@auth_bp.route('/google/signup', methods=['GET'])
def google_signup():
    """Initiate Google OAuth signup"""
    if not GOOGLE_CLIENT_ID:
        return jsonify({'error': 'Google OAuth not configured'}), 500
    
    # Store the intent in session to differentiate login vs signup
    session['oauth_intent'] = 'signup'
    
    # Google OAuth URL
    google_auth_url = f"https://accounts.google.com/o/oauth2/v2/auth"
    params = {
        'client_id': GOOGLE_CLIENT_ID,
        'redirect_uri': GOOGLE_REDIRECT_URI,
        'scope': 'openid email profile',
        'response_type': 'code',
        'access_type': 'offline',
        'state': 'signup'  # Add state parameter to track intent
    }
    
    auth_url = f"{google_auth_url}?{'&'.join([f'{k}={v}' for k, v in params.items()])}"
    return redirect(auth_url)

@auth_bp.route('/google/callback', methods=['GET'])
def google_callback():
    """Handle Google OAuth callback"""
    try:
        code = request.args.get('code')
        error = request.args.get('error')
        state = request.args.get('state')  # Get the state parameter
        oauth_intent = session.get('oauth_intent', 'login')  # Get intent from session
        
        # Determine which template to use for errors
        error_template = SIGNUP_TEMPLATE if oauth_intent == 'signup' else LOGIN_TEMPLATE
        
        if error:
            logging.error(f"Google OAuth error: {error}")
            return render_template_string(error_template, 
                                        errors=[f"Google authentication failed: {error}"])
        
        if not code:
            logging.error("Google OAuth: No authorization code received")
            return render_template_string(error_template, 
                                        errors=["Google authentication failed: No authorization code"])
        
        logging.info(f"Google OAuth callback: intent={oauth_intent}, state={state}")
        
        # Exchange code for access token
        token_url = "https://oauth2.googleapis.com/token"
        token_data = {
            'client_id': GOOGLE_CLIENT_ID,
            'client_secret': GOOGLE_CLIENT_SECRET,
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': GOOGLE_REDIRECT_URI
        }
        
        logging.info("Exchanging authorization code for access token")
        token_response = requests.post(token_url, data=token_data)
        token_response.raise_for_status()
        token_info = token_response.json()
        
        # Get user info from Google
        user_info_url = "https://www.googleapis.com/oauth2/v2/userinfo"
        headers = {'Authorization': f"Bearer {token_info['access_token']}"}
        logging.info("Fetching user info from Google")
        user_response = requests.get(user_info_url, headers=headers)
        user_response.raise_for_status()
        user_info = user_response.json()
        
        # Extract user data
        google_id = user_info['id']
        email = user_info['email']
        first_name = user_info.get('given_name', '')
        last_name = user_info.get('family_name', '')
        
        logging.info(f"Google user info received: email={email}, name={first_name} {last_name}")
        
        # Create or get user
        result = User.create_google_user(google_id, email, first_name, last_name)
        
        if result['success']:
            user = result['user']
            
            # Log user details before login
            logging.info(f"Attempting to login user: {user.email}, ID: {user.id}, Active: {user.is_active()}")
            
            # Login user with Flask-Login
            login_success = login_user(user, remember=True)
            logging.info(f"Login user result: {login_success}")
            
            # Update last login
            user.update_last_login()
            
            # Force session to be permanent BEFORE checking
            session.permanent = True
            session.modified = True  # Explicitly mark session as modified
            
            # Verify session was created
            logging.info(f"Session user_id after login: {session.get('_user_id', 'NOT SET')}")
            logging.info(f"Current user authenticated: {current_user.is_authenticated if current_user else 'current_user is None'}")
            logging.info(f"Session permanent: {session.permanent}")
            logging.info(f"Session keys: {list(session.keys())}")
            
            # Clear the OAuth intent from session
            session.pop('oauth_intent', None)
            
            logging.info(f"Google user successfully authenticated: {email}")
            
            # Instead of redirecting, return the success page directly to avoid session loss
            # This eliminates any potential session cookie issues with redirects
            user_info = {
                'email': user.email,
                'name': user.full_name,
                'id': user.id,
                'verified': user.email_verified
            }
            
            success_html = f"""
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Login Successful</title>
                <script src="https://cdn.tailwindcss.com"></script>
            </head>
            <body class="min-h-screen bg-gradient-to-br from-green-50 to-blue-100 flex items-center justify-center">
                <div class="max-w-md w-full mx-4 bg-white rounded-2xl shadow-lg p-8 text-center">
                    <div class="text-6xl mb-4">✅</div>
                    <h1 class="text-2xl font-bold text-gray-900 mb-4">Login Successful!</h1>
                    <p class="text-gray-600 mb-6">Welcome, {user_info['name']}!</p>
                    
                    <div class="bg-green-50 border border-green-200 rounded-lg p-4 mb-6 text-left">
                        <h3 class="font-semibold text-green-800 mb-2">Account Details:</h3>
                        <p class="text-sm text-green-700">Email: {user_info['email']}</p>
                        <p class="text-sm text-green-700">ID: {user_info['id']}</p>
                        <p class="text-sm text-green-700">Verified: {'Yes' if user_info['verified'] else 'No'}</p>
                    </div>
                    
                    <div class="text-sm text-gray-500 mb-4">
                        Redirecting to chatbot in <span id="countdown">3</span> seconds...
                    </div>
                    
                    <button onclick="goToChatbot()" class="bg-blue-600 text-white px-6 py-3 rounded-lg hover:bg-blue-700 transition duration-200 w-full mb-2">
                        Go to Chatbot Now
                    </button>
                    
                    <button onclick="testSession()" class="bg-gray-500 text-white px-4 py-2 rounded-lg hover:bg-gray-600 transition duration-200 w-full text-sm">
                        Debug: Test Session
                    </button>
                    
                    <div id="debug-info" class="mt-4 p-2 bg-gray-100 rounded text-xs text-left hidden"></div>
                </div>
                
                <script>
                    let countdown = 3;
                    const countdownElement = document.getElementById('countdown');
                    
                    function goToChatbot() {{
                        window.location.href = '/chatbot';
                    }}
                    
                    async function testSession() {{
                        try {{
                            const response = await fetch('/auth/debug-session');
                            const data = await response.json();
                            const debugDiv = document.getElementById('debug-info');
                            debugDiv.classList.remove('hidden');
                            debugDiv.innerHTML = '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
                        }} catch (e) {{
                            console.error('Session test failed:', e);
                        }}
                    }}
                    
                    const timer = setInterval(() => {{
                        countdown--;
                        countdownElement.textContent = countdown;
                        
                        if (countdown <= 0) {{
                            clearInterval(timer);
                            goToChatbot();
                        }}
                    }}, 1000);
                </script>
            </body>
            </html>
            """
            
            return success_html
        else:
            logging.error(f"Failed to create/login Google user: {result['errors']}")
            return render_template_string(error_template, 
                                        errors=result['errors'])
    
    except requests.exceptions.RequestException as e:
        logging.error(f"Google OAuth network error: {e}")
        error_template = SIGNUP_TEMPLATE if session.get('oauth_intent') == 'signup' else LOGIN_TEMPLATE
        return render_template_string(error_template, 
                                    errors=["Network error during Google authentication. Please try again."])
    except Exception as e:
        logging.error(f"Google OAuth unexpected error: {e}", exc_info=True)
        error_template = SIGNUP_TEMPLATE if session.get('oauth_intent') == 'signup' else LOGIN_TEMPLATE
        return render_template_string(error_template, 
                                    errors=["Google authentication failed. Please try again."])

@auth_bp.route('/logout', methods=['GET', 'POST'])
@login_required
def logout():
    """User logout endpoint"""
    try:
        user_email = current_user.email if current_user.is_authenticated else 'Unknown'
        logout_user()
        session.clear()
        
        logging.info(f"User logged out: {user_email}")
        
        if request.is_json:
            return jsonify({
                'success': True,
                'message': 'Logged out successfully',
                'redirect': '/auth/login'
            }), 200
        else:
            return redirect('/auth/login')
            
    except Exception as e:
        logging.error(f"Logout error: {e}", exc_info=True)
        
        if request.is_json:
            return jsonify({'success': False, 'error': 'Logout failed'}), 500
        else:
            return redirect('/auth/login')

@auth_bp.route('/profile', methods=['GET'])
@login_required
def profile():
    """Get current user profile"""
    try:
        if request.is_json:
            return jsonify({
                'success': True,
                'user': current_user.to_dict()
            }), 200
        else:
            return render_template_string(PROFILE_TEMPLATE, user=current_user)
            
    except Exception as e:
        logging.error(f"Profile error: {e}", exc_info=True)
        
        if request.is_json:
            return jsonify({'success': False, 'error': 'Failed to load profile'}), 500
        else:
            return render_template_string(PROFILE_TEMPLATE, error='Failed to load profile')

@auth_bp.route('/profile/update', methods=['POST'])
@login_required
def update_profile():
    """Update user profile"""
    try:
        data = request.get_json() if request.is_json else request.form
        
        preferences = data.get('preferences', {})
        
        # Update user preferences
        success = current_user.update_preferences(preferences)
        
        if success:
            if request.is_json:
                return jsonify({
                    'success': True,
                    'message': 'Profile updated successfully',
                    'user': current_user.to_dict()
                }), 200
            else:
                return render_template_string(PROFILE_TEMPLATE, 
                                            user=current_user, 
                                            message='Profile updated successfully')
        else:
            error_msg = 'Failed to update profile'
            if request.is_json:
                return jsonify({'success': False, 'error': error_msg}), 500
            else:
                return render_template_string(PROFILE_TEMPLATE, 
                                            user=current_user, 
                                            error=error_msg)
                
    except Exception as e:
        logging.error(f"Profile update error: {e}", exc_info=True)
        error_msg = 'An error occurred while updating profile'
        
        if request.is_json:
            return jsonify({'success': False, 'error': error_msg}), 500
        else:
            return render_template_string(PROFILE_TEMPLATE, 
                                        user=current_user, 
                                        error=error_msg)

@auth_bp.route('/check', methods=['GET'])
def check_auth():
    """Check authentication status"""
    try:
        if current_user.is_authenticated:
            return jsonify({
                'authenticated': True,
                'user': current_user.to_dict()
            }), 200
        else:
            return jsonify({
                'authenticated': False,
                'user': None
            }), 200
            
    except Exception as e:
        logging.error(f"Auth check error: {e}", exc_info=True)
        return jsonify({
            'authenticated': False,
            'user': None,
            'error': 'Failed to check authentication'
        }), 500

@auth_bp.route('/test-login', methods=['GET'])
def test_login():
    """Serve test login page for debugging"""
    return render_template_string(TEST_LOGIN_TEMPLATE)

@auth_bp.route('/debug-session', methods=['GET'])
def debug_session():
    """Debug endpoint to check session and authentication status"""
    try:
        session_info = {
            'session_keys': list(session.keys()),
            'user_id': session.get('_user_id', 'NOT SET'),
            'permanent': session.permanent,
            'current_user_authenticated': current_user.is_authenticated if current_user else False,
            'current_user_id': current_user.id if current_user and current_user.is_authenticated else 'NOT SET',
            'current_user_email': current_user.email if current_user and current_user.is_authenticated else 'NOT SET'
        }
        
        return jsonify({
            'success': True,
            'session_info': session_info
        }), 200
        
    except Exception as e:
        logging.error(f"Debug session error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# Template strings for forms (will be replaced with proper template files later)
LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - Stock Analysis Chatbot</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .liquid-glass {
            background: rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border: 1px solid rgba(255, 255, 255, 0.2);
            box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.37);
        }
        
        /* Ensure Google buttons are clickable */
        .google-auth-button {
            position: relative !important;
            z-index: 100 !important;
            pointer-events: auto !important;
            cursor: pointer !important;
            display: block !important;
            text-decoration: none !important;
        }
        
        .google-auth-button:hover {
            background-color: #f9fafb !important;
            border-color: #d1d5db !important;
        }
        
        /* Debug styling to make button more visible */
        .google-auth-button:active {
            transform: translateY(1px);
        }
        
        /* Perfect alignment for Google button content */
        .google-auth-button {
            display: grid !important;
            grid-template-columns: auto 1fr !important;
            align-items: center !important;
            justify-items: center !important;
        }
        
        .google-auth-button svg {
            justify-self: start !important;
            align-self: center !important;
        }
        
        .google-auth-button span {
            justify-self: center !important;
            align-self: center !important;
            line-height: 1 !important;
        }
    </style>
</head>
<body class="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
    <div class="min-h-screen flex items-center justify-center py-12 px-4 sm:px-6 lg:px-8">
        <div class="max-w-md w-full space-y-8">
            <div class="liquid-glass rounded-2xl p-6">
                <div class="text-center">
                    <h2 class="text-3xl font-bold text-gray-900 mb-2">Welcome Back</h2>
                    <p class="text-gray-600">Sign in to your account</p>
                </div>

                {% if error %}
                <div class="mt-4 bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
                    {{ error }}
                </div>
                {% endif %}

                <form class="mt-6 space-y-4" id="loginForm">
                    <div>
                        <label for="email" class="block text-sm font-medium text-gray-700">Email address</label>
                        <input id="email" name="email" type="email" required 
                               value="{{ email or '' }}"
                               class="mt-1 appearance-none relative block w-full px-3 py-3 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-md focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 focus:z-10 sm:text-sm" 
                               placeholder="Enter your email">
                    </div>
                    
                    <div>
                        <label for="password" class="block text-sm font-medium text-gray-700">Password</label>
                        <input id="password" name="password" type="password" required 
                               class="mt-1 appearance-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-md focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 focus:z-10 sm:text-sm" 
                               placeholder="Enter your password">
                    </div>

                    <div class="flex items-center justify-between">
                        <div class="flex items-center">
                            <input id="remember" name="remember" type="checkbox" 
                                   class="h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-gray-300 rounded">
                            <label for="remember" class="ml-2 block text-sm text-gray-900">Remember me</label>
                        </div>
                    </div>

                    <!-- Error message container -->
                    <div id="loginError" class="hidden bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
                    </div>

                    <div>
                        <button type="submit" id="loginButton"
                                class="group relative w-full flex justify-center py-2 px-4 border border-transparent text-sm font-medium rounded-md text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 transition duration-150 ease-in-out disabled:bg-gray-400 disabled:cursor-not-allowed">
                            <span id="loginButtonText">Sign in</span>
                            <svg id="loginSpinner" class="hidden animate-spin ml-2 h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                            </svg>
                        </button>
                    </div>

                    <div class="text-center">
                        <p class="text-sm text-gray-600">
                            Don't have an account? 
                            <a href="/auth/signup" class="font-medium text-indigo-600 hover:text-indigo-500">Sign up</a>
                        </p>
                    </div>
                </form>
                
                <!-- Google Sign-In -->
                <div class="mt-4">
                    <div class="relative">
                        <div class="absolute inset-0 flex items-center">
                            <div class="w-full border-t border-gray-300" />
                        </div>
                        <div class="relative flex justify-center text-sm">
                            <span class="px-2 bg-white text-gray-500">Or continue with</span>
                        </div>
                    </div>
                    
                    <div class="mt-4 relative z-10">
                        <a href="/auth/google/login" 
                           class="google-auth-button w-full grid grid-cols-[auto_1fr] items-center justify-center px-4 py-2 border border-gray-300 rounded-md shadow-sm bg-white text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 transition duration-150 ease-in-out cursor-pointer block"
                           style="position:relative; z-index: 10; pointer-events: auto;">
                            <svg class="w-5 h-5 mr-3" viewBox="0 0 24 24">
                                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                                <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                            </svg>
                            <span class="text-center">Sign in with Google</span>
                        </a>
                        

                    </div>
                </div>
            </div>
        </div>
        
    <script>
        document.addEventListener('DOMContentLoaded', function() {
            const loginForm = document.getElementById('loginForm');
            const loginButton = document.getElementById('loginButton');
            const loginButtonText = document.getElementById('loginButtonText');
            const loginSpinner = document.getElementById('loginSpinner');
            const loginError = document.getElementById('loginError');
            
            loginForm.addEventListener('submit', async function(e) {
                e.preventDefault();
                
                // Show loading state
                loginButton.disabled = true;
                loginButtonText.textContent = 'Signing in...';
                loginSpinner.classList.remove('hidden');
                loginError.classList.add('hidden');
                
                // Get form data
                const email = document.getElementById('email').value;
                const password = document.getElementById('password').value;
                const remember = document.getElementById('remember').checked;
                
                try {
                    const response = await fetch('/auth/login', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        credentials: 'include',
                        body: JSON.stringify({
                            email: email,
                            password: password,
                            remember: remember
                        })
                    });
                    
                    const data = await response.json();
                    
                    if (response.ok && data.success) {
                        // Success - redirect to chatbot or specified page
                        window.location.href = data.redirect || '/chatbot';
                    } else {
                        // Show error
                        loginError.textContent = data.error || 'Login failed. Please try again.';
                        loginError.classList.remove('hidden');
                    }
                    
                } catch (error) {
                    console.error('Login error:', error);
                    loginError.textContent = 'Network error. Please check your connection and try again.';
                    loginError.classList.remove('hidden');
                } finally {
                    // Reset form state
                    loginButton.disabled = false;
                    loginButtonText.textContent = 'Sign in';
                    loginSpinner.classList.add('hidden');
                }
            });
        });
    </script>
    </body>
</html>
"""

SIGNUP_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sign Up - Stock Analysis Chatbot</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .liquid-glass {
            background: rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border: 1px solid rgba(255, 255, 255, 0.2);
            box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.37);
        }
        .requirement-met { color: #059669; }
        .requirement-unmet { color: #dc2626; }
        .requirement-pending { color: #6b7280; }
        
        /* Ensure Google buttons are clickable */
        .google-auth-button {
            position: relative !important;
            z-index: 100 !important;
            pointer-events: auto !important;
            cursor: pointer !important;
            display: block !important;
            text-decoration: none !important;
        }
        
        .google-auth-button:hover {
            background-color: #f9fafb !important;
            border-color: #d1d5db !important;
        }
        
        /* Debug styling to make button more visible */
        .google-auth-button:active {
            transform: translateY(1px);
        }
        
        /* Perfect alignment for Google button content */
        .google-auth-button {
            display: grid !important;
            grid-template-columns: auto 1fr !important;
            align-items: center !important;
            justify-items: center !important;
        }
        
        .google-auth-button svg {
            justify-self: start !important;
            align-self: center !important;
        }
        
        .google-auth-button span {
            justify-self: center !important;
            align-self: center !important;
            line-height: 1 !important;
        }
    </style>
</head>
<body class="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
    <div class="min-h-screen flex items-center justify-center py-12 px-4 sm:px-6 lg:px-8">
        <div class="max-w-md w-full space-y-8">
            <div class="liquid-glass rounded-2xl p-6">
                <div class="text-center">
                    <h2 class="text-3xl font-bold text-gray-900 mb-2">Create Account</h2>
                    <p class="text-gray-600">Join our stock analysis platform</p>
                </div>

                {% if errors %}
                <div class="mt-4 bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
                    <ul class="list-disc list-inside">
                        {% for error in errors %}
                        <li>{{ error }}</li>
                        {% endfor %}
                    </ul>
                </div>
                {% endif %}

                <form class="mt-6 space-y-4" id="signupForm">
                    <div class="grid grid-cols-2 gap-3">
                        <div>
                            <label for="first_name" class="block text-sm font-medium text-gray-700">First name</label>
                            <input id="first_name" name="first_name" type="text" 
                                   value="{{ first_name or '' }}"
                                   class="mt-1 appearance-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-md focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 focus:z-10 sm:text-sm" 
                                   placeholder="First name">
                        </div>
                        <div>
                            <label for="last_name" class="block text-sm font-medium text-gray-700">Last name</label>
                            <input id="last_name" name="last_name" type="text" 
                                   value="{{ last_name or '' }}"
                                   class="mt-1 appearance-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-md focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 focus:z-10 sm:text-sm" 
                                   placeholder="Last name">
                        </div>
                    </div>
                    
                    <div>
                        <label for="email" class="block text-sm font-medium text-gray-700">Email address</label>
                        <input id="email" name="email" type="email" required 
                               value="{{ email or '' }}"
                               class="mt-1 appearance-none relative block w-full px-3 py-3 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-md focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 focus:z-10 sm:text-sm" 
                               placeholder="Enter your email">
                    </div>
                    
                    <div>
                        <label for="password" class="block text-sm font-medium text-gray-700">Password</label>
                        <input id="password" name="password" type="password" required 
                               class="mt-1 appearance-none relative block w-full px-3 py-3 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-md focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 focus:z-10 sm:text-sm" 
                               placeholder="Create a strong password"
                               oninput="validatePassword(this.value)">
                        
                        <!-- Live Password Requirements - Compact Grid Layout -->
                        <div class="mt-2 grid grid-cols-2 gap-x-2 gap-y-1" id="passwordRequirements">
                            <div class="text-xs requirement-pending" id="req-length">
                                <span class="inline-block w-2 h-2 rounded-full bg-gray-300 mr-1"></span>
                                8+ characters
                            </div>
                            <div class="text-xs requirement-pending" id="req-uppercase">
                                <span class="inline-block w-2 h-2 rounded-full bg-gray-300 mr-1"></span>
                                Uppercase (A-Z)
                            </div>
                            <div class="text-xs requirement-pending" id="req-lowercase">
                                <span class="inline-block w-2 h-2 rounded-full bg-gray-300 mr-1"></span>
                                Lowercase (a-z)
                            </div>
                            <div class="text-xs requirement-pending" id="req-number">
                                <span class="inline-block w-2 h-2 rounded-full bg-gray-300 mr-1"></span>
                                Number (0-9)
                            </div>
                            <div class="text-xs requirement-pending col-span-2" id="req-special">
                                <span class="inline-block w-2 h-2 rounded-full bg-gray-300 mr-1"></span>
                                Special character (!@#$%^&*(),.?":{}|<>_)
                            </div>
                        </div>
                        
                        <!-- Requirements Not Met Warning -->
                        <div class="mt-2 hidden" id="requirementsWarning">
                            <p class="text-xs text-red-600 bg-red-50 border border-red-200 rounded px-2 py-1">
                                ⚠️ Password requirements not met
                            </p>
                        </div>
                    </div>

                    <div>
                        <label for="confirm_password" class="block text-sm font-medium text-gray-700">Confirm Password</label>
                        <input id="confirm_password" name="confirm_password" type="password" required 
                               class="mt-1 appearance-none relative block w-full px-3 py-3 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-md focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 focus:z-10 sm:text-sm" 
                               placeholder="Confirm your password"
                               oninput="validateConfirmPassword()">
                        
                        <!-- Password Match Indicator -->
                        <div class="mt-1 hidden" id="passwordMatch">
                            <p class="text-xs text-green-600 bg-green-50 border border-green-200 rounded px-2 py-1">
                                ✅ Passwords match
                            </p>
                        </div>
                        <div class="mt-1 hidden" id="passwordMismatch">
                            <p class="text-xs text-red-600 bg-red-50 border border-red-200 rounded px-2 py-1">
                                ❌ Passwords do not match
                            </p>
                        </div>
                    </div>

                    <!-- Error message container -->
                    <div id="signupError" class="hidden bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
                    </div>

                    <div>
                        <button type="submit" id="submitBtn"
                                class="group relative w-full flex justify-center py-2 px-4 border border-transparent text-sm font-medium rounded-md text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 transition duration-150 ease-in-out disabled:bg-gray-400 disabled:cursor-not-allowed">
                            <span id="submitButtonText">Create Account</span>
                            <svg id="submitSpinner" class="hidden animate-spin ml-2 h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                            </svg>
                        </button>
                    </div>

                    <div class="text-center">
                        <p class="text-sm text-gray-600">
                            Already have an account? 
                            <a href="/auth/login" class="font-medium text-indigo-600 hover:text-indigo-500">Sign in</a>
                        </p>
                    </div>
                </form>
                
                <!-- Google Sign-Up -->
                <div class="mt-4">
                    <div class="relative">
                        <div class="absolute inset-0 flex items-center">
                            <div class="w-full border-t border-gray-300" />
                        </div>
                        <div class="relative flex justify-center text-sm">
                            <span class="px-2 bg-white text-gray-500">Or continue with</span>
                        </div>
                    </div>
                    
                    <div class="mt-4 relative z-10">
                        <a href="/auth/google/signup" 
                           class="google-auth-button w-full grid grid-cols-[auto_1fr] items-center justify-center px-4 py-2 border border-gray-300 rounded-md shadow-sm bg-white text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 transition duration-150 ease-in-out cursor-pointer block"
                           style="position: relative; z-index: 10; pointer-events: auto;">
                            <svg class="w-5 h-5 mr-3" viewBox="0 0 24 24">
                                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                                <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                            </svg>
                            <span class="text-center">Sign up with Google</span>
                        </a>
                        

                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        function validatePassword(password) {
            const requirements = {
                length: password.length >= 8,
                uppercase: /[A-Z]/.test(password),
                lowercase: /[a-z]/.test(password),
                number: /[0-9]/.test(password),
                special: /[!@#$%^&*(),.?":{}|<>_]/.test(password)
            };
            
            // Update requirement indicators
            Object.keys(requirements).forEach(req => {
                const element = document.getElementById('req-' + req);
                const dot = element.querySelector('span');
                
                if (requirements[req]) {
                    element.className = 'text-xs requirement-met';
                    dot.className = 'inline-block w-2 h-2 rounded-full bg-green-500 mr-2';
                } else {
                    element.className = 'text-xs requirement-unmet';
                    dot.className = 'inline-block w-2 h-2 rounded-full bg-red-500 mr-2';
                }
            });
            
            // Show/hide requirements warning
            const allMet = Object.values(requirements).every(Boolean);
            const warning = document.getElementById('requirementsWarning');
            if (allMet) {
                warning.classList.add('hidden');
            } else {
                warning.classList.remove('hidden');
            }
            
            // Validate confirm password
            validateConfirmPassword();
            
            // Update submit button state
            updateSubmitButton();
        }
        
        function validateConfirmPassword() {
            const password = document.getElementById('password').value;
            const confirmPassword = document.getElementById('confirm_password').value;
            const matchIndicator = document.getElementById('passwordMatch');
            const mismatchIndicator = document.getElementById('passwordMismatch');
            
            if (confirmPassword === '') {
                matchIndicator.classList.add('hidden');
                mismatchIndicator.classList.add('hidden');
                return;
            }
            
            if (password === confirmPassword) {
                matchIndicator.classList.remove('hidden');
                mismatchIndicator.classList.add('hidden');
            } else {
                matchIndicator.classList.add('hidden');
                mismatchIndicator.classList.remove('hidden');
            }
            
            updateSubmitButton();
        }
        
        function updateSubmitButton() {
            const password = document.getElementById('password').value;
            const confirmPassword = document.getElementById('confirm_password').value;
            const submitBtn = document.getElementById('submitBtn');
            
            // Check if all requirements are met
            const requirements = {
                length: password.length >= 8,
                uppercase: /[A-Z]/.test(password),
                lowercase: /[a-z]/.test(password),
                number: /[0-9]/.test(password),
                special: /[!@#$%^&*(),.?":{}|<>_]/.test(password)
            };
            
            const allRequirementsMet = Object.values(requirements).every(Boolean);
            const passwordsMatch = password === confirmPassword && password !== '';
            
            if (allRequirementsMet && passwordsMatch) {
                submitBtn.disabled = false;
                submitBtn.className = submitBtn.className.replace('disabled:bg-gray-400 disabled:cursor-not-allowed', '');
            } else {
                submitBtn.disabled = true;
                submitBtn.className += ' disabled:bg-gray-400 disabled:cursor-not-allowed';
            }
        }
        
        // Initialize validation on page load
        document.addEventListener('DOMContentLoaded', function() {
            updateSubmitButton();
            
            // Add signup form submission handler
            const signupForm = document.getElementById('signupForm');
            const submitBtn = document.getElementById('submitBtn');
            const submitButtonText = document.getElementById('submitButtonText');
            const submitSpinner = document.getElementById('submitSpinner');
            const signupError = document.getElementById('signupError');
            
            if (signupForm) {
                signupForm.addEventListener('submit', async function(e) {
                    e.preventDefault();
                    
                    // Show loading state
                    submitBtn.disabled = true;
                    submitButtonText.textContent = 'Creating Account...';
                    submitSpinner.classList.remove('hidden');
                    signupError.classList.add('hidden');
                    
                    // Get form data
                    const email = document.getElementById('email').value;
                    const password = document.getElementById('password').value;
                    const confirmPassword = document.getElementById('confirm_password').value;
                    const firstName = document.getElementById('first_name').value;
                    const lastName = document.getElementById('last_name').value;
                    
                    try {
                        const response = await fetch('/auth/signup', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                            },
                            credentials: 'include',
                            body: JSON.stringify({
                                email: email,
                                password: password,
                                confirm_password: confirmPassword,
                                first_name: firstName,
                                last_name: lastName
                            })
                        });
                        
                        const data = await response.json();
                        
                        if (response.ok && data.success) {
                            // Success - redirect to verification page
                            window.location.href = data.redirect || '/auth/verify-email-sent';
                        } else {
                            // Show errors
                            const errors = data.errors || [data.error || 'Signup failed. Please try again.'];
                            signupError.innerHTML = errors.map(error => `<div>${error}</div>`).join('');
                            signupError.classList.remove('hidden');
                        }
                        
                    } catch (error) {
                        console.error('Signup error:', error);
                        signupError.textContent = 'Network error. Please check your connection and try again.';
                        signupError.classList.remove('hidden');
                    } finally {
                        // Reset form state
                        submitBtn.disabled = false;
                        submitButtonText.textContent = 'Create Account';
                        submitSpinner.classList.add('hidden');
                    }
                });
            }
        });
    </script>
</body>
</html>
"""

# Email verification templates
VERIFY_EMAIL_SENT_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Verify Your Email - Stock Analysis Chatbot</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .liquid-glass {
            background: rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border: 1px solid rgba(255, 255, 255, 0.2);
            box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.37);
        }
    </style>
</head>
<body class="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
    <div class="min-h-screen flex items-center justify-center py-12 px-4 sm:px-6 lg:px-8">
        <div class="max-w-md w-full space-y-8">
            <div class="liquid-glass rounded-2xl p-8 text-center">
                <div class="text-6xl mb-4">📧</div>
                <h2 class="text-3xl font-bold text-gray-900 mb-4">Check Your Email</h2>
                <p class="text-gray-600 mb-6">
                    We've sent a verification link to your email address. 
                    Please check your inbox and click the verification button.
                </p>
                
                <div class="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
                    <p class="text-sm text-blue-800">
                        <strong>Note:</strong> The verification link will expire in 24 hours.
                    </p>
                </div>
                
                <div class="space-y-4">
                    <a href="/auth/login" 
                       class="w-full flex justify-center py-3 px-4 border border-transparent text-sm font-medium rounded-md text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 transition duration-150 ease-in-out">
                        Back to Login
                    </a>
                    
                    <button onclick="resendVerification()" 
                            class="w-full flex justify-center py-3 px-4 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-500 transition duration-150 ease-in-out">
                        Resend Verification Email
                    </button>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        function resendVerification() {
            // Get email from URL or prompt user
            const email = prompt('Please enter your email address:');
            if (!email) return;
            
            fetch('/auth/resend-verification', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: email })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    alert('Verification email sent! Please check your inbox.');
                } else {
                    alert('Error: ' + data.error);
                }
            })
            .catch(error => {
                alert('Error sending verification email. Please try again.');
            });
        }
    </script>
</body>
</html>
"""

VERIFY_EMAIL_SUCCESS_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Email Verified - Stock Analysis Chatbot</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .liquid-glass {
            background: rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border: 1px solid rgba(255, 255, 255, 0.2);
            box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.37);
        }
    </style>
</head>
<body class="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
    <div class="min-h-screen flex items-center justify-center py-12 px-4 sm:px-6 lg:px-8">
        <div class="max-w-md w-full space-y-8">
            <div class="liquid-glass rounded-2xl p-8 text-center">
                <div class="text-6xl mb-4 text-green-500">✅</div>
                <h2 class="text-3xl font-bold text-gray-900 mb-4">Email Verified!</h2>
                <p class="text-gray-600 mb-6">
                    Congratulations! Your email has been successfully verified. 
                    You're now logged in and ready to use the Stock Analysis Chatbot.
                </p>
                
                <div class="bg-green-50 border border-green-200 rounded-lg p-4 mb-6">
                    <p class="text-sm text-green-800">
                        Welcome, <strong>{{ user.first_name or 'User' }}</strong>!
                    </p>
                </div>
                
                <a href="/chatbot" 
                   class="w-full flex justify-center py-3 px-4 border border-transparent text-sm font-medium rounded-md text-white bg-green-600 hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500 transition duration-150 ease-in-out">
                    Go to Chatbot
                </a>
            </div>
        </div>
    </div>
</body>
</html>
"""

VERIFY_EMAIL_ERROR_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Verification Error - Stock Analysis Chatbot</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .liquid-glass {
            background: rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border: 1px solid rgba(255, 255, 255, 0.2);
            box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.37);
        }
    </style>
</head>
<body class="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
    <div class="min-h-screen flex items-center justify-center py-12 px-4 sm:px-6 lg:px-8">
        <div class="max-w-md w-full space-y-8">
            <div class="liquid-glass rounded-2xl p-8 text-center">
                <div class="text-6xl mb-4 text-red-500">❌</div>
                <h2 class="text-2xl font-bold text-gray-900 mb-4">Verification Failed</h2>
                <p class="text-gray-600 mb-6">
                    {{ error }}
                </p>
                
                <div class="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
                    <p class="text-sm text-red-800">
                        <strong>What to do:</strong><br>
                        • Check if the link is still valid (24 hours)<br>
                        • Try signing up again<br>
                        • Contact support if the problem persists
                    </p>
                </div>
                
                <div class="space-y-4">
                    <a href="/auth/signup" 
                       class="w-full flex justify-center py-3 px-4 border border-transparent text-sm font-medium rounded-md text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 transition duration-150 ease-in-out">
                        Sign Up Again
                    </a>
                    
                    <a href="/auth/login" 
                       class="w-full flex justify-center py-3 px-4 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-500 transition duration-150 ease-in-out">
                        Back to Login
                    </a>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
"""

PROFILE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Profile - Stock Analysis Chatbot</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
    <div class="min-h-screen py-12 px-4 sm:px-6 lg:px-8">
        <div class="max-w-2xl mx-auto">
            <div class="bg-white rounded-2xl shadow-lg p-8">
                <div class="text-center mb-8">
                    <h1 class="text-3xl font-bold text-gray-900">User Profile</h1>
                </div>

                {% if message %}
                <div class="mb-4 bg-green-100 border border-green-400 text-green-700 px-4 py-3 rounded">
                    {{ message }}
                </div>
                {% endif %}

                {% if error %}
                <div class="mb-4 bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
                    {{ error }}
                </div>
                {% endif %}

                <div class="space-y-6">
                    <div>
                        <label class="block text-sm font-medium text-gray-700">Email</label>
                        <p class="mt-1 text-lg text-gray-900">{{ user.email }}</p>
                    </div>
                    
                    <div>
                        <label class="block text-sm font-medium text-gray-700">Name</label>
                        <p class="mt-1 text-lg text-gray-900">{{ user.full_name or 'Not provided' }}</p>
                    </div>
                    
                    <div>
                        <label class="block text-sm font-medium text-gray-700">Member Since</label>
                        <p class="mt-1 text-lg text-gray-900">{{ user.created_at.strftime('%B %d, %Y') if user.created_at else 'Unknown' }}</p>
                    </div>
                    
                    <div>
                        <label class="block text-sm font-medium text-gray-700">Last Login</label>
                        <p class="mt-1 text-lg text-gray-900">{{ user.last_login.strftime('%B %d, %Y at %I:%M %p') if user.last_login else 'First time login' }}</p>
                    </div>
                    
                    <!-- Notification Settings -->
                    <div class="border-t pt-6">
                        <h3 class="text-lg font-medium text-gray-900 mb-4">Notification Settings</h3>
                        <div class="flex items-center justify-between">
                            <div>
                                <label class="block text-sm font-medium text-gray-700">Email Notifications</label>
                                <p class="text-sm text-gray-500">Receive news updates and analysis alerts</p>
                            </div>
                            <div class="flex items-center">
                                <button id="notificationToggle" 
                                        class="relative inline-flex h-6 w-11 items-center rounded-full bg-indigo-600 transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
                                        onclick="toggleNotification()">
                                    <span id="toggleThumb" 
                                          class="inline-block h-4 w-4 transform rounded-full bg-white transition-transform translate-x-6"></span>
                                </button>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="mt-8 flex justify-center space-x-4">
                    <a href="/chatbot" 
                       class="px-6 py-3 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 transition duration-150">
                        Go to Chatbot
                    </a>
                    <a href="/watchlist.html" 
                       class="px-6 py-3 bg-green-600 text-white rounded-md hover:bg-green-700 transition duration-150">
                        View Watchlist
                    </a>
                    <a href="/auth/logout" 
                       class="px-6 py-3 bg-gray-600 text-white rounded-md hover:bg-gray-700 transition duration-150">
                        Logout
                    </a>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        // Initialize notification toggle state (enabled by default)
        let notificationEnabled = true;
        
        function toggleNotification() {
            notificationEnabled = !notificationEnabled;
            const toggle = document.getElementById('notificationToggle');
            const thumb = document.getElementById('toggleThumb');
            
            if (notificationEnabled) {
                toggle.classList.remove('bg-gray-200');
                toggle.classList.add('bg-indigo-600');
                thumb.classList.remove('translate-x-1');
                thumb.classList.add('translate-x-6');
            } else {
                toggle.classList.remove('bg-indigo-600');
                toggle.classList.add('bg-gray-200');
                thumb.classList.remove('translate-x-6');
                thumb.classList.add('translate-x-1');
            }
            
            // Show feedback to user (no backend connection as requested)
            const status = notificationEnabled ? 'enabled' : 'disabled';
            console.log(`Email notifications ${status}`);
            
            // Optional: Show a temporary message
            showNotificationStatus(status);
        }
        
        function showNotificationStatus(status) {
            // Create a temporary status message
            const message = document.createElement('div');
            message.className = `fixed top-4 right-4 px-4 py-2 rounded-md text-white text-sm z-50 ${
                status === 'enabled' ? 'bg-green-500' : 'bg-gray-500'
            }`;
            message.textContent = `Notifications ${status}`;
            
            document.body.appendChild(message);
            
            // Remove message after 2 seconds
            setTimeout(() => {
                if (message.parentNode) {
                    message.parentNode.removeChild(message);
                }
            }, 2000);
        }
        
        // Initialize the toggle on page load
        document.addEventListener('DOMContentLoaded', function() {
            // Toggle starts enabled by default
            const toggle = document.getElementById('notificationToggle');
            const thumb = document.getElementById('toggleThumb');
            
            toggle.classList.add('bg-indigo-600');
            thumb.classList.add('translate-x-6');
        });
    </script>
</body>
</html>
"""

TEST_LOGIN_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Test Login - Debug</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
    <div class="min-h-screen flex items-center justify-center py-12 px-4 sm:px-6 lg:px-8">
        <div class="max-w-md w-full space-y-8">
            <div class="bg-white rounded-2xl shadow-lg p-6">
                <div class="text-center">
                    <h2 class="text-3xl font-bold text-gray-900 mb-2">Test Login</h2>
                    <p class="text-gray-600">Debug version with console logging</p>
                </div>

                <div id="debugInfo" class="bg-gray-100 border border-gray-300 text-gray-700 px-4 py-3 rounded text-sm mb-4">
                    <strong>Debug Info:</strong>
                    <div id="debugLog">Ready to test...</div>
                </div>

                <form class="mt-6 space-y-4" id="loginForm">
                    <div>
                        <label for="email" class="block text-sm font-medium text-gray-700">Email</label>
                        <input id="email" name="email" type="email" required 
                               value="jiahuitang25@1utar.my"
                               class="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500">
                    </div>
                    
                    <div>
                        <label for="password" class="block text-sm font-medium text-gray-700">Password</label>
                        <input id="password" name="password" type="password" required 
                               value="TestPassword123!"
                               class="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500">
                    </div>

                    <div id="loginError" class="hidden bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded"></div>

                    <div>
                        <button type="submit" id="loginButton"
                                class="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500">
                            <span id="loginButtonText">Sign in</span>
                        </button>
                    </div>
                </form>
            </div>
        </div>
    </div>
    
    <script>
        function addDebugLog(message) {
            const debugLog = document.getElementById("debugLog");
            const timestamp = new Date().toLocaleTimeString();
            debugLog.innerHTML += "<br>[" + timestamp + "] " + message;
            console.log("[LOGIN DEBUG] " + message);
        }
        
        addDebugLog("Script loaded successfully");
        
        document.addEventListener("DOMContentLoaded", function() {
            addDebugLog("DOM Content Loaded");
            
            const loginForm = document.getElementById("loginForm");
            const loginButton = document.getElementById("loginButton");
            const loginButtonText = document.getElementById("loginButtonText");
            const loginError = document.getElementById("loginError");
            
            if (!loginForm) {
                addDebugLog("ERROR: loginForm not found!");
                return;
            }
            
            addDebugLog("Form found, adding event listener");
            
            loginForm.addEventListener("submit", async function(e) {
                addDebugLog("Form submitted - preventing default");
                e.preventDefault();
                
                loginButton.disabled = true;
                loginButtonText.textContent = "Signing in...";
                loginError.classList.add("hidden");
                
                const email = document.getElementById("email").value;
                const password = document.getElementById("password").value;
                
                addDebugLog("Email: " + email + ", Password: [" + password.length + " chars]");
                
                try {
                    addDebugLog("Sending fetch request to /auth/login");
                    
                    const response = await fetch("/auth/login", {
                        method: "POST",
                        headers: {
                            "Content-Type": "application/json",
                        },
                        credentials: "include",
                        body: JSON.stringify({
                            email: email,
                            password: password,
                            remember: false
                        })
                    });
                    
                    addDebugLog("Response status: " + response.status);
                    
                    const data = await response.json();
                    addDebugLog("Response data: " + JSON.stringify(data));
                    
                    if (response.ok && data.success) {
                        addDebugLog("Login successful! Redirecting to: " + data.redirect);
                        setTimeout(function() {
                            window.location.href = data.redirect || "/chatbot";
                        }, 2000);
                    } else {
                        const errorMsg = data.error || "Login failed. Please try again.";
                        addDebugLog("Login failed: " + errorMsg);
                        loginError.textContent = errorMsg;
                        loginError.classList.remove("hidden");
                    }
                    
                } catch (error) {
                    addDebugLog("Network error: " + error.message);
                    loginError.textContent = "Network error. Please check your connection and try again.";
                    loginError.classList.remove("hidden");
                } finally {
                    loginButton.disabled = false;
                    loginButtonText.textContent = "Sign in";
                    addDebugLog("Form state reset");
                }
            });
            
            addDebugLog("Event listener attached successfully");
        });
        
        setTimeout(function() {
            addDebugLog("Timer test: JavaScript is working properly");
        }, 1000);
    </script>
</body>
</html>
"""
