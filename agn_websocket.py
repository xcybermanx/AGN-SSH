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

# =============================================
# 🚀 AGN WEBSOCKET PROXY - ENHANCED VERSION
# =============================================

# Configuration
LISTENING_ADDR = '0.0.0.0'
LISTENING_PORT = 80
PASS = 'dvdvcdVV123/'  # Leave empty for no password
BUFLEN = 4096 * 4
TIMEOUT = 60
DEFAULT_HOST = '127.0.0.1:22'
RESPONSE = 'HTTP/1.1 101 Switching Protocols\r\n\r\nContent-Length: 104857600000\r\n\r\n'

# Statistics
connection_stats = {
    'total_connections': 0,
    'active_connections': 0,
    'connections_per_minute': 0,
    'last_reset': time.time(),
    'start_time': time.time()
}

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
    file_handler = logging.FileHandler('/var/log/agn_websocket.log')
    file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)
    
    # Console handler (with colors)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(ColorFormatter())
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

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

    def run(self):
        self.soc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.soc.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.soc.settimeout(2)
        intport = int(self.port)
        
        try:
            self.soc.bind((self.host, intport))
            self.soc.listen(0)
            self.running = True

            logging.info(f"🚀 {Colors.GREEN}AGN WebSocket Proxy started on {self.host}:{self.port}{Colors.RESET}")
            logging.info(f"🔐 {Colors.YELLOW}Password protection: {'Enabled' if PASS else 'Disabled'}{Colors.RESET}")
            logging.info(f"📊 {Colors.CYAN}Real-time logging: Active{Colors.RESET}")

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

            # Enhanced header parsing for various payload types
            hostPort = self.findHeader(self.client_buffer, b'X-Real-Host')

            # Support for WebSocket-style payloads without X-Real-Host
            if hostPort == b'':
                host_header = self.findHeader(self.client_buffer, b'Host')
                
                # Check if this is a WebSocket upgrade request
                upgrade_header = self.findHeader(self.client_buffer, b'Upgrade')
                connection_header = self.findHeader(self.client_buffer, b'Connection')
                
                if upgrade_header and b'websocket' in upgrade_header.lower():
                    # This is a WebSocket-style payload, extract target from Host header
                    if host_header and not host_header.endswith(b':8098'):
                        # Host header contains the actual target
                        hostPort = host_header
                        logging.info(f"🌐 {Colors.MAGENTA}WebSocket payload detected, target: {hostPort.decode('utf-8')}{Colors.RESET}")
                    else:
                        # Use default SSH target
                        hostPort = DEFAULT_HOST.encode('utf-8')
                else:
                    # Standard proxy request
                    hostPort = host_header if host_header else DEFAULT_HOST.encode('utf-8')

            # If still no host, use default
            if hostPort == b'':
                hostPort = DEFAULT_HOST.encode('utf-8')

            split = self.findHeader(self.client_buffer, b'X-Split')

            if split != b'':
                self.client.recv(BUFLEN)

            if hostPort != b'':
                passwd = self.findHeader(self.client_buffer, b'X-Pass')
                
                if len(PASS) != 0 and passwd == PASS.encode('utf-8'):
                    self.method_CONNECT(hostPort)
                elif len(PASS) != 0 and passwd != PASS.encode('utf-8'):
                    self.client.send(b'HTTP/1.1 400 WrongPass!\r\n\r\n')
                    logging.warning(f"🔒 {Colors.RED}Wrong password attempt from {self.log}{Colors.RESET}")
                else:
                    # Allow connection for WebSocket-style payloads
                    self.method_CONNECT(hostPort)
            else:
                logging.warning(f"⚠️ {Colors.YELLOW}No target host provided from {self.log}{Colors.RESET}")
                self.client.send(b'HTTP/1.1 400 NoTargetHost!\r\n\r\n')

        except Exception as e:
            self.log += f' - error: {str(e)}'
            logging.error(f"💥 {Colors.RED}Connection error: {self.log}{Colors.RESET}")
        finally:
            self.connection_duration = time.time() - self.start_time
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
        data_transferred = 0
        
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
                            data_transferred += len(data)
                            if in_ is self.target:
                                self.client.send(data)
                            else:
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
        
        # Log data transfer stats
        if data_transferred > 0:
            logging.info(f"📊 {Colors.BLUE}Data transferred: {data_transferred} bytes - {self.log}{Colors.RESET}")

def print_usage():
    print(f'''
{Colors.CYAN}{Colors.BOLD}
╔═══════════════════════════════════════╗
║          🚀 AGN WebSocket Proxy       ║
║           Enhanced Version            ║
╚═══════════════════════════════════════╝{Colors.RESET}

{Colors.YELLOW}Usage:{Colors.RESET}
  {Colors.WHITE}agn_websocket.py -p <port>{Colors.RESET}
  {Colors.WHITE}agn_websocket.py -b <bindAddr> -p <port>{Colors.RESET}
  {Colors.WHITE}agn_websocket.py -b 0.0.0.0 -p 8098{Colors.RESET}

{Colors.YELLOW}Options:{Colors.RESET}
  {Colors.WHITE}-b, --bind    Bind address (default: 0.0.0.0){Colors.RESET}
  {Colors.WHITE}-p, --port    Listening port (default: 8098){Colors.RESET}
  {Colors.WHITE}-h, --help    Show this help message{Colors.RESET}

{Colors.YELLOW}Features:{Colors.RESET}
  {Colors.GREEN}✅ Real-time colored logging{Colors.RESET}
  {Colors.GREEN}✅ WebSocket payload support{Colors.RESET}
  {Colors.GREEN}✅ Connection statistics{Colors.RESET}
  {Colors.GREEN}✅ ISP bypass capabilities{Colors.RESET}
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
║          🚀 AGN WebSocket Proxy       ║
║           By Khaled AGN               ║
║        Telegram: @khaledagn           ║
║                                       ║
║         {Colors.MAGENTA}🚀 ENHANCED VERSION{Colors.CYAN}           ║
║         {Colors.GREEN}✅ Real-time Logging{Colors.CYAN}           ║
║         {Colors.YELLOW}🌐 ISP Bypass Ready{Colors.CYAN}           ║
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
    print(f"{Colors.YELLOW}🔐 {Colors.WHITE}Password: {Colors.GREEN if PASS else Colors.RED}{'Enabled' if PASS else 'Disabled'}{Colors.RESET}")
    print(f"{Colors.YELLOW}📊 {Colors.WHITE}Logging to: {Colors.CYAN}/var/log/agn_websocket.log{Colors.RESET}")
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
