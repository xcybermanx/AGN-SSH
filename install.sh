#!/bin/bash

# Constants
INSTALL_DIR="/opt/gx-tunnel"
SYSTEMD_SERVICE_FILE="/etc/systemd/system/gx-tunnel.service"
PYTHON_BIN=$(command -v python3)
MANAGER_SCRIPT="gx-manager.sh"
MANAGER_PATH="$INSTALL_DIR/$MANAGER_SCRIPT"
MANAGER_LINK="/usr/local/bin/gxtunnel"
WEB_PANEL_DIR="/opt/gx-webpanel"
WEB_PANEL_PORT="8080"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to display banner
display_banner() {
    echo -e "${BLUE}"
    echo -e "┌─────────────────────────────────────────────────────────┐"
    echo -e "│                    ${GREEN}🛰️ GX TUNNEL${BLUE}                           │"
    echo -e "│         ${YELLOW}Advanced WebSocket Tunnel Solution${BLUE}              │"
    echo -e "│                                                         │"
    echo -e "│                 ${GREEN}🚀 Auto-Installer${BLUE}                        │"
    echo -e "│    ${GREEN}✅ WebSocket Proxy${BLUE}    ${YELLOW}🌐 Web Panel${BLUE}                 │"
    echo -e "│    ${BLUE}🔧 Auto-Config${BLUE}       ${GREEN}⚡ Quick Setup${BLUE}                │"
    echo -e "│                                                         │"
    echo -e "│              ${YELLOW}Created by: Jawad${BLUE}                        │"
    echo -e "└─────────────────────────────────────────────────────────┘"
    echo -e "${NC}"
}

# Function to print status
print_status() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

# Function to install required packages
install_required_packages() {
    print_status "Installing required packages..."
    apt-get update > /dev/null 2>&1
    apt-get install -y python3-pip wget curl net-tools ufw dos2unix > /dev/null 2>&1
    
    # Install websockify
    print_status "Installing websockify..."
    pip3 install websockify > /dev/null 2>&1
    
    # Install web server components
    print_status "Installing web server components..."
    apt-get install -y nginx python3-venv > /dev/null 2>&1
}

# Function to create WebSocket tunnel service
install_websockify_service() {
    print_status "Setting up WebSocket tunnel service..."
    
    # Create websockify service
    cat > /etc/systemd/system/websockify.service <<EOF
[Unit]
Description=Websockify WebSocket to TCP Bridge
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/websockify 0.0.0.0:8098 127.0.0.1:22
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    # Create enhanced Python tunnel service (backup)
    cat > /etc/systemd/system/gx-tunnel.service <<EOF
[Unit]
Description=GX Tunnel WebSocket Service
After=network.target

[Service]
Type=simple
ExecStart=$PYTHON_BIN $INSTALL_DIR/gx_tunnel.py
Restart=always
RestartSec=5
User=root
WorkingDirectory=$INSTALL_DIR
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF
}

# Function to install UDP Gateway
install_udp_gateway() {
    print_status "Installing UDP Gateway..."
    
    # Install dependencies
    apt-get install -y build-essential cmake git > /dev/null 2>&1
    
    # Download and compile badvpn
    cd /tmp
    git clone https://github.com/ambrop72/badvpn.git > /dev/null 2>&1
    cd badvpn
    mkdir build
    cd build
    cmake .. -DBUILD_NOTHING_BY_DEFAULT=1 -DBUILD_UDPGW=1 > /dev/null 2>&1
    make > /dev/null 2>&1
    cp udpgw/badvpn-udpgw /usr/local/bin/
    
    # Create UDP Gateway service
    cat > /etc/systemd/system/udpgw.service <<EOF
[Unit]
Description=UDP Gateway for GX Tunnel
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/badvpn-udpgw --listen-addr 0.0.0.0:7300
Restart=always
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
EOF
}

