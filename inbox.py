from flask import Flask, request, jsonify, render_template, redirect, url_for, request, abort 
from flask_sqlalchemy import SQLAlchemy
import requests
from datetime import datetime, timezone
from flask_socketio import SocketIO, emit
from sqlalchemy.exc import SQLAlchemyError
import json
import os
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///whatsapp.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*")


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(15), unique=True, nullable=False)
    profile_name = db.Column(db.String(50), nullable=False)
    profile_pic = db.Column(db.String(255))  # Assuming you store a URL or file path here
    last_message_time = db.Column(db.DateTime, nullable=True)


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    is_sent  = db.Column(db.Boolean, default=True, nullable=False)  # True for sent, False for received
    media_id = db.Column(db.Integer, nullable=True)


login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # The name of the view to redirect to when the user needs to log in.




# Initialize the database and create tables
with app.app_context():
    db.create_all()


VERIFY_TOKEN = 'lawda'
WHATSAPP_API_URL = 'https://graph.facebook.com/v18.0/214379408423824/messages'
ACCESS_TOKEN = 'EAAFkxnZBSXb8BOyI0cXvoOxvq8hMIjjCLFEdin1zkvj4obJJRGjecjorekIyeJtJfe3L8UT8KJ58HMH9rqKAeQteq58c5IFT7ya27NsviSBOJ0DGAOX32TTUEngb9BP7qUOpZAohZBRsQlaYkIhkyZAtPxEFjoBSGFiTzeMjjFYZCRc404L1SA0O7Gi9kmw87mXMsZCZAx1lZC27qJQE'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        # Check if the credentials match
        if username == "Lodu" and password == "Parigandu100%":
            user = User.query.filter_by(phone_number="unique_identifier").first()
            # In a real app, "unique_identifier" should be replaced with the user's unique identifier.
            if user:
                login_user(user)
                return redirect(url_for('/'))
            else:
                # Handle case where the user does not exist in your database
                pass  # You might want to create a user record or handle differently
        else:
            return "Invalid username or password", 401
    return render_template('login.html')


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/secret')
@login_required
def secret():
    return 'This is a secret page.'


@app.route('/get-users')
def get_users():
    # Fetch all users and sort them by the last message time in descending order
    users = User.query.order_by(User.last_message_time.desc(), User.id).all()
    user_list = []
    for user in users:
        user_list.append({
            'id': user.id,
            'name': user.profile_name,
            'phone': user.phone_number,
            'lastMessageTime': user.last_message_time.isoformat() if user.last_message_time else None,
            'profilePic': user.profile_pic if user.profile_pic else url_for('static', filename='default_profile_pic.png')
        })
    return jsonify(user_list)


@app.route('/send-message/<int:user_id>', methods=['POST'])
def send_message(user_id):
    try:
        # Fetch the user or return a 404 error if not found
        user = User.query.get_or_404(user_id)
        data = request.get_json()

        # Ensure message text is provided
        message_text = data.get('message')
        if not message_text:
            return jsonify({'success': False, 'error': 'Message content is required'}), 400

        # Handle optional tempId
        temp_id = data.get('tempId')

        # Define headers and payload for the external API request
        headers = {'Authorization': f'Bearer {ACCESS_TOKEN}', 'Content-Type': 'application/json'}
        payload = {
            'messaging_product': 'whatsapp',
            'to': user.phone_number,
            'type': 'text',
            'text': {'body': message_text}
        }

        # Make the external API request
        response = requests.post(WHATSAPP_API_URL, headers=headers, json=payload)
        
        # Handle unsuccessful external request
        if response.status_code != 200:
            return jsonify({'success': False, 'error': response.text}), response.status_code

        # Create the message instance
        new_message = Message(user_id=user.id, content=message_text, is_sent=True)
        db.session.add(new_message)
        user.last_message_time = datetime.utcnow()
        db.session.commit()

        # Emit the socketio events for real-time communication
        socketio.emit('update_contact_list', {
            'id': user.id,
            'name': user.profile_name,
            'phone': user.phone_number,
            'profilePic': user.profile_pic if user.profile_pic else url_for('static', filename='default_profile_pic.png'),
            'lastMessageTime': user.last_message_time.isoformat() if user.last_message_time else None
        })

        socketio.emit('new_message', {
            'user_id': user.id,
            'content': message_text,
            'timestamp': datetime.utcnow().isoformat()  # Or however you format the timestamp
        })


        # Return a successful response
        return jsonify({'success': True, 'tempId': temp_id}), 200

    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Database error'}), 500
    except requests.RequestException as e:
        return jsonify({'success': False, 'error': 'External API error'}), 500
    except Exception as e:
        # Catch any other errors that are not explicitly handled
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/conversation/<int:user_id>')
def conversation(user_id):
    user = User.query.get_or_404(user_id)
    messages = Message.query.filter_by(user_id=user.id).order_by(Message.timestamp.asc()).all()
    return render_template('conversation.html', user=user, messages=messages)


