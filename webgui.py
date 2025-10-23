#!/usr/bin/python3
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
import json
import sqlite3
import subprocess
import psutil
import os
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'gx_tunnel_secret_key_2024'
CORS(app)

# Configuration
USER_DB = "/opt/gx_tunnel/users.json"
STATS_DB = "/opt/gx_tunnel/statistics.db"
CONFIG_FILE = "/opt/gx_tunnel/gx_config.conf"

# Admin credentials
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"

class UserManager:
    def __init__(self, db_path):
        self.db_path = db_path
    
    def load_users(self):
        try:
            with open(self.db_path, 'r') as f:
                data = json.load(f)
                return data.get('users', []), data.get('settings', {})
        except:
            return [], {}
    
    def save_users(self, users, settings):
        data = {
            'users': users,
            'settings': settings
        }
        with open(self.db_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def add_user(self, username, password, expires=None, max_connections=3):
        users, settings = self.load_users()
        
        # Check if user exists
        for user in users:
            if user['username'] == username:
                return False, "User already exists"
        
        user_data = {
            'username': username,
            'password': password,
            'created': datetime.now().strftime('%Y-%m-%d'),
            'expires': expires,
            'max_connections': max_connections,
            'active': True
        }
        
        users.append(user_data)
        self.save_users(users, settings)
        
        # Create system user
        try:
            subprocess.run(['useradd', '-m', '-s', '/usr/sbin/nologin', username], check=True)
            subprocess.run(['chpasswd'], input=f"{username}:{password}", text=True, check=True)
        except subprocess.CalledProcessError as e:
            return False, f"Failed to create system user: {str(e)}"
        
        return True, "User created successfully"
    
    def delete_user(self, username):
        users, settings = self.load_users()
        users = [u for u in users if u['username'] != username]
        self.save_users(users, settings)
        
        # Delete system user
        try:
            subprocess.run(['userdel', '-r', username], check=True)
        except subprocess.CalledProcessError:
            pass  # User might not exist in system
        
        return True, "User deleted successfully"

class StatisticsManager:
    def __init__(self, db_path):
        self.db_path = db_path
    
    def get_user_stats(self, username):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT connections, download_bytes, upload_bytes, last_connection
            FROM user_stats WHERE username = ?
        ''', (username,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return {
                'connections': result[0],
                'download_bytes': result[1],
                'upload_bytes': result[2],
                'last_connection': result[3]
            }
        return None
    
    def get_global_stats(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        stats = {}
        cursor.execute('SELECT key, value FROM global_stats')
        for row in cursor.fetchall():
            stats[row[0]] = row[1]
        
        conn.close()
        return stats
    
    def get_recent_connections(self, limit=10):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT username, client_ip, start_time, duration, download_bytes, upload_bytes
            FROM connection_log 
            ORDER BY id DESC 
            LIMIT ?
        ''', (limit,))
        
        connections = []
        for row in cursor.fetchall():
            connections.append({
                'username': row[0],
                'client_ip': row[1],
                'start_time': row[2],
                'duration': row[3],
                'download_bytes': row[4],
                'upload_bytes': row[5]
            })
        
        conn.close()
        return connections

def get_system_stats():
    # CPU usage
    cpu_usage = psutil.cpu_percent(interval=1)
    
    # Memory usage
    memory = psutil.virtual_memory()
    memory_usage = memory.percent
    memory_total = memory.total / (1024 ** 3)  # GB
    memory_used = memory.used / (1024 ** 3)    # GB
    
    # Disk usage
    disk = psutil.disk_usage('/')
    disk_usage = disk.percent
    disk_total = disk.total / (1024 ** 3)      # GB
    disk_used = disk.used / (1024 ** 3)        # GB
    
    # Network statistics
    net_io = psutil.net_io_counters()
    network_stats = {
        'bytes_sent': net_io.bytes_sent,
        'bytes_recv': net_io.bytes_recv
    }
    
    # Uptime
    uptime_seconds = psutil.boot_time()
    uptime = datetime.now() - datetime.fromtimestamp(uptime_seconds)
    
    return {
        'cpu_usage': cpu_usage,
        'memory_usage': memory_usage,
        'memory_total': round(memory_total, 2),
        'memory_used': round(memory_used, 2),
        'disk_usage': disk_usage,
        'disk_total': round(disk_total, 2),
        'disk_used': round(disk_used, 2),
        'network': network_stats,
        'uptime': str(uptime).split('.')[0]
    }

