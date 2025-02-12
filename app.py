from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_socketio import SocketIO, emit
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secretkey'
socketio = SocketIO(app)

MAX_USERNAME_LENGTH = 16

# Global dictionary mapping Socket.IO session IDs to usernames
active_users = {}

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        username = request.form.get('username')
        if username:
            if len(username) > MAX_USERNAME_LENGTH:
                flash(f"Username must be at most {MAX_USERNAME_LENGTH} characters long.")
                return redirect(url_for('index'))
            else:
                session['username'] = username
                session.pop('target', None)
                return redirect(url_for('select'))
        else:
            flash("Username cannot be empty.")
            return redirect(url_for('index'))
    return render_template('index.html')

@app.route('/select')
def select():
    if 'username' not in session:
        return redirect(url_for('index'))
    return render_template('select.html', username=session['username'])

@app.route('/set_target', methods=['POST'])
def set_target():
    """
    A chooses B from the user list.
    - Store B in session['target']
    - Send a 'chat_request' socket event to B so B can accept/decline
    - Redirect A to a "waiting" page instead of /chat
    """
    if 'username' not in session:
        return redirect(url_for('index'))
    target = request.form.get('target')
    if not target:
        flash("You must select a chat partner.")
        return redirect(url_for('select'))

    session['target'] = target

    # Find target's Socket.IO session ID
    target_sid = None
    for sid, user in active_users.items():
        if user == target:
            target_sid = sid
            break

    # Notify B that A wants to chat
    if target_sid:
        socketio.emit('chat_request', {'from': session['username']}, to=target_sid)

    # Instead of going directly to /chat, go to a "waiting" page
    return redirect(url_for('waiting'))

@app.route('/waiting')
def waiting():
    """
    Show a waiting page to A while B decides to accept or decline.
    """
    if 'username' not in session or 'target' not in session:
        return redirect(url_for('index'))
    return render_template(
        'waiting.html',
        username=session['username'],
        target=session['target']
    )

@app.route('/cancel_request', methods=['POST'])
def cancel_request():
    """
    A calls this to cancel the outgoing request before it's accepted/declined.
    - Tells B "request_canceled" so B won't bother accepting.
    - Clears A's target and returns to select page.
    """
    if 'username' not in session or 'target' not in session:
        return redirect(url_for('index'))

    target = session['target']
    username = session['username']

    # Find target's sid
    target_sid = None
    for sid, user in active_users.items():
        if user == target:
            target_sid = sid
            break

    # Notify B that A canceled
    if target_sid:
        socketio.emit('request_canceled', {'canceler': username}, to=target_sid)

    # Clear A's target
    session.pop('target', None)
    flash("Chat request canceled.")
    return redirect(url_for('select'))

@app.route('/accept_request', methods=['POST'])
def accept_request():
    if 'username' not in session:
        return redirect(url_for('index'))

    requester = request.form.get('requester')
    if not requester:
        flash("No requester provided.")
        return redirect(url_for('select'))

    # B sets session['target'] to A
    session['target'] = requester

    # Notify A that B accepted
    requester_sid = None
    for sid, user in active_users.items():
        if user == requester:
            requester_sid = sid
            break
    if requester_sid:
        socketio.emit('chat_accepted', {'accepter': session['username']}, to=requester_sid)

    return redirect(url_for('chat'))

@app.route('/decline_request', methods=['POST'])
def decline_request():
    if 'username' not in session:
        return redirect(url_for('index'))

    requester = request.form.get('requester')
    if not requester:
        flash("No requester provided.")
        return redirect(url_for('select'))

    # Notify A that B declined
    requester_sid = None
    for sid, user in active_users.items():
        if user == requester:
            requester_sid = sid
            break
    if requester_sid:
        socketio.emit('chat_declined', {'decliner': session['username']}, to=requester_sid)

    return redirect(url_for('select'))

@app.route('/chat')
def chat():
    if 'username' not in session or 'target' not in session:
        return redirect(url_for('index'))
    return render_template('chat.html', username=session['username'], target=session['target'])

# ----- SocketIO Events ----- #

def update_active_users():
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
    target_username = data.get('target')
    message = data.get('message')
    sender_username = active_users.get(request.sid, 'Anonymous')
    timestamp = time.strftime('%I:%M %p')

    # Find target sid
    target_sid = None
    for sid, user in active_users.items():
        if user == target_username:
            target_sid = sid
            break

    if target_sid:
        emit('private_message', {
            'username': sender_username,
            'message': message,
            'timestamp': timestamp
        }, to=target_sid)
        # Echo to sender
        emit('private_message', {
            'username': sender_username,
            'message': message,
            'timestamp': timestamp,
            'to': target_username
        }, to=request.sid)
    else:
        emit('error_message', {'error': 'User not found or offline.'}, to=request.sid)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=12345, debug=True)