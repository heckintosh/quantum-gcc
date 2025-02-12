from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_socketio import SocketIO, emit
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secretkey'
socketio = SocketIO(app)

MAX_USERNAME_LENGTH = 16

active_users = {}     # sid -> username
ongoing_chats = {}    # username -> partner_username  (both directions)

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
    if 'username' not in session:
        return redirect(url_for('index'))
    target = request.form.get('target')
    if not target:
        flash("You must select a chat partner.")
        return redirect(url_for('select'))

    session['target'] = target

    target_sid = None
    for sid, user in active_users.items():
        if user == target:
            target_sid = sid
            break

    if target_sid:
        socketio.emit('chat_request', {'from': session['username']}, to=target_sid)

    return redirect(url_for('waiting'))

@app.route('/waiting')
def waiting():
    if 'username' not in session or 'target' not in session:
        return redirect(url_for('index'))
    return render_template('waiting.html', 
                           username=session['username'],
                           target=session['target'])

@app.route('/cancel_request', methods=['POST'])
def cancel_request():
    if 'username' not in session or 'target' not in session:
        return redirect(url_for('index'))

    target = session['target']
    username = session['username']

    target_sid = None
    for sid, user in active_users.items():
        if user == target:
            target_sid = sid
            break

    if target_sid:
        socketio.emit('request_canceled', {'canceler': username}, to=target_sid)

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

    session['target'] = requester

    # -- NEW: Mark them in ongoing_chats so the server knows they're in a chat
    b_username = session['username']
    ongoing_chats[b_username] = requester
    ongoing_chats[requester] = b_username
    # For example, ongoing_chats['Alice']='Bob' and ongoing_chats['Bob']='Alice'

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
    return render_template('chat.html', 
                           username=session['username'], 
                           target=session['target'])

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
    """
    If a user in a 1-on-1 chat disconnects,
    notify their partner with 'chat_ended' so the partner is "kicked" out.
    """
    sid = request.sid
    if sid in active_users:
        leaver = active_users[sid]
        del active_users[sid]
        update_active_users()

        # Check if 'leaver' is in an ongoing chat
        if leaver in ongoing_chats:
            partner = ongoing_chats[leaver]
            # Remove both from the dict
            del ongoing_chats[leaver]
            if partner in ongoing_chats:
                del ongoing_chats[partner]

            # Find partner's sid
            partner_sid = None
            for s_id, user in active_users.items():
                if user == partner:
                    partner_sid = s_id
                    break

            # Notify partner that the chat ended
            if partner_sid:
                socketio.emit('chat_ended', {'leaver': leaver}, to=partner_sid)

@app.route('/leave_chat', methods=['POST'])
def leave_chat():
    """
    User explicitly leaves the current chat,
    so we kick the other user (send chat_ended).
    Then redirect this user to /select.
    """
    if 'username' not in session:
        return redirect(url_for('index'))

    leaver = session['username']
    partner = session.get('target')

    # Remove from any ongoing chat dictionary
    if partner:
        # server code that finds and removes this pair from ongoing_chats...
        # Example:
        if leaver in ongoing_chats:
            del ongoing_chats[leaver]
        if partner in ongoing_chats:
            del ongoing_chats[partner]

        # Find partner's Socket.IO session ID
        partner_sid = None
        for sid, user in active_users.items():
            if user == partner:
                partner_sid = sid
                break

        # Emit 'chat_ended' to partner
        if partner_sid:
            socketio.emit('chat_ended', {'leaver': leaver}, to=partner_sid)

    # Clear your target
    session.pop('target', None)

    return redirect(url_for('select'))

@socketio.on('private_message')
def handle_private_message(data):
    target_username = data.get('target')
    message = data.get('message')
    sender_username = active_users.get(request.sid, 'Anonymous')
    timestamp = time.strftime('%I:%M %p')

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