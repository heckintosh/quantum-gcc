from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_socketio import SocketIO, emit
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secretkey'
socketio = SocketIO(app)

MAX_USERNAME_LENGTH = 16  # define maximum username length

# Global dictionary mapping Socket.IO session IDs to usernames
active_users = {}

@app.route('/', methods=['GET', 'POST'])
def index():
    """
    Landing page where users enter a username.
    After a valid username is submitted, redirect to the partner selection screen.
    """
    if request.method == 'POST':
        username = request.form.get('username')
        if username:
            if len(username) > MAX_USERNAME_LENGTH:
                flash(f"Username must be at most {MAX_USERNAME_LENGTH} characters long.")
                return redirect(url_for('index'))
            else:
                session['username'] = username
                print(session['username'])
                # Clear any previously set chat target
                session.pop('target', None)
                return redirect(url_for('select'))
        else:
            flash("Username cannot be empty.")
            return redirect(url_for('index'))
    return render_template('index.html')

@app.route('/select')
def select():
    """
    Screen for selecting a chat partner.
    The active users (excluding yourself) are shown; you must select one to chat with.
    """
    if 'username' not in session:
        return redirect(url_for('index'))
    return render_template('select.html', username=session['username'])

@app.route('/set_target', methods=['POST'])
def set_target():
    """
    Receives the selected chat partner and stores it in the session.
    Redirects to the chat interface.
    """
    if 'username' not in session:
        return redirect(url_for('index'))
    target = request.form.get('target')
    if not target:
        flash("You must select a chat partner.")
        return redirect(url_for('select'))
    session['target'] = target
    return redirect(url_for('chat'))

@app.route('/chat')
def chat():
    """
    Chat page. Displays a header indicating a private chat with the chosen user.
    """
    if 'username' not in session or 'target' not in session:
        return redirect(url_for('index'))
    return render_template('chat.html', username=session['username'], target=session['target'])

def update_active_users():
    """Broadcast the list of active users to all connected clients."""
    users = list(active_users.values())
    socketio.emit('active_users', users)

@socketio.on('connect')
def handle_connect():
    username = session.get('username')
    if username:
        active_users[request.sid] = username
        update_active_users()

@socketio.on('disconnect')
def handle_disconnect():
    if request.sid in active_users:
        del active_users[request.sid]
        update_active_users()

@socketio.on('private_message')
def handle_private_message(data):
    """
    Expected data: {
      'target': 'target_username',
      'message': '...'
    }
    Sends the message only to the target user and echoes it to the sender.
    """
    target_username = data.get('target')
    message = data.get('message')
    sender_username = active_users.get(request.sid, 'Anonymous')
    timestamp = time.strftime('%I:%M %p')

    # Find the target user's Socket.IO session ID.
    target_sid = None
    for sid, user in active_users.items():
        if user == target_username:
            target_sid = sid
            break

    if target_sid:
        # Send the private message to the target client.
        emit('private_message', {
            'username': sender_username,
            'message': message,
            'timestamp': timestamp
        }, to=target_sid)
        # Also echo the message to the sender.
        emit('private_message', {
            'username': sender_username,
            'message': message,
            'timestamp': timestamp,
            'to': target_username
        }, to=request.sid)
    else:
        # Send an error back if the target is offline.
        emit('error_message', {'error': 'User not found or offline.'}, to=request.sid)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=12345, debug=True)
