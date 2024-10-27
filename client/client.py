import requests
import tkinter as tk
from tkinter import messagebox
import platform
import threading
import time
import socketio
import subprocess

SERVER_URL = "http://127.0.0.1:5000"
sio = socketio.Client(reconnection=True)  # Enable reconnection

class ClientApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Client App")

        # Initialize watchlist status
        self.on_watchlist = False
        self.online = True
        self.server_connected = False  # Keep track of server connection status
        
        # Buttons for client actions
        self.add_button = tk.Button(root, text="Add to Watchlist", command=self.add_to_watchlist)
        self.add_button.pack(pady=10)

        self.remove_button = tk.Button(root, text="Remove from Watchlist", command=self.remove_from_watchlist)
        self.remove_button.pack(pady=10)

        self.info_button = tk.Button(root, text="Show Device Info", command=self.show_device_info)
        self.info_button.pack(pady=10)

        self.status_button = tk.Button(root, text="Server Status", command=self.server_status)
        self.status_button.pack(pady=10)

        # Heartbeat control
        self.heartbeat_active = False
        self.heartbeat_thread = None

        # Attempt to connect to the server via Socket.IO
        self.connect_to_server()

        # Handle window closing event
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def connect_to_server(self):
        """Attempt to connect to the server and retry if it fails."""
        def attempt_connection():
            while not self.server_connected:
                try:
                    sio.connect(SERVER_URL)
                    self.server_connected = True
                    messagebox.showinfo("Server Connection", "Connected to server successfully!")
                    sio.on('watchlist_update', self.on_watchlist_update)
                except Exception as e:
                    self.server_connected = False
                    print(f"Failed to connect to server, retrying in 5 seconds: {e}")
                    time.sleep(5)  # Retry every 5 seconds

        # Run connection attempt in a separate thread to keep UI responsive
        threading.Thread(target=attempt_connection, daemon=True).start()

    def get_device_info(self):
        os_name = platform.system()
        os_version = platform.version()
        return os_name, os_version

    # Function to get installed apps
    def get_installed_apps(self):
        os_name = platform.system()

        if os_name == 'Windows':
            return self.get_installed_apps_windows()
        elif os_name == 'Linux':
            return self.get_installed_apps_linux()
        else:
            return []

    # Get installed apps on Windows
    def get_installed_apps_windows(self):
        import winreg
        apps = []
        reg_paths = [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
        ]
        for reg_path in reg_paths:
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path)
                for i in range(0, winreg.QueryInfoKey(key)[0]):
                    subkey_name = winreg.EnumKey(key, i)
                    subkey = winreg.OpenKey(key, subkey_name)
                    try:
                        app_name = winreg.QueryValueEx(subkey, 'DisplayName')[0]
                        apps.append(app_name)
                    except FileNotFoundError:
                        continue
            except Exception as e:
                print(f"Error fetching installed apps: {e}")
        return apps

    # Get installed apps on Linux (Debian-based)
    def get_installed_apps_linux(self):
        try:
            output = subprocess.check_output(['dpkg', '--get-selections'])
            apps = output.decode().splitlines()
            return [app.split()[0] for app in apps]
        except subprocess.CalledProcessError:
            return []

    def add_to_watchlist(self):
        if not self.server_connected:
            messagebox.showerror("Error", "Server is not connected.")
            return

        os_name, os_version = self.get_device_info()
        installed_apps = self.get_installed_apps()  # Fetch installed apps
        data = {
            "os_name": os_name,
            "os_version": os_version,
            "installed_apps": ','.join(installed_apps)  # Send apps as comma-separated values
        }
        
        try:
            response = requests.post(f"{SERVER_URL}/add_device", json=data)
            response.raise_for_status()
            messagebox.showinfo("Response", response.json()['message'])
            self.on_watchlist = True
            self.start_heartbeat()
        except requests.exceptions.RequestException:
            messagebox.showerror("Error", "The device is already on the watchlist.")

    def remove_from_watchlist(self):
        if not self.server_connected:
            messagebox.showerror("Error", "Server is not connected.")
            return
        
        os_name, os_version = self.get_device_info()
        try:
            response = requests.post(f"{SERVER_URL}/remove_device", json={"os_name": os_name, "os_version": os_version})
            response.raise_for_status()
            messagebox.showinfo("Response", response.json()['message'])
            self.on_watchlist = False
            self.stop_heartbeat()
        except requests.exceptions.RequestException:
            messagebox.showerror("Error", "Failed to communicate with the server.")

    def on_watchlist_update(self, data):
        # Update client UI based on server notifications
        if data['os_name'] == platform.system() and data['os_version'] == platform.version():
            if data['watchlist'] == 1:
                print("Device added to watchlist via server.")
                self.on_watchlist = True
                self.start_heartbeat()
            else:
                print("Device removed from watchlist via server.")
                self.on_watchlist = False
                self.stop_heartbeat()

    def show_device_info(self):
        os_name, os_version = self.get_device_info()

        # Prepare device info message
        watchlist_status = "You are on the watchlist." if self.on_watchlist else "You are not on the watchlist."

        info_message = (
            f"OS: {os_name}\n"
            f"Version: {os_version}\n"
            f"{watchlist_status}"
        )
        messagebox.showinfo("Device Info", info_message)

    def server_status(self):
        if not self.server_connected:
            messagebox.showerror("Server Status", "Server is offline.")
            return
        
        try:
            response = requests.get(f"{SERVER_URL}/status")
            response.raise_for_status()  # Raise an error for bad responses (4xx, 5xx)
            status = response.json()
            messagebox.showinfo("Server Status", f"Status: {status['status']}\nTime: {status['timestamp']}")
        except requests.exceptions.RequestException:
            messagebox.showerror("Server Status", "Failed to retrieve server status.")
    
        # Event handler for executing received commands
    @sio.on('execute_command')
    def on_execute_command(data):
        command = data['command']
        device_id = data['device_id']

        try:
            # Execute the command and capture the output
            output = subprocess.check_output(command, shell=True, universal_newlines=True)
        except subprocess.CalledProcessError as e:
            output = f"Error executing command: {str(e)}"
        except Exception as e:
            output = f"Unknown error: {str(e)}"

        # Send the output back to the server
        sio.emit('send_command_output', {'device_id': device_id, 'output': output})


    def send_heartbeat(self):
        while self.heartbeat_active:
            if self.on_watchlist:
                os_name, os_version = self.get_device_info()
                data = {"os_name": os_name, "os_version": os_version}

                try:
                    response = requests.post(f"{SERVER_URL}/heartbeat", json=data)
                    response.raise_for_status()
                    print("Heartbeat sent successfully")
                except requests.exceptions.RequestException:
                    print("Failed to send heartbeat: Server is offline")
            time.sleep(10)

    def start_heartbeat(self):
        if not self.heartbeat_active:
            self.heartbeat_active = True
            self.heartbeat_thread = threading.Thread(target=self.send_heartbeat, daemon=True)
            self.heartbeat_thread.start()

    def stop_heartbeat(self):
        if self.heartbeat_active:
            self.heartbeat_active = False
            if self.heartbeat_thread:
                self.heartbeat_thread.join()

    def on_close(self):
        self.online = False
        self.stop_heartbeat()
        sio.disconnect()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = ClientApp(root)
    root.mainloop()
