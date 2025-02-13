from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_socketio import SocketIO, emit
import time
from hashlib import sha256

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secretkey'
socketio = SocketIO(app)

MAX_USERNAME_LENGTH = 16

active_users = {}     # sid -> username
ongoing_chats = {}    # username -> partner_username  (both directions)

# --------------- NEW: Track which users have "quantkeys" ---------------
quant_keys = {}  #username : key
quant_keys_hash = {} #key hash : username

# ------------------ Admin Route to Set a Quantum Key -------------------
@app.route('/update', methods=['POST'])
def update_quantkey():
    """
    This route expects:
      - A request header: 'Authorization: qkadmin'
      - form data: 'username' and 'quantkey'
    If valid, store quantkey in quant_keys[username].
    """
    if request.headers.get('Authorization') != 'qkdadmin':
        return "Unauthorized", 401

    username = request.form.get('username')
    qk = request.form.get('quantkey')
    if not username or not qk:
        return "Missing username or quantkey", 400

    # Assign the quantkey to this user
    if username in quant_keys:
        return "Username is taken", 400
    
    quant_keys[username] = bytes.fromhex(qk)
    print(quant_keys)
    quant_keys_hash[sha256(bytes.fromhex(qk)).hexdigest()] = username
    print(quant_keys_hash)
    return f"Assigned quantkey to user '{username}'", 200

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        quantkeyhash = request.form.get('username') #TODO: change name plsssss
        if quantkeyhash:
            quantkeyhash = quantkeyhash.strip().lstrip()
            # -------------- NEW: Check if this username is in quant_keys --------------
            if quantkeyhash not in quant_keys_hash.keys():
                flash("Invalid quant key")
                return redirect(url_for('index'))

            session['username'] = quant_keys_hash[quantkeyhash]
            session.pop('target', None)
            return redirect(url_for('select'))
        else:
            flash("Username cannot be empty.")
            return redirect(url_for('index'))
    elif request.method == "GET":
        return render_template('index.html')

@app.route('/select')
def select():
    if 'username' not in session:
        return redirect(url_for('index'))
    # Double-check user still has quantkey in case it was removed
    if session['username'] not in quant_keys:
        flash("Your quantkey is missing. Contact admin.")
        return redirect(url_for('index'))
    return render_template('select.html', username=session['username'])

@app.route('/set_target', methods=['POST'])
def set_target():
    if 'username' not in session:
        return redirect(url_for('index'))
    if session['username'] not in quant_keys:
        flash("Your quantkey is missing. Contact admin.")
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
    if session['username'] not in quant_keys:
        flash("Your quantkey is missing. Contact admin.")
        return redirect(url_for('index'))

    return render_template('waiting.html', 
                           username=session['username'],
                           target=session['target'])

@app.route('/cancel_request', methods=['POST'])
def cancel_request():
    if 'username' not in session or 'target' not in session:
        return redirect(url_for('index'))
    if session['username'] not in quant_keys:
        flash("Your quantkey is missing. Contact admin.")
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
    if session['username'] not in quant_keys:
        flash("Your quantkey is missing. Contact admin.")
        return redirect(url_for('index'))

    requester = request.form.get('requester')
    if not requester:
        flash("No requester provided.")
        return redirect(url_for('select'))

    session['target'] = requester

    b_username = session['username']
    ongoing_chats[b_username] = requester
    ongoing_chats[requester] = b_username

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
    if session['username'] not in quant_keys:
        flash("Your quantkey is missing. Contact admin.")
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
    # Check user still has quantkey
    if session['username'] not in quant_keys:
        flash("Your quantkey is missing. Contact admin.")
        return redirect(url_for('index'))

    return render_template('chat.html', 
                           username=session['username'], 
                           target=session['target'])

def update_active_users():
    users = list(active_users.values())
    socketio.emit('active_users', users)

@socketio.on('connect')
def handle_connect():
    """
    On Socket.IO connect, ensure the session's username has a quantkey.
    If not, refuse connection (disconnect).
    """
    username = session.get('username')
    if not username or (username not in quant_keys):
        # You can either forcibly disconnect or just ignore
        emit('error_message', {'error': 'No quantkey. Access denied.'})
        return  # won't register in active_users
    # Otherwise, register as active
    active_users[request.sid] = username
    update_active_users()

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    if sid in active_users:
        leaver = active_users[sid]
        del active_users[sid]
        update_active_users()

        # Check if 'leaver' is in an ongoing chat
        if leaver in ongoing_chats:
            partner = ongoing_chats[leaver]
            del ongoing_chats[leaver]
            if partner in ongoing_chats:
                del ongoing_chats[partner]

            partner_sid = None
            for s_id, user in active_users.items():
                if user == partner:
                    partner_sid = s_id
                    break

            if partner_sid:
                socketio.emit('chat_ended', {'leaver': leaver}, to=partner_sid)

@app.route('/leave_chat', methods=['POST'])
def leave_chat():
    if 'username' not in session:
        return redirect(url_for('index'))
    if session['username'] not in quant_keys:
        flash("Your quantkey is missing. Contact admin.")
        return redirect(url_for('index'))

    leaver = session['username']
    partner = session.get('target')

    if partner:
        if leaver in ongoing_chats:
            del ongoing_chats[leaver]
        if partner in ongoing_chats:
            del ongoing_chats[partner]

        partner_sid = None
        for sid, user in active_users.items():
            if user == partner:
                partner_sid = sid
                break

        if partner_sid:
            socketio.emit('chat_ended', {'leaver': leaver}, to=partner_sid)

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