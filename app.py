from flask import Flask, render_template, request, redirect, url_for, session
from flask_socketio import SocketIO, send

app = Flask(__name__)
# For production, replace 'secretkey' with a secure, random value
app.config['SECRET_KEY'] = 'secretkey'
socketio = SocketIO(app)

@app.route('/', methods=['GET', 'POST'])
def index():
    """Landing page where users enter a username."""
    if request.method == 'POST':
        username = request.form.get('username')
        if username:
            session['username'] = username
            return redirect(url_for('chat'))
    return render_template('index.html')

@app.route('/chat')
def chat():
    """Chat page - requires a username from the session."""
    if 'username' not in session:
        return redirect(url_for('index'))
    return render_template('chat.html', username=session['username'])

@socketio.on('chat_message')
def handle_chat_message(data):
    """
    Expects data in the form:
    {
      'username': 'UserName',
      'message': 'Hello World!'
    }
    This is then broadcast to all connected clients.
    """
    username = data.get('username')
    message = data.get('message')
    print(f"{username} says: {message}")

    # Broadcast the message to all clients (including the sender)
    # 'send' by default uses the 'message' event, but let's keep it explicit.
    send(data, broadcast=True)

if __name__ == '__main__':
    # You can also choose a port, e.g. port=8000
    socketio.run(app, host='0.0.0.0', port=12345, debug=True)