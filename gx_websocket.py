#!/usr/bin/python3
import socket
import threading
import select
import sys
import getopt
import time
import logging
from datetime import datetime
import os
import json
import hashlib
import sqlite3
from typing import Dict, List, Optional

# =============================================
# 🚀 GX TUNNEL - WebSocket SSH Tunnel
# =============================================

# Configuration
LISTENING_ADDR = '0.0.0.0'
LISTENING_PORT = 8080
BUFLEN = 4096 * 4
TIMEOUT = 60
DEFAULT_HOST = '127.0.0.1:22'
RESPONSE = 'HTTP/1.1 101 Switching Protocols\r\n\r\nContent-Length: 104857600000\r\n\r\n'

# Database paths
USER_DB = "/opt/gx_tunnel/users.json"
STATS_DB = "/opt/gx_tunnel/statistics.db"
LOG_DIR = "/var/log/gx_tunnel"

# Statistics
connection_stats = {
    'total_connections': 0,
    'active_connections': 0,
    'connections_per_minute': 0,
    'last_reset': time.time(),
    'start_time': time.time()
}

# Active connections tracking
active_connections = {}
user_connections = {}

# Color codes for pretty output
class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

# Setup logging with colors and enhanced format
class ColorFormatter(logging.Formatter):
    FORMATS = {
        logging.DEBUG: Colors.CYAN + "%(asctime)s - %(levelname)s - %(message)s" + Colors.RESET,
        logging.INFO: Colors.GREEN + "%(asctime)s - %(levelname)s - %(message)s" + Colors.RESET,
        logging.WARNING: Colors.YELLOW + "%(asctime)s - %(levelname)s - %(message)s" + Colors.RESET,
        logging.ERROR: Colors.RED + "%(asctime)s - %(levelname)s - %(message)s" + Colors.RESET,
        logging.CRITICAL: Colors.RED + Colors.BOLD + "%(asctime)s - %(levelname)s - %(message)s" + Colors.RESET
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)

# Setup logging
def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Clear any existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # File handler (no colors)
    file_handler = logging.FileHandler(f'{LOG_DIR}/websocket.log')
    file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)
    
    # Console handler (with colors)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(ColorFormatter())
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

class StatisticsManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # User statistics table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_stats (
                username TEXT PRIMARY KEY,
                connections INTEGER DEFAULT 0,
                download_bytes INTEGER DEFAULT 0,
                upload_bytes INTEGER DEFAULT 0,
                last_connection TEXT
            )
        ''')
        
        # Global statistics table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS global_stats (
                key TEXT PRIMARY KEY,
                value INTEGER DEFAULT 0
            )
        ''')
        
        # Connection log table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS connection_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                client_ip TEXT,
                start_time TEXT,
                end_time TEXT,
                duration INTEGER,
                download_bytes INTEGER,
                upload_bytes INTEGER
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def log_connection(self, username, client_ip, duration, download_bytes, upload_bytes):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Update user stats
        cursor.execute('''
            INSERT OR REPLACE INTO user_stats 
            (username, connections, download_bytes, upload_bytes, last_connection)
            VALUES (?, COALESCE((SELECT connections FROM user_stats WHERE username = ?), 0) + 1,
                   COALESCE((SELECT download_bytes FROM user_stats WHERE username = ?), 0) + ?,
                   COALESCE((SELECT upload_bytes FROM user_stats WHERE username = ?), 0) + ?,
                   datetime('now'))
        ''', (username, username, username, download_bytes, username, upload_bytes))
        
        # Update global stats
        cursor.execute('''
            INSERT OR REPLACE INTO global_stats (key, value)
            VALUES ('total_download', COALESCE((SELECT value FROM global_stats WHERE key = 'total_download'), 0) + ?)
        ''', (download_bytes,))
        
        cursor.execute('''
            INSERT OR REPLACE INTO global_stats (key, value)
            VALUES ('total_upload', COALESCE((SELECT value FROM global_stats WHERE key = 'total_upload'), 0) + ?)
        ''', (upload_bytes,))
        
        # Log connection
        cursor.execute('''
            INSERT INTO connection_log 
            (username, client_ip, start_time, end_time, duration, download_bytes, upload_bytes)
            VALUES (?, ?, datetime('now', ?), datetime('now'), ?, ?, ?)
        ''', (username, client_ip, f'-{duration} seconds', duration, download_bytes, upload_bytes))
        
        conn.commit()
        conn.close()
    
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

class UserManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self.load_users()
    
    def load_users(self):
        try:
            with open(self.db_path, 'r') as f:
                data = json.load(f)
                self.users = data.get('users', [])
                self.settings = data.get('settings', {})
        except:
            self.users = []
            self.settings = {}
    
    def save_users(self):
        data = {
            'users': self.users,
            'settings': self.settings
        }
        with open(self.db_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def validate_user(self, username, password):
        for user in self.users:
            if user['username'] == username:
                # Check if account is expired
                if 'expires' in user and user['expires']:
                    expiry_date = datetime.strptime(user['expires'], '%Y-%m-%d')
                    if datetime.now() > expiry_date:
                        return False, "Account expired"
                
                # Check if account is active
                if not user.get('active', True):
                    return False, "Account disabled"
                
                # Check concurrent connections
                max_conn = self.settings.get('max_connections_per_user', 3)
                current_conn = user_connections.get(username, 0)
                if current_conn >= max_conn:
                    return False, f"Maximum connections ({max_conn}) reached"
                
                # Simple password validation
                if user['password'] == password:
                    return True, "Valid user"
                else:
                    return False, "Invalid password"
        return False, "User not found"
    
    def add_user(self, username, password, expires=None, max_connections=3):
        user_data = {
            'username': username,
            'password': password,
            'created': datetime.now().strftime('%Y-%m-%d'),
            'expires': expires,
            'max_connections': max_connections,
            'active': True
        }
        self.users.append(user_data)
        self.save_users()
    
    def delete_user(self, username):
        self.users = [u for u in self.users if u['username'] != username]
        self.save_users()
    
    def update_user(self, username, **kwargs):
        for user in self.users:
            if user['username'] == username:
                user.update(kwargs)
                break
        self.save_users()

class Server(threading.Thread):
    def __init__(self, host, port):
        threading.Thread.__init__(self)
        self.running = False
        self.host = host
        self.port = port
        self.threads = []
        self.threadsLock = threading.Lock()
        self.logLock = threading.Lock()
        self.connection_events = []
        self.user_manager = UserManager(USER_DB)
        self.stats_manager = StatisticsManager(STATS_DB)

    def run(self):
        self.soc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.soc.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.soc.settimeout(2)
        intport = int(self.port)
        
        try:
            self.soc.bind((self.host, intport))
            self.soc.listen(0)
            self.running = True

            logging.info(f"🚀 {Colors.GREEN}GX Tunnel started on {self.host}:{self.port}{Colors.RESET}")
            logging.info(f"📊 {Colors.CYAN}Real-time logging: Active{Colors.RESET}")
            logging.info(f"👥 {Colors.YELLOW}User authentication: Enabled{Colors.RESET}")

            while self.running:
                try:
                    c, addr = self.soc.accept()
                    c.setblocking(1)
                    
                    # Log new connection attempt
                    client_ip = addr[0]
                    logging.info(f"🔗 {Colors.BLUE}New connection from {client_ip}{Colors.RESET}")
                    
                except socket.timeout:
                    continue

                conn = ConnectionHandler(c, self, addr)
                conn.start()
                self.addConn(conn)
                
        except Exception as e:
            logging.error(f"❌ {Colors.RED}Server error: {e}{Colors.RESET}")
        finally:
            self.running = False
            self.soc.close()
            logging.info(f"🛑 {Colors.YELLOW}Server stopped{Colors.RESET}")

    def printLog(self, log):
        logging.info(log)

    def addConn(self, conn):
        try:
            self.threadsLock.acquire()
            if self.running:
                self.threads.append(conn)
                connection_stats['total_connections'] += 1
                connection_stats['active_connections'] = len(self.threads)
                
                # Log connection event
                event = {
                    'time': datetime.now().strftime('%H:%M:%S'),
                    'client': conn.log.split(' ')[1],
                    'target': conn.log.split('CONNECT ')[1] if 'CONNECT' in conn.log else 'Unknown',
                    'type': 'NEW'
                }
                self.connection_events.append(event)
                
        finally:
            self.threadsLock.release()

    def removeConn(self, conn):
        try:
            self.threadsLock.acquire()
            if conn in self.threads:
                self.threads.remove(conn)
                connection_stats['active_connections'] = len(self.threads)
                
                # Log disconnection event
                event = {
                    'time': datetime.now().strftime('%H:%M:%S'),
                    'client': conn.log.split(' ')[1],
                    'target': conn.log.split('CONNECT ')[1] if 'CONNECT' in conn.log else 'Unknown',
                    'type': 'CLOSE',
                    'duration': getattr(conn, 'connection_duration', 0)
                }
                self.connection_events.append(event)
                
        finally:
            self.threadsLock.release()

    def close(self):
        try:
            self.running = False
            self.threadsLock.acquire()
            threads = list(self.threads)
            for c in threads:
                c.close()
        finally:
            self.threadsLock.release()

    def get_stats(self):
        current_time = time.time()
        uptime = current_time - connection_stats['start_time']
        
        return {
            'active_connections': len(self.threads),
            'total_connections': connection_stats['total_connections'],
            'listening_port': self.port,
            'server_uptime': uptime,
            'connections_per_minute': connection_stats['total_connections'] / (uptime / 60) if uptime > 0 else 0
        }
    
    def get_recent_events(self, count=10):
        return self.connection_events[-count:]

class ConnectionHandler(threading.Thread):
    def __init__(self, socClient, server, addr):
        threading.Thread.__init__(self)
        self.clientClosed = False
        self.targetClosed = True
        self.client = socClient
        self.client_buffer = b''
        self.server = server
        self.log = f"Connection: {addr[0]}:{addr[1]}"
        self.start_time = time.time()
        self.connection_duration = 0
        self.username = None
        self.client_ip = addr[0]
        self.download_bytes = 0
        self.upload_bytes = 0

    def close(self):
        try:
            if not self.clientClosed:
                self.client.shutdown(socket.SHUT_RDWR)
                self.client.close()
        except:
            pass
        finally:
            self.clientClosed = True

        try:
            if not self.targetClosed:
                self.target.shutdown(socket.SHUT_RDWR)
                self.target.close()
        except:
            pass
        finally:
            self.targetClosed = True

    def run(self):
        try:
            self.client_buffer = self.client.recv(BUFLEN)

            # Extract credentials from headers
            username_header = self.findHeader(self.client_buffer, b'X-Username')
            password_header = self.findHeader(self.client_buffer, b'X-Password')

            if username_header and password_header:
                username = username_header.decode('utf-8')
                password = password_header.decode('utf-8')
                
                # Validate user
                valid, message = self.server.user_manager.validate_user(username, password)
                if not valid:
                    self.client.send(b'HTTP/1.1 401 Unauthorized\r\n\r\n' + message.encode())
                    logging.warning(f"🔒 {Colors.RED}Authentication failed for {username}: {message}{Colors.RESET}")
                    return
                
                self.username = username
                
                # Track user connection
                if username not in user_connections:
                    user_connections[username] = 0
                user_connections[username] += 1
                
                logging.info(f"✅ {Colors.GREEN}User {username} authenticated successfully ({user_connections[username]} active connections){Colors.RESET}")
            else:
                self.client.send(b'HTTP/1.1 401 Credentials Required\r\n\r\n')
                logging.warning(f"⚠️ {Colors.YELLOW}No credentials provided from {self.log}{Colors.RESET}")
                return

            # Extract target host
            hostPort = self.findHeader(self.client_buffer, b'X-Real-Host')
            if hostPort == b'':
                host_header = self.findHeader(self.client_buffer, b'Host')
                hostPort = host_header if host_header else DEFAULT_HOST.encode('utf-8')

            if hostPort != b'':
                self.method_CONNECT(hostPort)
            else:
                self.client.send(b'HTTP/1.1 400 NoTargetHost!\r\n\r\n')

        except Exception as e:
            self.log += f' - error: {str(e)}'
            logging.error(f"💥 {Colors.RED}Connection error: {self.log}{Colors.RESET}")
        finally:
            self.connection_duration = time.time() - self.start_time
            
            # Update statistics
            if self.username:
                # Remove from active connections
                if self.username in user_connections:
                    user_connections[self.username] = max(0, user_connections[self.username] - 1)
                
                # Log statistics
                self.server.stats_manager.log_connection(
                    self.username, 
                    self.client_ip, 
                    int(self.connection_duration),
                    self.download_bytes,
                    self.upload_bytes
                )
                
                logging.info(f"🔌 {Colors.CYAN}Connection closed: {self.username} from {self.log} - Duration: {self.connection_duration:.2f}s - Data: ↓{self.download_bytes} ↑{self.upload_bytes} bytes{Colors.RESET}")
            else:
                logging.info(f"🔌 {Colors.CYAN}Connection closed: {self.log} - Duration: {self.connection_duration:.2f}s{Colors.RESET}")
            
            self.close()
            self.server.removeConn(self)

    def findHeader(self, head, header):
        aux = head.find(header + b': ')

        if aux == -1:
            return b''

        aux = head.find(b':', aux)
        head = head[aux+2:]
        aux = head.find(b'\r\n')

        if aux == -1:
            return b''

        return head[:aux]

    def connect_target(self, host):
        try:
            i = host.find(b':')
            if i != -1:
                port = int(host[i+1:])
                host = host[:i]
            else:
                port = 22  # Default to SSH port

            (soc_family, soc_type, proto, _, address) = socket.getaddrinfo(host.decode('utf-8'), port)[0]

            self.target = socket.socket(soc_family, soc_type, proto)
            self.targetClosed = False
            self.target.connect(address)
            
            logging.info(f"✅ {Colors.GREEN}Connected to target: {host.decode('utf-8')}:{port}{Colors.RESET}")
            
        except Exception as e:
            logging.error(f"❌ {Colors.RED}Failed to connect to target {host.decode('utf-8')}: {e}{Colors.RESET}")
            raise

    def method_CONNECT(self, path):
        target_info = path.decode('utf-8')
        self.log += f' - CONNECT {target_info}'
        
        if self.username:
            logging.info(f"🚀 {Colors.GREEN}New tunnel established for {self.username}: {self.log}{Colors.RESET}")
        else:
            logging.info(f"🚀 {Colors.GREEN}New tunnel established: {self.log}{Colors.RESET}")

        try:
            self.connect_target(path)
            self.client.sendall(RESPONSE.encode('utf-8'))
            self.client_buffer = b''
            self.doCONNECT()
        except Exception as e:
            logging.error(f"💥 {Colors.RED}Tunnel setup failed: {e}{Colors.RESET}")
            self.client.send(b'HTTP/1.1 500 TunnelError\r\n\r\n')

    def doCONNECT(self):
        socs = [self.client, self.target]
        count = 0
        error = False
        
        while True:
            count += 1
            (recv, _, err) = select.select(socs, [], socs, 3)
            if err:
                error = True
            if recv:
                for in_ in recv:
                    try:
                        data = in_.recv(BUFLEN)
                        if data:
                            # Track data transfer
                            if in_ is self.target:
                                self.download_bytes += len(data)
                                self.client.send(data)
                            else:
                                self.upload_bytes += len(data)
                                while data:
                                    byte = self.target.send(data)
                                    data = data[byte:]
                            count = 0
                        else:
                            break
                    except:
                        error = True
                        break
            if count == TIMEOUT:
                error = True
            if error:
                break

def print_usage():
    print(f'''
{Colors.CYAN}{Colors.BOLD}
╔═══════════════════════════════════════╗
║          🚀 GX TUNNEL                 ║
║      WebSocket SSH Tunnel             ║
╚═══════════════════════════════════════╝{Colors.RESET}

{Colors.YELLOW}Usage:{Colors.RESET}
  {Colors.WHITE}gx_websocket.py -p <port>{Colors.RESET}
  {Colors.WHITE}gx_websocket.py -b <bindAddr> -p <port>{Colors.RESET}

{Colors.YELLOW}Options:{Colors.RESET}
  {Colors.WHITE}-b, --bind    Bind address (default: 0.0.0.0){Colors.RESET}
  {Colors.WHITE}-p, --port    Listening port (default: 8080){Colors.RESET}
  {Colors.WHITE}-h, --help    Show this help message{Colors.RESET}

{Colors.YELLOW}Features:{Colors.RESET}
  {Colors.GREEN}✅ SSH over WebSocket tunneling{Colors.RESET}
  {Colors.GREEN}✅ User authentication system{Colors.RESET}
  {Colors.GREEN}✅ Account expiration support{Colors.RESET}
  {Colors.GREEN}✅ Connection statistics{Colors.RESET}
  {Colors.GREEN}✅ Real-time monitoring{Colors.RESET}
    ''')

def parse_args(argv):
    global LISTENING_ADDR
    global LISTENING_PORT
    
    try:
        opts, args = getopt.getopt(argv,"hb:p:",["bind=","port="])
    except getopt.GetoptError:
        print_usage()
        sys.exit(2)
    for opt, arg in opts:
        if opt == '-h':
            print_usage()
            sys.exit()
        elif opt in ("-b", "--bind"):
            LISTENING_ADDR = arg
        elif opt in ("-p", "--port"):
            LISTENING_PORT = int(arg)

def show_banner():
    banner = f'''
{Colors.CYAN}{Colors.BOLD}
╔═══════════════════════════════════════╗
║          🚀 GX TUNNEL                 ║
║           By Jawad                    ║
║        Telegram: @jawadx              ║
║                                       ║
║         {Colors.MAGENTA}🚀 UNLIMITED BANDWIDTH{Colors.CYAN}        ║
║         {Colors.GREEN}✅ Web GUI Admin{Colors.CYAN}               ║
║         {Colors.YELLOW}🌐 Real-time Stats{Colors.CYAN}            ║
╚═══════════════════════════════════════╝{Colors.RESET}
    '''
    print(banner)

def display_stats(server):
    stats = server.get_stats()
    recent_events = server.get_recent_events(5)
    
    print(f"\n{Colors.CYAN}{Colors.BOLD}📊 REAL-TIME STATISTICS:{Colors.RESET}")
    print(f"{Colors.WHITE}╔═══════════════════════════════════════╗{Colors.RESET}")
    print(f"{Colors.WHITE}║ {Colors.GREEN}🟢 Active Connections: {Colors.CYAN}{stats['active_connections']:>15}{Colors.WHITE} ║{Colors.RESET}")
    print(f"{Colors.WHITE}║ {Colors.YELLOW}📈 Total Connections: {Colors.CYAN}{stats['total_connections']:>15}{Colors.WHITE} ║{Colors.RESET}")
    print(f"{Colors.WHITE}║ {Colors.BLUE}⏱️  Server Uptime: {Colors.CYAN}{stats['server_uptime']:>18.1f}s{Colors.WHITE} ║{Colors.RESET}")
    print(f"{Colors.WHITE}║ {Colors.MAGENTA}🚀 Connections/Min: {Colors.CYAN}{stats['connections_per_minute']:>16.1f}{Colors.WHITE} ║{Colors.RESET}")
    print(f"{Colors.WHITE}╚═══════════════════════════════════════╝{Colors.RESET}")
    
    if recent_events:
        print(f"\n{Colors.YELLOW}{Colors.BOLD}🕒 RECENT ACTIVITY:{Colors.RESET}")
        for event in recent_events:
            icon = "🟢" if event['type'] == 'NEW' else "🔴"
            color = Colors.GREEN if event['type'] == 'NEW' else Colors.RED
            duration = f" - {event['duration']:.1f}s" if 'duration' in event else ""
            print(f"  {icon} {color}{event['time']} - {event['client']} → {event['target']}{duration}{Colors.RESET}")

def main(host=LISTENING_ADDR, port=LISTENING_PORT):
    # Setup logging first
    setup_logging()
    
    # Show banner
    show_banner()
    
    print(f"{Colors.YELLOW}📍 {Colors.WHITE}Listening on: {Colors.CYAN}{LISTENING_ADDR}:{LISTENING_PORT}{Colors.RESET}")
    print(f"{Colors.YELLOW}👥 {Colors.WHITE}User authentication: {Colors.GREEN}Enabled{Colors.RESET}")
    print(f"{Colors.YELLOW}📊 {Colors.WHITE}Logging to: {Colors.CYAN}{LOG_DIR}/websocket.log{Colors.RESET}")
    print(f"{Colors.YELLOW}🚀 {Colors.WHITE}Starting server...{Colors.RESET}\n")
    
    server = Server(LISTENING_ADDR, LISTENING_PORT)
    server.start()
    
    last_stat_display = 0
    stat_interval = 10  # seconds
    
    try:
        while True:
            time.sleep(2)
            
            # Display stats every stat_interval seconds
            current_time = time.time()
            if current_time - last_stat_display >= stat_interval:
                display_stats(server)
                last_stat_display = current_time
                
                # Log stats to file
                stats = server.get_stats()
                logging.info(f"📈 Stats - Active: {stats['active_connections']}, Total: {stats['total_connections']}, Rate: {stats['connections_per_minute']:.1f}/min")
                
    except KeyboardInterrupt:
        print(f'\n\n{Colors.YELLOW}🛑 Stopping server...{Colors.RESET}')
        server.close()
        server.join()
        print(f'{Colors.GREEN}✅ Server stopped successfully{Colors.RESET}')

if __name__ == '__main__':
    parse_args(sys.argv[1:])
    main()
