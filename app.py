from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_socketio import SocketIO, send
import time

app = Flask(__name__)
# Replace with a more secure secret key for production
app.config['SECRET_KEY'] = 'secretkey'
socketio = SocketIO(app)

MAX_USERNAME_LENGTH = 16  # define your desired max length here

@app.route('/', methods=['GET', 'POST'])
def index():
    """
    Landing page where users enter a username.
    """
    if request.method == 'POST':
        username = request.form.get('username')  # get form data
        if username:
            # Check length
            if len(username) > MAX_USERNAME_LENGTH:
                flash(f"Username must be at most {MAX_USERNAME_LENGTH} characters long.")
                return redirect(url_for('index'))
            else:
                # if okay, proceed
                session['username'] = username
                return redirect(url_for('chat'))
        else:
            flash("Username cannot be empty.")
            return redirect(url_for('index'))
    return render_template('index.html')

@app.route('/chat')
def chat():
    """
    Chat page - requires a username from the session.
    If no username is found, redirect to index.
    """
    if 'username' not in session:
        return redirect(url_for('index'))
    return render_template('chat.html', username=session['username'])

@socketio.on('chat_message')
def handle_chat_message(data):
    """
    Expects data in the form:
    {
      'username': '...',
      'message': '...'
    }
    Broadcasts this to all clients.
    """
    username = data.get('username')
    message = data.get('message')
    timestamp = time.strftime('%I:%M %p')  # e.g. "09:15 PM"

    # We can add a timestamp on the server side, so all clients see the same time.
    data['timestamp'] = timestamp
    print(f"{username} ({timestamp}): {message}")

    # Broadcast the message to all connected clients
    send(data, broadcast=True)

if __name__ == '__main__':
    # Run the SocketIO server
    socketio.run(app, host='0.0.0.0', port=12345, debug=True)