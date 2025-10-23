#!/bin/bash

# Constants
PYTHON_SCRIPT_URL="https://raw.githubusercontent.com/xcybermanx/AGN-SSH/main/agn_websocket.py"
AGN_MANAGER_SCRIPT_URL="https://raw.githubusercontent.com/xcybermanx/AGN-SSH/main/agnws_manager.sh"
WEBGUI_SCRIPT_URL="https://raw.githubusercontent.com/xcybermanx/AGN-SSH/main/webgui.py"
INSTALL_DIR="/opt/gx_tunnel"
SYSTEMD_SERVICE_FILE="/etc/systemd/system/gx-tunnel.service"
WEBGUI_SERVICE_FILE="/etc/systemd/system/gx-webgui.service"
PYTHON_BIN=$(command -v python3)
AGN_MANAGER_SCRIPT="gx_manager.sh"
AGN_MANAGER_PATH="$INSTALL_DIR/$AGN_MANAGER_SCRIPT"
AGN_MANAGER_LINK="/usr/local/bin/gxtunnel"
USER_DB="$INSTALL_DIR/users.json"
LOG_DIR="/var/log/gx_tunnel"

# Function to install required packages
install_required_packages() {
    echo "Installing required packages..."
    apt-get update
    apt-get install -y python3-pip dos2unix wget jq net-tools fail2ban
    pip3 install --upgrade pip
    pip3 install flask flask-cors psutil
}

# Function to download Python proxy script using wget
download_gx_websocket() {
    echo "Downloading Python proxy script..."
    wget -O "$INSTALL_DIR/gx_websocket.py" "$PYTHON_SCRIPT_URL"
}

# Function to download manager script
download_gx_manager() {
    echo "Downloading $AGN_MANAGER_SCRIPT..."
    wget -O "$AGN_MANAGER_PATH" "$AGN_MANAGER_SCRIPT_URL"
    chmod +x "$AGN_MANAGER_PATH"
    ln -sf "$AGN_MANAGER_PATH" "$AGN_MANAGER_LINK"
    convert_to_unix_line_endings "$AGN_MANAGER_PATH"
}

# Function to download web GUI
download_webgui() {
    echo "Downloading Web GUI..."
    wget -O "$INSTALL_DIR/webgui.py" "$WEBGUI_SCRIPT_URL"
    chmod +x "$INSTALL_DIR/webgui.py"
}

# Function to initialize user database
initialize_user_db() {
    if [ ! -f "$USER_DB" ]; then
        echo "Initializing user database..."
        cat > "$USER_DB" <<EOF
{
    "users": [],
    "settings": {
        "max_users": 100,
        "default_expiry_days": 30,
        "max_connections_per_user": 3
    },
    "statistics": {
        "total_connections": 0,
        "total_download": 0,
        "total_upload": 0
    }
}
EOF
    fi
    chmod 600 "$USER_DB"
}

# Function to setup fail2ban
setup_fail2ban() {
    echo "Setting up fail2ban..."
    cat > /etc/fail2ban/jail.d/gx-tunnel.conf <<EOF
[gx-tunnel]
enabled = true
port = 8080,8081
filter = gx-tunnel
logpath = $LOG_DIR/websocket.log
maxretry = 3
bantime = 3600
findtime = 600
EOF

    cat > /etc/fail2ban/filter.d/gx-tunnel.conf <<EOF
[Definition]
failregex = ^.*ERROR.*Authentication failed for .* from <HOST>
            ^.*WARNING.*Wrong password attempt from <HOST>
ignoreregex =
EOF

    systemctl enable fail2ban
    systemctl start fail2ban
}

# Function to convert script to Unix line endings
convert_to_unix_line_endings() {
    local file="$1"
    echo "Converting $file to Unix line endings..."
    dos2unix "$file"
}

# Function to start systemd service
start_systemd_service() {
    echo "Starting gx-tunnel service..."
    systemctl start gx-tunnel
    systemctl start gx-webgui
    systemctl status gx-tunnel --no-pager
}

