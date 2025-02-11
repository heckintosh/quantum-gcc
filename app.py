from flask import Flask, render_template
from flask_socketio import SocketIO, send

app = Flask(__name__)
# You should use a secret key for production
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app)

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('message')
def handle_message(msg):
    """Receive message from a client and broadcast to all."""
    print('Received message: ' + str(msg))
    # Broadcast the message to all connected clients
    send(msg, broadcast=True)

if __name__ == '__main__':
    # debug=True automatically reloads on code changes
    socketio.run(app, host='0.0.0.0', port=8000, debug=True)