def bytes_to_human(bytes_size):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} PB"

# Routes
@app.route('/')
def index():
    if 'admin' not in session:
        return redirect(url_for('login'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['admin'] = True
            return jsonify({'success': True, 'message': 'Login successful'})
        else:
            return jsonify({'success': False, 'message': 'Invalid credentials'})
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('admin', None)
    return redirect(url_for('login'))

@app.route('/api/users')
def get_users():
    if 'admin' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    user_manager = UserManager(USER_DB)
    users, settings = user_manager.load_users()
    stats_manager = StatisticsManager(STATS_DB)
    
    # Add statistics to users
    for user in users:
        user_stats = stats_manager.get_user_stats(user['username'])
        if user_stats:
            user.update(user_stats)
        else:
            user.update({
                'connections': 0,
                'download_bytes': 0,
                'upload_bytes': 0,
                'last_connection': 'Never'
            })
        
        # Check if account is expired
        if user.get('expires'):
            expiry_date = datetime.strptime(user['expires'], '%Y-%m-%d')
            if datetime.now() > expiry_date:
                user['status'] = 'Expired'
            else:
                days_left = (expiry_date - datetime.now()).days
                user['status'] = f'{days_left} days left'
        else:
            user['status'] = 'Active'
    
    return jsonify({'users': users, 'settings': settings})

@app.route('/api/users/add', methods=['POST'])
def add_user():
    if 'admin' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    expires = data.get('expires')
    max_connections = data.get('max_connections', 3)
    
    if not username or not password:
        return jsonify({'success': False, 'message': 'Username and password are required'})
    
    user_manager = UserManager(USER_DB)
    success, message = user_manager.add_user(username, password, expires, max_connections)
    
    return jsonify({'success': success, 'message': message})

@app.route('/api/users/delete', methods=['POST'])
def delete_user():
    if 'admin' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.get_json()
    username = data.get('username')
    
    if not username:
        return jsonify({'success': False, 'message': 'Username is required'})
    
    user_manager = UserManager(USER_DB)
    success, message = user_manager.delete_user(username)
    
    return jsonify({'success': success, 'message': message})

@app.route('/api/stats')
def get_stats():
    if 'admin' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    stats_manager = StatisticsManager(STATS_DB)
    system_stats = get_system_stats()
    global_stats = stats_manager.get_global_stats()
    recent_connections = stats_manager.get_recent_connections(10)
    
    # Get service status
    try:
        tunnel_status = subprocess.run(['systemctl', 'is-active', 'gx-tunnel'], 
                                     capture_output=True, text=True).stdout.strip()
        webgui_status = subprocess.run(['systemctl', 'is-active', 'gx-webgui'], 
                                     capture_output=True, text=True).stdout.strip()
    except:
        tunnel_status = 'unknown'
        webgui_status = 'unknown'
    
    return jsonify({
        'system': system_stats,
        'global': global_stats,
        'recent_connections': recent_connections,
        'services': {
            'tunnel': tunnel_status,
            'webgui': webgui_status
        }
    })

@app.route('/api/services/restart', methods=['POST'])
def restart_services():
    if 'admin' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    try:
        subprocess.run(['systemctl', 'restart', 'gx-tunnel'], check=True)
        subprocess.run(['systemctl', 'restart', 'gx-webgui'], check=True)
        return jsonify({'success': True, 'message': 'Services restarted successfully'})
    except subprocess.CalledProcessError as e:
        return jsonify({'success': False, 'message': f'Failed to restart services: {str(e)}'})

@app.route('/api/services/stop', methods=['POST'])
def stop_services():
    if 'admin' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    try:
        subprocess.run(['systemctl', 'stop', 'gx-tunnel'], check=True)
        subprocess.run(['systemctl', 'stop', 'gx-webgui'], check=True)
        return jsonify({'success': True, 'message': 'Services stopped successfully'})
    except subprocess.CalledProcessError as e:
        return jsonify({'success': False, 'message': f'Failed to stop services: {str(e)}'})

@app.route('/api/services/start', methods=['POST'])
def start_services():
    if 'admin' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    try:
        subprocess.run(['systemctl', 'start', 'gx-tunnel'], check=True)
        subprocess.run(['systemctl', 'start', 'gx-webgui'], check=True)
        return jsonify({'success': True, 'message': 'Services started successfully'})
    except subprocess.CalledProcessError as e:
        return jsonify({'success': False, 'message': f'Failed to start services: {str(e)}'})

# Template routes
@app.route('/templates/<template_name>')
def serve_template(template_name):
    if 'admin' not in session:
        return redirect(url_for('login'))
    
    templates = {
        'users': 'users.html',
        'stats': 'stats.html',
        'settings': 'settings.html'
    }
    
    if template_name in templates:
        return render_template(templates[template_name])
    
    return 'Template not found', 404

if __name__ == '__main__':
    # Create templates directory if it doesn't exist
    templates_dir = os.path.join(os.path.dirname(__file__), 'templates')
    os.makedirs(templates_dir, exist_ok=True)
    
    # Create basic templates
    create_templates(templates_dir)
    
    app.run(host='0.0.0.0', port=8081, debug=False)

def create_templates(templates_dir):
    # Create login template
    login_html = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GX Tunnel - Login</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .login-container {
            background: white;
            padding: 40px;
            border-radius: 10px;
            box-shadow: 0 15px 35px rgba(0,0,0,0.1);
            width: 100%;
            max-width: 400px;
        }
        .logo { 
            text-align: center; 
            margin-bottom: 30px;
            color: #333;
        }
        .logo h1 { 
            font-size: 28px; 
            margin-bottom: 5px;
        }
        .logo p { 
            color: #666; 
            font-size: 14px;
        }
        .form-group { 
            margin-bottom: 20px; 
        }
        .form-group label { 
            display: block; 
            margin-bottom: 5px; 
            color: #333;
            font-weight: 500;
        }
        .form-group input {
            width: 100%;
            padding: 12px;
            border: 2px solid #ddd;
            border-radius: 5px;
            font-size: 16px;
            transition: border-color 0.3s;
        }
        .form-group input:focus {
            border-color: #667eea;
            outline: none;
        }
        .btn {
            width: 100%;
            padding: 12px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 5px;
            font-size: 16px;
            cursor: pointer;
            transition: transform 0.2s;
        }
        .btn:hover {
            transform: translateY(-2px);
        }
        .alert {
            padding: 10px;
            margin-bottom: 20px;
            border-radius: 5px;
            display: none;
        }
        .alert.error {
            background: #fee;
            border: 1px solid #fcc;
            color: #c66;
        }
    </style>
</head>
<body>
    <div class="login-container">
        <div class="logo">
            <h1>🚀 GX Tunnel</h1>
            <p>WebSocket SSH Tunnel Administration</p>
        </div>
        <div id="alert" class="alert error"></div>
        <form id="loginForm">
            <div class="form-group">
                <label for="username">Username:</label>
                <input type="text" id="username" name="username" required value="admin">
            </div>
            <div class="form-group">
                <label for="password">Password:</label>
                <input type="password" id="password" name="password" required value="admin123">
            </div>
            <button type="submit" class="btn">Login</button>
        </form>
    </div>

    <script>
        document.getElementById('loginForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const formData = new FormData(e.target);
            const data = {
                username: formData.get('username'),
                password: formData.get('password')
            };
            
            try {
                const response = await fetch('/login', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(data)
                });
                
                const result = await response.json();
                
                if (result.success) {
                    window.location.href = '/';
                } else {
                    showAlert(result.message, 'error');
                }
            } catch (error) {
                showAlert('Login failed: ' + error.message, 'error');
            }
        });
        
        function showAlert(message, type) {
            const alert = document.getElementById('alert');
            alert.textContent = message;
            alert.className = `alert ${type}`;
            alert.style.display = 'block';
        }
    </script>