# Function to install systemd service
install_systemd_service() {
    echo "Creating systemd service files..."
    
    # Main tunnel service
    cat > "$SYSTEMD_SERVICE_FILE" <<EOF
[Unit]
Description=GX Tunnel WebSocket SSH Service
After=network.target

[Service]
ExecStart=$PYTHON_BIN $INSTALL_DIR/gx_websocket.py
Restart=always
User=root
Group=root
WorkingDirectory=$INSTALL_DIR
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

    # Web GUI service
    cat > "$WEBGUI_SERVICE_FILE" <<EOF
[Unit]
Description=GX Tunnel Web GUI
After=network.target gx-tunnel.service

[Service]
ExecStart=$PYTHON_BIN $INSTALL_DIR/webgui.py
Restart=always
User=root
Group=root
WorkingDirectory=$INSTALL_DIR
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

    echo "Reloading systemd daemon..."
    systemctl daemon-reload
    echo "Enabling gx-tunnel services..."
    systemctl enable gx-tunnel gx-webgui
}

# Function to create log directory
create_log_dir() {
    mkdir -p "$LOG_DIR"
    touch "$LOG_DIR/websocket.log"
    touch "$LOG_DIR/connections.log"
    chmod 666 "$LOG_DIR"/*.log
}

# Function to display banner
display_banner() {
    cat << "EOF"

╔═══════════════════════════════════════════════╗
║              🚀 GX TUNNEL                     ║
║           Advanced SSH WebSocket Tunnel       ║
║              Unlimited Bandwidth              ║
║            Created by: Jawad                  ║
║           Telegram: @jawadx                   ║
╚═══════════════════════════════════════════════╝
EOF
    echo
}

# Function to display installation summary
display_installation_summary() {
    local server_ip=$(hostname -I | awk '{print $1}')
    
    echo "Installation completed successfully!"
    echo
    echo "┌─────────────────────────────────────────────────────────┐"
    echo "│ 🎯 INSTALLATION SUMMARY                                  │"
    echo "├─────────────────────────────────────────────────────────┤"
    echo "│ 📦 Service: GX Tunnel WebSocket SSH Proxy               │"
    echo "│ 🌐 WebSocket Port: 8080                                 │"
    echo "│ 🖥️  Web GUI Port: 8081                                  │"
    echo "│ 📊 Log Directory: $LOG_DIR                              │"
    echo "│ 💾 Installation: $INSTALL_DIR                           │"
    echo "└─────────────────────────────────────────────────────────┘"
    echo
    echo "🚀 Quick Start:"
    echo "   gxtunnel menu          # Interactive management"
    echo "   gxtunnel add-user      # Add new user"
    echo
    echo "🌐 Web GUI:"
    echo "   http://$server_ip:8081"
    echo "   Default admin password: admin123"
    echo
    echo "📚 Features:"
    echo "   ✅ SSH over WebSocket tunneling"
    echo "   ✅ User management with expiration"
    echo "   ✅ Web-based GUI administration"
    echo "   ✅ Fail2Ban protection"
    echo "   ✅ Real-time statistics"
    echo "   ✅ Unlimited bandwidth"
}

# Main function
main() {
    display_banner

    # Install required packages
    install_required_packages

    # Check if python3 is available
    if [ -z "$PYTHON_BIN" ]; then
        echo "Error: Python 3 is not installed or not found in PATH. Please install Python 3."
        exit 1
    fi

    # Create installation directory
    echo "Creating installation directory: $INSTALL_DIR"
    mkdir -p "$INSTALL_DIR"

    # Create log directory
    create_log_dir

    # Download scripts
    download_gx_websocket
    download_gx_manager
    download_webgui

    # Initialize user database
    initialize_user_db

    # Setup fail2ban
    setup_fail2ban

    # Install systemd service
    install_systemd_service
    
    # Start systemd service
    start_systemd_service

    # Display installation summary
    display_installation_summary
}

# Run main function
main