@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        if mode and token:
            if mode == 'subscribe' and token == VERIFY_TOKEN:
                print('WEBHOOK_VERIFIED')
                return challenge
            else:
                return 'Verification token mismatch', 403
    elif request.method == 'POST':
        incoming_message = request.json
        print(incoming_message)
        try:
            sender_id = incoming_message['entry'][0]['changes'][0]['value']['contacts'][0]['wa_id']
            contact_info = incoming_message['entry'][0]['changes'][0]['value']['contacts'][0]
            profile_name = contact_info.get('profile', {}).get('name', sender_id)
            user = User.query.filter_by(phone_number=sender_id).first()
            if not user:
                user = User(phone_number=sender_id, profile_name=profile_name)
                db.session.add(user)
                db.session.commit()

            message_type = incoming_message['entry'][0]['changes'][0]['value']['messages'][0]['type']
            message_content = None
            media_id = None
            if message_type == 'text':
                message_content = incoming_message['entry'][0]['changes'][0]['value']['messages'][0]['text']['body']
            elif message_type == 'image':
                media_id = incoming_message['entry'][0]['changes'][0]['value']['messages'][0]['image']['id']
                message_content = media_id  # Placeholder text for image messages

                # Retrieve the media URL for the given media ID
                url = f"https://graph.facebook.com/v18.0/{media_id}"
                headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
                response = requests.get(url, headers=headers)
                if response.status_code == 200:
                    media_url = response.json().get('url')
                    print(media_url)

                    # Download the media from the given URL and save it to the specified path
                    filename = f"media_{media_id}.jpg"  # Or use a different path/filename
                    downloadableheaders = {
                        "Authorization": f"Bearer {ACCESS_TOKEN}"
                    }
                    url = media_url
                    response = requests.get(url, headers=downloadableheaders, stream=True)
                    if response.status_code == 200:
                        # The file will be saved to the current directory with the name 'downloaded_image.jpg'
                        with open(filename, 'wb') as f:
                            for chunk in response.iter_content(1024):
                                f.write(chunk)
                        print("The image has been downloaded successfully.")
                    else:
                        print(f"Failed to download the image: {response.status_code}")                    

                else:
                    print(f"Failed to retrieve media URL: {response.status_code}, {response.text}")
            
            # elif 'audio' in incoming_message['entry'][0]['changes'][0]['value']['messages'][0]:
            #     message_type = 'audio'
            #     media_id = incoming_message['entry'][0]['changes'][0]['value']['messages'][0]['audio']['id']
            #     print("this is an audio message 4 u")




            else:
                message_content = 'another media fie'
                

            new_message = Message(user_id=user.id, content=message_content, is_sent=False, media_id=media_id)
            db.session.add(new_message)
            user.last_message_time = datetime.utcnow()
            db.session.commit()

            # Emitting socket events as before
            socketio.emit('new_received_message', {
                'user_id': user.id,
                'content': message_content,
                'timestamp': datetime.utcnow().isoformat(),
                'media_id': media_id  # Optionally include media ID in the event
            })
            print(f"Emitted new_message for user_id {user.id} with content: {message_content}")

            socketio.emit('update_contact_list', {
                'id': user.id,
                'name': user.profile_name,
                'phone': user.phone_number,
                'profilePic': user.profile_pic if user.profile_pic else url_for('static', filename='default_profile_pic.png'),
                'lastMessageTime': user.last_message_time.isoformat() if user.last_message_time else None
            })
            print(f"Emitted update_contact_list for user_id {user.id}")
        except (KeyError, IndexError) as e:
            print(f"Error processing incoming message: {e}")
            return jsonify(success=False, error=str(e)), 500

        return jsonify(success=True), 200
    else:
        return 'Invalid request method', 405


@app.route('/get-messages/<int:user_id>')
def get_messages(user_id):
    messages = Message.query.filter_by(user_id=user_id).all()
    messages_formatted = [
        {
            'content': message.content,
            'is_sent': message.is_sent,
            'timestamp': message.timestamp.isoformat()  # You might want to send this as well
        }
        for message in messages
    ]
    return jsonify(messages_formatted)

@app.route('/')
def index():
    users = User.query.all()
    return render_template('index.html', users=users)



@socketio.on('message')
def handle_message(data):
    # This is where you handle incoming messages and broadcast them to clients.
    # 'data' contains the message information.
    socketio.emit('new_message', data)

@socketio.on('message_from_client')
def handle_message(message):
    # Assuming 'message' is a dictionary with 'user_id' and 'content'
    emit('message_from_server', message, broadcast=True)
# In your Flask app, after setting up SocketIO
@socketio.on('connect')
def test_connect():
    emit('new_received_message', {'user_id': 'test_id', 'content': 'Test message from server'})


socketio = SocketIO(app)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