</body>
</html>
    '''
    
    with open(os.path.join(templates_dir, 'login.html'), 'w') as f:
        f.write(login_html)
    
    # Create main template
    index_html = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GX Tunnel - Administration</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #f5f6fa;
        }
        .sidebar {
            width: 250px;
            background: white;
            height: 100vh;
            position: fixed;
            box-shadow: 2px 0 10px rgba(0,0,0,0.1);
        }
        .logo {
            padding: 30px 20px;
            border-bottom: 1px solid #eee;
        }
        .logo h1 {
            font-size: 24px;
            color: #333;
        }
        .logo p {
            color: #666;
            font-size: 12px;
        }
        .nav { padding: 20px 0; }
        .nav-item {
            padding: 15px 20px;
            cursor: pointer;
            transition: background 0.3s;
            border-left: 3px solid transparent;
        }
        .nav-item:hover {
            background: #f8f9fa;
        }
        .nav-item.active {
            background: #f0f4ff;
            border-left-color: #667eea;
            color: #667eea;
        }
        .main-content {
            margin-left: 250px;
            padding: 20px;
        }
        .header {
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }
        .content-area {
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }
        .stat-card {
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            text-align: center;
        }
        .stat-card h3 {
            color: #666;
            font-size: 14px;
            margin-bottom: 10px;
        }
        .stat-card .value {
            font-size: 24px;
            font-weight: bold;
            color: #333;
        }
        .btn {
            padding: 10px 20px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            margin: 5px;
        }
        .btn-primary { background: #667eea; color: white; }
        .btn-success { background: #28a745; color: white; }
        .btn-danger { background: #dc3545; color: white; }
        .btn-warning { background: #ffc107; color: black; }
    </style>
</head>
<body>
    <div class="sidebar">
        <div class="logo">
            <h1>🚀 GX Tunnel</h1>
            <p>Web Administration Panel</p>
        </div>
        <div class="nav">
            <div class="nav-item active" data-page="dashboard">📊 Dashboard</div>
            <div class="nav-item" data-page="users">👥 User Management</div>
            <div class="nav-item" data-page="stats">📈 Statistics</div>
            <div class="nav-item" data-page="settings">⚙️ Settings</div>
            <div class="nav-item" onclick="logout()">🚪 Logout</div>
        </div>
    </div>
    
    <div class="main-content">
        <div class="header">
            <h1 id="pageTitle">Dashboard</h1>
        </div>
        
        <div class="content-area" id="contentArea">
            <div id="dashboardContent">
                <div class="stats-grid">
                    <div class="stat-card">
                        <h3>Total Users</h3>
                        <div class="value" id="totalUsers">0</div>
                    </div>
                    <div class="stat-card">
                        <h3>Active Connections</h3>
                        <div class="value" id="activeConnections">0</div>
                    </div>
                    <div class="stat-card">
                        <h3>CPU Usage</h3>
                        <div class="value" id="cpuUsage">0%</div>
                    </div>
                    <div class="stat-card">
                        <h3>Memory Usage</h3>
                        <div class="value" id="memoryUsage">0%</div>
                    </div>
                </div>
                
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                    <div>
                        <h3>Service Control</h3>
                        <button class="btn btn-success" onclick="controlService('start')">Start Services</button>
                        <button class="btn btn-warning" onclick="controlService('restart')">Restart Services</button>
                        <button class="btn btn-danger" onclick="controlService('stop')">Stop Services</button>
                    </div>
                    <div>
                        <h3>Quick Actions</h3>
                        <button class="btn btn-primary" onclick="loadPage('users')">Add New User</button>
                        <button class="btn btn-primary" onclick="refreshStats()">Refresh Statistics</button>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        // Navigation
        document.querySelectorAll('.nav-item').forEach(item => {
            item.addEventListener('click', function() {
                if(this.dataset.page) {
                    document.querySelectorAll('.nav-item').forEach(nav => nav.classList.remove('active'));
                    this.classList.add('active');
                    loadPage(this.dataset.page);
                }
            });
        });
        
        async function loadPage(page) {
            document.getElementById('pageTitle').textContent = getPageTitle(page);
            
            try {
                const response = await fetch(`/templates/${page}`);
                const html = await response.text();
                document.getElementById('contentArea').innerHTML = html;
                
                if(page === 'dashboard') {
                    loadDashboard();
                } else if(page === 'users') {
                    loadUsers();
                } else if(page === 'stats') {
                    loadStatistics();
                }
            } catch (error) {
                document.getElementById('contentArea').innerHTML = `<p>Error loading page: ${error.message}</p>`;
            }
        }
        
        function getPageTitle(page) {
            const titles = {
                dashboard: 'Dashboard',
                users: 'User Management',
                stats: 'Statistics',
                settings: 'Settings'
            };
            return titles[page] || 'GX Tunnel';
        }
        
        async function loadDashboard() {
            await refreshStats();
        }
        
        async function refreshStats() {
            try {
                const response = await fetch('/api/stats');
                const data = await response.json();
                
                // Update stats cards
                document.getElementById('cpuUsage').textContent = data.system.cpu_usage + '%';
                document.getElementById('memoryUsage').textContent = data.system.memory_usage + '%';
                
                // Load users count
                const usersResponse = await fetch('/api/users');
                const usersData = await usersResponse.json();
                document.getElementById('totalUsers').textContent = usersData.users.length;
                
            } catch (error) {
                console.error('Error loading stats:', error);
            }
        }
        
        async function controlService(action) {
            try {
                const response = await fetch(`/api/services/${action}`, { method: 'POST' });
                const result = await response.json();
                alert(result.message);
            } catch (error) {
                alert('Error: ' + error.message);
            }
        }
        
        function logout() {
            window.location.href = '/logout';
        }
        
        // Load dashboard on start
        loadDashboard();
        setInterval(refreshStats, 5000); // Refresh every 5 seconds
    </script>
</body>
</html>
    '''
    
    with open(os.path.join(templates_dir, 'index.html'), 'w') as f:
        f.write(index_html)
    
    # Create users template
    users_html = '''
<div>
    <h2>User Management</h2>
    
    <div style="margin-bottom: 20px;">
        <button class="btn btn-primary" onclick="showAddUserForm()">Add New User</button>
    </div>
    
    <div id="addUserForm" style="display: none; background: #f8f9fa; padding: 20px; border-radius: 5px; margin-bottom: 20px;">
        <h3>Add New User</h3>
        <form id="userForm">
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px;">
                <div>
                    <label>Username:</label>
                    <input type="text" name="username" required style="width: 100%; padding: 8px;">
                </div>
                <div>
                    <label>Password:</label>
                    <input type="text" name="password" required style="width: 100%; padding: 8px;">
                </div>
            </div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px;">
                <div>
                    <label>Expiration Date (optional):</label>
                    <input type="date" name="expires" style="width: 100%; padding: 8px;">
                </div>
                <div>
                    <label>Max Connections:</label>
                    <input type="number" name="max_connections" value="3" min="1" style="width: 100%; padding: 8px;">
                </div>
            </div>
            <button type="submit" class="btn btn-success">Create User</button>
            <button type="button" class="btn btn-danger" onclick="hideAddUserForm()">Cancel</button>
        </form>
    </div>
    
    <div id="usersList">
        <table style="width: 100%; border-collapse: collapse;">
            <thead>
                <tr style="background: #f8f9fa;">
                    <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">Username</th>
                    <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">Password</th>
                    <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">Created</th>
                    <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">Expires</th>
                    <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">Max Conn</th>
                    <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">Status</th>
                    <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">Actions</th>
                </tr>
            </thead>
            <tbody id="usersTableBody">
            </tbody>
        </table>
    </div>
</div>

<script>
    async function loadUsers() {
        try {
            const response = await fetch('/api/users');
            const data = await response.json();
            displayUsers(data.users);
        } catch (error) {
            console.error('Error loading users:', error);
        }
    }
    
    function displayUsers(users) {
        const tbody = document.getElementById('usersTableBody');
        tbody.innerHTML = '';
        
        users.forEach(user => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td style="padding: 10px; border-bottom: 1px solid #dee2e6;">${user.username}</td>
                <td style="padding: 10px; border-bottom: 1px solid #dee2e6;">${user.password}</td>
                <td style="padding: 10px; border-bottom: 1px solid #dee2e6;">${user.created}</td>
                <td style="padding: 10px; border-bottom: 1px solid #dee2e6;">${user.expires || 'Never'}</td>
                <td style="padding: 10px; border-bottom: 1px solid #dee2e6;">${user.max_connections || 3}</td>
                <td style="padding: 10px; border-bottom: 1px solid #dee2e6;">${user.status}</td>
                <td style="padding: 10px; border-bottom: 1px solid #dee2e6;">
                    <button class="btn btn-danger btn-sm" onclick="deleteUser('${user.username}')">Delete</button>
                </td>
            `;
            tbody.appendChild(row);
        });
    }
    
    function showAddUserForm() {
        document.getElementById('addUserForm').style.display = 'block';
    }
    
    function hideAddUserForm() {
        document.getElementById('addUserForm').style.display = 'none';
    }
    
    document.getElementById('userForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const formData = new FormData(e.target);
        const data = {
            username: formData.get('username'),
            password: formData.get('password'),
            expires: formData.get('expires') || null,
            max_connections: parseInt(formData.get('max_connections'))
        };
        
        try {
            const response = await fetch('/api/users/add', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(data)
            });
            
            const result = await response.json();
            alert(result.message);
            
            if(result.success) {
                hideAddUserForm();
                e.target.reset();
                loadUsers();
            }
        } catch (error) {
            alert('Error: ' + error.message);
        }
    });
    
    async function deleteUser(username) {
        if(confirm(`Are you sure you want to delete user ${username}?`)) {
            try {
                const response = await fetch('/api/users/delete', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({username: username})
                });
                
                const result = await response.json();
                alert(result.message);
                
                if(result.success) {
                    loadUsers();
                }
            } catch (error) {
                alert('Error: ' + error.message);
            }
        }
    }
    
    // Load users when page is shown
    loadUsers();
</script>
'''
    
    with open(os.path.join(templates_dir, 'users.html'), 'w') as f:
        f.write(users_html)
    
    # Create stats template
    stats_html = '''
<div>
    <h2>System Statistics</h2>
    
    <div class="stats-grid" style="margin-bottom: 20px;">
        <div class="stat-card">
            <h3>Total Download</h3>
            <div class="value" id="totalDownload">0 B</div>
        </div>
        <div class="stat-card">
            <h3>Total Upload</h3>
            <div class="value" id="totalUpload">0 B</div>
        </div>
        <div class="stat-card">
            <h3>Total Connections</h3>
            <div class="value" id="totalConnections">0</div>
        </div>
        <div class="stat-card">
            <h3>Server Uptime</h3>
            <div class="value" id="serverUptime">0</div>
        </div>
    </div>
    
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
        <div>
            <h3>System Information</h3>
            <div id="systemInfo" style="background: #f8f9fa; padding: 15px; border-radius: 5px;">
                Loading...
            </div>
        </div>
        <div>
            <h3>Service Status</h3>
            <div id="serviceStatus" style="background: #f8f9fa; padding: 15px; border-radius: 5px;">
                Loading...
            </div>
        </div>
    </div>
    
    <div style="margin-top: 20px;">
        <h3>Recent Connections</h3>
        <div id="recentConnections">
            Loading...
        </div>
    </div>
</div>

<script>
    async function loadStatistics() {
        try {
            const response = await fetch('/api/stats');
            const data = await response.json();
            updateStatistics(data);
        } catch (error) {
            console.error('Error loading statistics:', error);
        }
    }
    
    function updateStatistics(data) {
        // Update global stats
        document.getElementById('totalDownload').textContent = formatBytes(data.global.total_download || 0);
        document.getElementById('totalUpload').textContent = formatBytes(data.global.total_upload || 0);
        document.getElementById('totalConnections').textContent = data.global.total_connections || 0;
        document.getElementById('serverUptime').textContent = data.system.uptime;
        
        // Update system info
        document.getElementById('systemInfo').innerHTML = `
            <p><strong>CPU Usage:</strong> ${data.system.cpu_usage}%</p>
            <p><strong>Memory:</strong> ${data.system.memory_used}GB / ${data.system.memory_total}GB (${data.system.memory_usage}%)</p>
            <p><strong>Disk:</strong> ${data.system.disk_used}GB / ${data.system.disk_total}GB (${data.system.disk_usage}%)</p>
            <p><strong>Network Sent:</strong> ${formatBytes(data.system.network.bytes_sent)}</p>
            <p><strong>Network Received:</strong> ${formatBytes(data.system.network.bytes_recv)}</p>
        `;
        
        // Update service status
        document.getElementById('serviceStatus').innerHTML = `
            <p><strong>Tunnel Service:</strong> <span style="color: ${data.services.tunnel === 'active' ? 'green' : 'red'}">${data.services.tunnel}</span></p>
            <p><strong>Web GUI:</strong> <span style="color: ${data.services.webgui === 'active' ? 'green' : 'red'}">${data.services.webgui}</span></p>
        `;
        
        // Update recent connections
        let connectionsHtml = '<table style="width: 100%; border-collapse: collapse;"><thead><tr style="background: #f8f9fa;"><th>User</th><th>IP</th><th>Time</th><th>Duration</th><th>Download</th><th>Upload</th></tr></thead><tbody>';
        
        data.recent_connections.forEach(conn => {
            connectionsHtml += `
                <tr>
                    <td style="padding: 8px; border-bottom: 1px solid #dee2e6;">${conn.username}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #dee2e6;">${conn.client_ip}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #dee2e6;">${new Date(conn.start_time).toLocaleString()}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #dee2e6;">${conn.duration}s</td>
                    <td style="padding: 8px; border-bottom: 1px solid #dee2e6;">${formatBytes(conn.download_bytes)}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #dee2e6;">${formatBytes(conn.upload_bytes)}</td>
                </tr>
            `;
        });
        
        connectionsHtml += '</tbody></table>';
        document.getElementById('recentConnections').innerHTML = connectionsHtml;
    }
    
    function formatBytes(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
    
    // Load statistics when page is shown
    loadStatistics();
    setInterval(loadStatistics, 10000); // Refresh every 10 seconds
</script>
'''
    
    with open(os.path.join(templates_dir, 'stats.html'), 'w') as f:
        f.write(stats_html)