# Function to create web management panel
install_web_panel() {
    print_status "Installing web management panel..."
    
    # Create web panel directory
    mkdir -p $WEB_PANEL_DIR
    
    # Create simple web panel
    cat > $WEB_PANEL_DIR/index.html <<'EOF'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GX Tunnel Manager</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { text-align: center; color: white; margin-bottom: 30px; }
        .header h1 { font-size: 2.5em; margin-bottom: 10px; }
        .header p { font-size: 1.2em; opacity: 0.9; }
        .dashboard { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .card { background: white; padding: 25px; border-radius: 15px; box-shadow: 0 10px 30px rgba(0,0,0,0.2); }
        .card h2 { color: #333; margin-bottom: 15px; font-size: 1.4em; }
        .status-item { display: flex; justify-content: space-between; margin-bottom: 10px; padding: 10px; background: #f8f9fa; border-radius: 8px; }
        .status-online { border-left: 4px solid #28a745; }
        .status-offline { border-left: 4px solid #dc3545; }
        .btn { background: #667eea; color: white; border: none; padding: 12px 24px; border-radius: 8px; cursor: pointer; font-size: 1em; margin: 5px; transition: background 0.3s; }
        .btn:hover { background: #764ba2; }
        .btn-restart { background: #ffc107; color: black; }
        .btn-stop { background: #dc3545; }
        .logs { background: #1e1e1e; color: #00ff00; padding: 15px; border-radius: 8px; font-family: monospace; height: 200px; overflow-y: auto; margin-top: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🛰️ GX Tunnel Manager</h1>
            <p>Advanced WebSocket Tunnel Solution</p>
        </div>
        
        <div class="dashboard">
            <div class="card">
                <h2>📊 Service Status</h2>
                <div id="statusContainer">
                    <div class="status-item status-online">
                        <span>WebSocket Tunnel</span>
                        <span id="websocketStatus">Checking...</span>
                    </div>
                    <div class="status-item">
                        <span>UDP Gateway</span>
                        <span id="udpStatus">Checking...</span>
                    </div>
                    <div class="status-item">
                        <span>Active Connections</span>
                        <span id="connections">0</span>
                    </div>
                </div>
            </div>
            
            <div class="card">
                <h2>🔧 Quick Actions</h2>
                <button class="btn" onclick="restartService()">🔄 Restart Tunnel</button>
                <button class="btn btn-restart" onclick="restartUDP()">🔄 Restart UDP</button>
                <button class="btn btn-stop" onclick="stopService()">🛑 Stop All</button>
                <button class="btn" onclick="viewLogs()">📜 View Logs</button>
            </div>
            
            <div class="card">
                <h2>🌐 Connection Info</h2>
                <div class="status-item">
                    <span>WebSocket Port:</span>
                    <span>8098</span>
                </div>
                <div class="status-item">
                    <span>UDP Gateway Port:</span>
                    <span>7300</span>
                </div>
                <div class="status-item">
                    <span>SSH Port:</span>
                    <span>22</span>
                </div>
            </div>
        </div>
        
        <div class="card">
            <h2>📜 Real-time Logs</h2>
            <div class="logs" id="logContainer">
                <div>GX Tunnel Web Panel Started...</div>
            </div>
        </div>
    </div>

    <script>
        function updateStatus() {
            fetch('/api/status')
                .then(r => r.json())
                .then(data => {
                    document.getElementById('websocketStatus').textContent = data.websocket;
                    document.getElementById('udpStatus').textContent = data.udp;
                    document.getElementById('connections').textContent = data.connections;
                });
        }
        
        function restartService() {
            fetch('/api/restart', {method: 'POST'});
        }
        
        function restartUDP() {
            fetch('/api/restart-udp', {method: 'POST'});
        }
        
        function stopService() {
            fetch('/api/stop', {method: 'POST'});
        }
        
        function viewLogs() {
            fetch('/api/logs')
                .then(r => r.text())
                .then(logs => {
                    document.getElementById('logContainer').innerHTML = logs;
                });
        }
        
        // Update status every 5 seconds
        setInterval(updateStatus, 5000);
        updateStatus();
    </script>
</body>
</html>
EOF

    # Create simple API backend
    cat > $WEB_PANEL_DIR/server.py <<'EOF'
#!/usr/bin/env python3
from http.server import HTTPServer, SimpleHTTPRequestHandler
import json
import os
import subprocess

class GXHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=os.path.dirname(__file__), **kwargs)
    
    def do_GET(self):
        if self.path == '/api/status':
            self.send_status()
        elif self.path == '/api/logs':
            self.send_logs()
        else:
            super().do_GET()
    
    def do_POST(self):
        if self.path == '/api/restart':
            subprocess.run(['systemctl', 'restart', 'websockify'])
            self.send_response(200)
            self.end_headers()
        elif self.path == '/api/restart-udp':
            subprocess.run(['systemctl', 'restart', 'udpgw'])
            self.send_response(200)
            self.end_headers()
        elif self.path == '/api/stop':
            subprocess.run(['systemctl', 'stop', 'websockify', 'udpgw'])
            self.send_response(200)
            self.end_headers()
        else:
            self.send_error(404)
    
    def send_status(self):
        try:
            # Check websockify status
            result = subprocess.run(['systemctl', 'is-active', 'websockify'], 
                                  capture_output=True, text=True)
            websockify_status = result.stdout.strip()
            
            # Check UDP status
            result = subprocess.run(['systemctl', 'is-active', 'udpgw'],
                                  capture_output=True, text=True)
            udp_status = result.stdout.strip()
            
            # Get connections (simplified)
            result = subprocess.run(['netstat', '-tunp'], capture_output=True, text=True)
            connections = len([line for line in result.stdout.split('\n') if ':8098' in line])
            
            status = {
                'websocket': '🟢 Running' if websockify_status == 'active' else '🔴 Stopped',
                'udp': '🟢 Running' if udp_status == 'active' else '🔴 Stopped',
                'connections': connections
            }
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(status).encode())
        except Exception as e:
            self.send_error(500, str(e))
    
    def send_logs(self):
        try:
            result = subprocess.run(['journalctl', '-u', 'websockify', '-n', '10', '--no-pager'],
                                  capture_output=True, text=True)
            logs = result.stdout
            
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(logs.encode())
        except Exception as e:
            self.send_error(500, str(e))

if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', 8080), GXHandler)
    print("GX Tunnel Web Panel running on http://0.0.0.0:8080")
    server.serve_forever()
EOF

    # Create web panel service
    cat > /etc/systemd/system/gx-webpanel.service <<EOF
[Unit]
Description=GX Tunnel Web Panel
After=network.target

[Service]
Type=simple
ExecStart=$PYTHON_BIN $WEB_PANEL_DIR/server.py
WorkingDirectory=$WEB_PANEL_DIR
Restart=always
User=root

[Install]
WantedBy=multi-user.target
EOF
}

# Function to create manager script
create_manager_script() {
    print_status "Creating management script..."
    
    mkdir -p $INSTALL_DIR
    
    # Download or create manager script
    cat > $MANAGER_PATH <<'EOF'
#!/bin/bash
# GX Tunnel Manager - Compact version
echo "GX Tunnel Manager - Use web panel at http://$(curl -s ifconfig.me):8080"
echo "Quick commands:"
echo "  systemctl status websockify"
echo "  systemctl status udpgw" 
echo "  systemctl restart websockify"
echo "Web Panel: http://localhost:8080"
EOF

    chmod +x $MANAGER_PATH
    ln -sf $MANAGER_PATH $MANAGER_LINK
}

# Function to configure firewall
configure_firewall() {
    print_status "Configuring firewall..."
    
    ufw --force enable > /dev/null 2>&1
    ufw allow 22 > /dev/null 2>&1
    ufw allow 8098 > /dev/null 2>&1
    ufw allow 7300 > /dev/null 2>&1
    ufw allow 8080 > /dev/null 2>&1
}

# Function to start services
start_services() {
    print_status "Starting services..."
    
    systemctl daemon-reload
    systemctl enable websockify udpgw gx-webpanel > /dev/null 2>&1
    systemctl start websockify udpgw gx-webpanel
}

# Function to display installation summary
display_installation_summary() {
    local server_ip=$(curl -s ifconfig.me)
    
    echo
    echo -e "${GREEN}┌─────────────────────────────────────────────────────────┐${NC}"
    echo -e "${GREEN}│                  INSTALLATION COMPLETE                  │${NC}"
    echo -e "${GREEN}└─────────────────────────────────────────────────────────┘${NC}"
    echo
    echo -e "${YELLOW}📡 Services Installed:${NC}"
    echo -e "  ${GREEN}✅ WebSocket Tunnel${NC} (port 8098)"
    echo -e "  ${GREEN}✅ UDP Gateway${NC} (port 7300)" 
    echo -e "  ${GREEN}✅ Web Management Panel${NC} (port 8080)"
    echo
    echo -e "${YELLOW}🌐 Access Points:${NC}"
    echo -e "  ${BLUE}Web Panel:${NC} http://$server_ip:8080"
    echo -e "  ${BLUE}WebSocket:${NC} ws://$server_ip:8098"
    echo -e "  ${BLUE}UDP Gateway:${NC} $server_ip:7300"
    echo
    echo -e "${YELLOW}🔧 Management:${NC}"
    echo -e "  ${GREEN}systemctl status websockify${NC} - Check tunnel status"
    echo -e "  ${GREEN}systemctl restart websockify${NC} - Restart tunnel"
    echo -e "  ${GREEN}gxtunnel${NC} - Show quick commands"
    echo
    echo -e "${GREEN}🚀 GX Tunnel is ready! Access the web panel to manage services.${NC}"
}

# Main function
main() {
    display_banner
    
    # Check if root
    if [ "$EUID" -ne 0 ]; then
        print_error "Please run as root"
        exit 1
    fi
    
    # Install packages
    install_required_packages
    
    # Setup services
    install_websockify_service
    install_udp_gateway
    install_web_panel
    create_manager_script
    
    # Configure system
    configure_firewall
    start_services
    
    # Show summary
    display_installation_summary
}

# Run main function
main
