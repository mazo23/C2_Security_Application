import os
from flask import Flask, request, jsonify, render_template, redirect, url_for
from flask_socketio import SocketIO, emit
import sqlite3
from datetime import datetime

app = Flask(__name__)
socketio = SocketIO(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(BASE_DIR, "db.sqlite")

# Function to connect to the database
def get_db():
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

# Function to log interactions into the logs table
def log_interaction(action, details=None):
    conn = get_db()
    cursor = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('INSERT INTO logs (timestamp, action, details) VALUES (?, ?, ?)', (timestamp, action, details))
    conn.commit()
    conn.close()

@app.route('/device/<int:device_id>/apps')
def show_installed_apps(device_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT installed_apps FROM devices WHERE id = ?', (device_id,))
    device = cursor.fetchone()
    apps = device['installed_apps'].split(',') if device and device['installed_apps'] else []
    conn.close()

    return render_template('installed_apps.html', apps=apps)

# Route to render the main UI
@app.route('/')
def index():
    return render_template('index.html')

# Route to fetch all devices for Devices tab
@app.route('/devices')
def devices():
    conn = get_db()
    cursor = conn.cursor()

    # Fetch all devices from the database
    cursor.execute('SELECT id, os_name, os_version, last_seen, watchlist FROM devices')
    devices = cursor.fetchall()

    devices_list = []
    for device in devices:
        devices_list.append({
            'id': device['id'],
            'os_name': device['os_name'],
            'os_version': device['os_version'],
            'last_seen': device['last_seen'],
            'watchlist': device['watchlist']
        })

    conn.close()

    return render_template('devices.html', devices=devices_list)

# Route to remove a device from the watchlist and notify client
@app.route('/remove_from_watchlist/<int:device_id>')
def remove_from_watchlist(device_id):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('UPDATE devices SET watchlist = 0 WHERE id = ?', (device_id,))
    conn.commit()
    
    cursor.execute('SELECT os_name, os_version FROM devices WHERE id = ?', (device_id,))
    device = cursor.fetchone()
    conn.close()

    # Log the interaction
    log_interaction("Removed from Watchlist", f"Device {device['os_name']} {device['os_version']} removed from watchlist")

    # Emit event to notify client about the device removal
    socketio.emit('watchlist_update', {'os_name': device['os_name'], 'os_version': device['os_version'], 'watchlist': 0})

    return redirect('/devices')

# Route to add a device to the watchlist and notify client
@app.route('/add_to_watchlist/<int:device_id>')
def add_to_watchlist(device_id):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('UPDATE devices SET watchlist = 1 WHERE id = ?', (device_id,))
    conn.commit()

    cursor.execute('SELECT os_name, os_version FROM devices WHERE id = ?', (device_id,))
    device = cursor.fetchone()
    conn.close()

    # Log the interaction
    log_interaction("Added to Watchlist", f"Device {device['os_name']} {device['os_version']} added to watchlist")

    # Emit event to notify client about the device being added
    socketio.emit('watchlist_update', {'os_name': device['os_name'], 'os_version': device['os_version'], 'watchlist': 1})

    return redirect('/devices')

# Route to add a device to the watchlist (with duplicate check)
@app.route('/add_device', methods=['POST'])
def add_device():
    os_name = request.json['os_name']
    os_version = request.json['os_version']
    installed_apps = request.json.get('installed_apps', '')  # Fetch installed apps sent by client
    last_seen = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # Current timestamp for last_seen
    online_timestamp = last_seen  # Set online_timestamp to the current time

    conn = get_db()
    cursor = conn.cursor()

    # Check if the device already exists in the database
    cursor.execute('''SELECT * FROM devices WHERE os_name = ? AND os_version = ?''', 
                (os_name, os_version))
    existing_device = cursor.fetchone()

    if existing_device:
        # If the device is already in the watchlist, notify the client
        if existing_device['watchlist'] == 1:
            conn.close()
            return jsonify({'message': 'Device is already on the watchlist.'}), 400
        else:
            # If the device exists but is not in the watchlist, update it
            cursor.execute('''UPDATE devices SET last_seen = ?, online_timestamp = ?, watchlist = 1, installed_apps = ?
                            WHERE os_name = ? AND os_version = ?''', 
                        (last_seen, online_timestamp, installed_apps, os_name, os_version))
            conn.commit()
            conn.close()
            # Log the interaction
            log_interaction("Added to Watchlist", f"Device {os_name} {os_version} added to watchlist with apps.")
            socketio.emit('watchlist_update', {'os_name': os_name, 'os_version': os_version, 'watchlist': 1})
            return jsonify({'message': 'Device added to the watchlist.'}), 200
    else:
        # If the device doesn't exist, insert it into the database
        try:
            cursor.execute('''INSERT INTO devices (os_name, os_version, last_seen, watchlist, online_timestamp, installed_apps) 
                            VALUES (?, ?, ?, ?, ?, ?)''', 
                        (os_name, os_version, last_seen, 1, online_timestamp, installed_apps))
            conn.commit()
            conn.close()
            # Log the interaction
            log_interaction("Device Added", f"Device {os_name} {os_version} added to the system with apps.")
            socketio.emit('watchlist_update', {'os_name': os_name, 'os_version': os_version, 'watchlist': 1})
            return jsonify({'message': 'Device added successfully!'}), 200
        except sqlite3.IntegrityError as e:
            conn.close()
            return jsonify({'error': str(e)}), 500

# Route to remove a device from the watchlist
@app.route('/remove_device', methods=['POST'])
def remove_device():
    os_name = request.json['os_name']
    os_version = request.json['os_version']

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''UPDATE devices SET watchlist = 0 WHERE os_name = ? AND os_version = ?''',
                (os_name, os_version))
    conn.commit()
    conn.close()

    # Log the interaction
    log_interaction("Removed from Watchlist", f"Device {os_name} {os_version} removed from watchlist")

    return jsonify({'message': 'Device removed from watchlist!'}), 200

# Route to check server status
@app.route('/status', methods=['GET'])
def status():
    return jsonify({'status': 'Server is running', 'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")})

# Route to receive heartbeat signals from clients
@app.route('/heartbeat', methods=['POST'])
def heartbeat():
    os_name = request.json['os_name']
    os_version = request.json['os_version']
    last_seen = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''UPDATE devices SET last_seen = ? WHERE os_name = ? AND os_version = ?''',
                (last_seen, os_name, os_version))
    conn.commit()
    conn.close()

    return jsonify({'message': 'Heartbeat received successfully'}), 200

@app.route('/execute_command', methods=['POST'])
def execute_command():
    device_id = request.form['device_id']
    command = request.form['command']

    # Log the command execution
    log_interaction("Command Executed", f"Command '{command}' executed on device ID {device_id}")

    # Emit the command to the specific client device
    socketio.emit('execute_command', {'command': command, 'device_id': device_id}, room=device_id)

    return redirect(url_for('devices', command=command))

@app.route('/receive_command_output', methods=['POST'])
def receive_command_output():
    device_id = request.json['device_id']
    output = request.json['output']

    # Log the command output and store it for display
    log_interaction("Command Output", f"Output from device {device_id}: {output}")

    # Optionally, you could store this output in a database to display later on the UI
    return jsonify({'message': 'Command output received successfully'})




# Route to fetch logs for Logs tab
@app.route('/logs')
def logs():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM logs ORDER BY timestamp DESC')
    logs = cursor.fetchall()
    conn.close()
    
    return render_template('logs.html', logs=logs)

if __name__ == "__main__":
    socketio.run(app, debug=True)
