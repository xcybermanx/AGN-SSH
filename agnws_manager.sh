#!/bin/bash

# Constants
AGN_WEBSOCKET_SERVICE="agn-websocket"
PYTHON_SCRIPT_PATH="/opt/agn_websocket/agn_websocket.py"
LOG_FILE="/var/log/agn_websocket.log"
UDPGW_SERVICE="udpgw"
UDPGW_PORT="7300"
CONFIG_FILE="/opt/agn_websocket/agn_config.conf"

# Color codes for pretty output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color

# Function to display banner
display_banner() {
   echo -e "${BLUE}"
   echo -e "┌─────────────────────────────────────────────────────────┐"
   echo -e "│                    ${WHITE}🛰️ GX TUNNEL${BLUE}                           │"
   echo -e "│         ${YELLOW}Advanced WebSocket Tunnel Solution${BLUE}              │"
   echo -e "│                                                         │"
   echo -e "│                 ${GREEN}🚀 Features:${BLUE}                            │"
   echo -e "│    ${GREEN}✅ Real-time Monitoring${BLUE}   ${YELLOW}🌐 ISP Bypass${BLUE}              │"
   echo -e "│    ${CYAN}🔒 Secure Tunneling${BLUE}      ${PURPLE}⚡ High Performance${BLUE}          │"
   echo -e "│                                                         │"
   echo -e "│              ${WHITE}Created by: Jawad${BLUE}                        │"
   echo -e "│           ${YELLOW}Telegram: @jawadx${BLUE}                          │"
   echo -e "└─────────────────────────────────────────────────────────┘"
   echo -e "${NC}"
}

# Function to show pretty header
show_header() {
    clear
    display_banner
    echo
}

# Function to load configuration
load_config() {
    if [ -f "$CONFIG_FILE" ]; then
        source "$CONFIG_FILE"
    else
        # Default values
        DOMAIN_NAME=""
        USE_DOMAIN=false
        CLOUDFLARE_API_KEY=""
        CLOUDFLARE_EMAIL=""
        CLOUDFLARE_ZONE_ID=""
    fi
}

# Function to save configuration
save_config() {
    cat > "$CONFIG_FILE" <<EOF
DOMAIN_NAME="$DOMAIN_NAME"
USE_DOMAIN=$USE_DOMAIN
CLOUDFLARE_API_KEY="$CLOUDFLARE_API_KEY"
CLOUDFLARE_EMAIL="$CLOUDFLARE_EMAIL"
CLOUDFLARE_ZONE_ID="$CLOUDFLARE_ZONE_ID"
EOF
    chmod 600 "$CONFIG_FILE"
}

# Function to get server address (IP or Domain)
get_server_address() {
    if [ "$USE_DOMAIN" = "true" ] && [ -n "$DOMAIN_NAME" ]; then
        echo "$DOMAIN_NAME"
    else
        get_ipv4_address
    fi
}

# Function to get IPv4 address only
get_ipv4_address() {
    # Try multiple methods to get IPv4
    local ipv4=""
    
    # Method 1: Use hostname -I (usually shows IPv4 first)
    ipv4=$(hostname -I | awk '{print $1}')
    
    # Method 2: Check if it's IPv4
    if [[ $ipv4 =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        echo "$ipv4"
        return
    fi
    
    # Method 3: Use ip command
    ipv4=$(ip -4 addr show | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | grep -v '127.0.0.1' | head -1)
    if [ -n "$ipv4" ]; then
        echo "$ipv4"
        return
    fi
    
    # Method 4: Use curl to external service
    ipv4=$(curl -s -4 ifconfig.me 2>/dev/null)
    if [ -n "$ipv4" ]; then
        echo "$ipv4"
        return
    fi
    
    # Method 5: Last resort - get first non-loopback IPv4
    ipv4=$(ip addr show | grep -oP 'inet \K[\d.]+' | grep -v '127.0.0.1' | head -1)
    if [ -n "$ipv4" ]; then
        echo "$ipv4"
    else
        echo "IP_NOT_FOUND"
    fi
}

# Function to check domain resolution
check_domain_resolution() {
    if [ -n "$DOMAIN_NAME" ]; then
        local resolved_ip=$(dig +short "$DOMAIN_NAME" | head -1)
        local server_ip=$(get_ipv4_address)
        
        if [ "$resolved_ip" = "$server_ip" ]; then
            echo -e "${GREEN}✅ Domain $DOMAIN_NAME correctly points to $server_ip${NC}"
            return 0
        else
            echo -e "${RED}❌ Domain $DOMAIN_NAME points to $resolved_ip but server IP is $server_ip${NC}"
            return 1
        fi
    else
        echo -e "${RED}❌ No domain configured${NC}"
        return 1
    fi
}

# Function to update Cloudflare DNS
update_cloudflare_dns() {
    if [ -z "$CLOUDFLARE_API_KEY" ] || [ -z "$CLOUDFLARE_EMAIL" ] || [ -z "$CLOUDFLARE_ZONE_ID" ] || [ -z "$DOMAIN_NAME" ]; then
        echo -e "${RED}❌ Cloudflare configuration incomplete${NC}"
        return 1
    fi
    
    local server_ip=$(get_ipv4_address)
    
    # Get existing DNS record ID
    local record_info=$(curl -s -X GET "https://api.cloudflare.com/client/v4/zones/$CLOUDFLARE_ZONE_ID/dns_records?type=A&name=$DOMAIN_NAME" \
        -H "X-Auth-Email: $CLOUDFLARE_EMAIL" \
        -H "X-Auth-Key: $CLOUDFLARE_API_KEY" \
        -H "Content-Type: application/json")
    
    local record_id=$(echo "$record_info" | grep -o '"id":"[^"]*' | cut -d'"' -f4)
    
    if [ -n "$record_id" ]; then
        # Update existing record
        local result=$(curl -s -X PUT "https://api.cloudflare.com/client/v4/zones/$CLOUDFLARE_ZONE_ID/dns_records/$record_id" \
            -H "X-Auth-Email: $CLOUDFLARE_EMAIL" \
            -H "X-Auth-Key: $CLOUDFLARE_API_KEY" \
            -H "Content-Type: application/json" \
            --data "{\"type\":\"A\",\"name\":\"$DOMAIN_NAME\",\"content\":\"$server_ip\",\"ttl\":120,\"proxied\":false}")
        
        if echo "$result" | grep -q '"success":true'; then
            echo -e "${GREEN}✅ Cloudflare DNS updated: $DOMAIN_NAME → $server_ip${NC}"
            return 0
        else
            echo -e "${RED}❌ Failed to update Cloudflare DNS${NC}"
            return 1
        fi
    else
        # Create new record
        local result=$(curl -s -X POST "https://api.cloudflare.com/client/v4/zones/$CLOUDFLARE_ZONE_ID/dns_records" \
            -H "X-Auth-Email: $CLOUDFLARE_EMAIL" \
            -H "X-Auth-Key: $CLOUDFLARE_API_KEY" \
            -H "Content-Type: application/json" \
            --data "{\"type\":\"A\",\"name\":\"$DOMAIN_NAME\",\"content\":\"$server_ip\",\"ttl\":120,\"proxied\":false}")
        
        if echo "$result" | grep -q '"success":true'; then
            echo -e "${GREEN}✅ Cloudflare DNS record created: $DOMAIN_NAME → $server_ip${NC}"
            return 0
        else
            echo -e "${RED}❌ Failed to create Cloudflare DNS record${NC}"
            return 1
        fi
    fi
}

# Function to show menu
show_menu() {
   show_header
   echo -e "${WHITE}📋 GX TUNNEL MANAGEMENT MENU${NC}"
   echo -e "${CYAN}┌─────────────────────────────────────────────────────────┐${NC}"
   echo -e "  ${YELLOW}1. ${GREEN}📊 Check Server Status${NC}"
   echo -e "  ${YELLOW}2. ${GREEN}👥 Manage Tunnel Users${NC}" 
   echo -e "  ${YELLOW}3. ${GREEN}🔧 Change Listening Port${NC}"
   echo -e "  ${YELLOW}4. ${GREEN}🔄 Restart GX Tunnel Service${NC}"
   echo -e "  ${YELLOW}5. ${GREEN}📈 View Connection Stats${NC}"
   echo -e "  ${YELLOW}6. ${GREEN}📜 View Service Logs${NC}"
   echo -e "  ${YELLOW}7. ${GREEN}🛑 Stop GX Tunnel Service${NC}"
   echo -e "  ${YELLOW}8. ${GREEN}🚀 Start GX Tunnel Service${NC}"
   echo -e "  ${YELLOW}9. ${GREEN}🌊 Manage UDP Gateway${NC}"
   echo -e "  ${YELLOW}10. ${GREEN}🌐 Manage Domain & Cloudflare${NC}"
   echo -e "  ${YELLOW}11. ${GREEN}⚙️ Generate Client Config${NC}"
   echo -e "  ${YELLOW}12. ${GREEN}ℹ️ Server Information${NC}"
   echo -e "  ${YELLOW}13. ${RED}🗑️ Uninstall GX Tunnel${NC}"
   echo -e "  ${YELLOW}14. ${RED}❌ Exit${NC}"
   echo -e "${CYAN}└─────────────────────────────────────────────────────────┘${NC}"
   echo
}

# Function to check server status
check_server_status() {
   echo -e "${WHITE}📊 GX TUNNEL SERVER STATUS${NC}"
   echo -e "${CYAN}───────────────────────────────────────────────────────────${NC}"
   
   # Check systemd service
   local service_status=$(systemctl is-active $AGN_WEBSOCKET_SERVICE)
   if [ "$service_status" = "active" ]; then
       echo -e "${GREEN}✅ GX Tunnel Service: ${WHITE}Active${NC}"
       
       # Check if process is running
       if pgrep -f "agn_websocket.py" > /dev/null; then
           echo -e "${GREEN}✅ GX Tunnel Process: ${WHITE}Running${NC}"
           
           # Get listening port
           local current_port=$(get_listening_port)
           echo -e "${BLUE}📍 Listening Port: ${WHITE}$current_port${NC}"
           
           # Get process info
           local pid=$(pgrep -f "agn_websocket.py")
           echo -e "${BLUE}🆔 Process ID: ${WHITE}$pid${NC}"
           
           # Check port listening
           if netstat -tulpn 2>/dev/null | grep ":$current_port" > /dev/null; then
               echo -e "${GREEN}🔊 Port $current_port: ${WHITE}Listening${NC}"
           else
               echo -e "${RED}🔇 Port $current_port: ${WHITE}Not listening${NC}"
           fi
       else
           echo -e "${RED}❌ GX Tunnel Process: ${WHITE}Not running${NC}"
       fi
   else
       echo -e "${RED}❌ GX Tunnel Service: ${WHITE}$service_status${NC}"
   fi
   
   # Check domain status
   echo
   echo -e "${WHITE}🌐 DOMAIN STATUS${NC}"
   if [ "$USE_DOMAIN" = "true" ] && [ -n "$DOMAIN_NAME" ]; then
       check_domain_resolution
   else
       echo -e "${YELLOW}ℹ️ Using IP address: ${WHITE}$(get_ipv4_address)${NC}"
   fi
   
   # Check UDP Gateway status
   echo
   check_udpgw_status
   
   # Show recent connections
   show_recent_connections
}

# Function to get listening port
get_listening_port() {
   if [ -f "$PYTHON_SCRIPT_PATH" ]; then
       grep -oP 'LISTENING_PORT\s*=\s*\K[0-9]+' "$PYTHON_SCRIPT_PATH" 2>/dev/null || echo "8098"
   else
       echo "8098"
   fi
}

# Function to show recent connections
show_recent_connections() {
   echo
   echo -e "${WHITE}📈 RECENT ACTIVITY${NC}"
   if [ -f "$LOG_FILE" ]; then
       local recent_conns=$(grep -c "New tunnel" "$LOG_FILE" 2>/dev/null || echo "0")
       local active_conns=$(grep "active_connections" "$LOG_FILE" | tail -1 | grep -oP 'active_connections:\s*\K[0-9]+' || echo "0")
       echo -e "${BLUE}🔄 Total Connections: ${WHITE}$recent_conns${NC}"
       echo -e "${GREEN}🔗 Active Connections: ${WHITE}$active_conns${NC}"
   else
       echo -e "${YELLOW}📝 No log file found${NC}"
   fi
}

# Function to add SSH user (SECURE - tunnel only)
add_ssh_user() {
    echo -e "${WHITE}👤 CREATE NEW TUNNEL USER${NC}"
    echo -e "${CYAN}───────────────────────────────────────────────────────────${NC}"
    
    read -p "Enter username: " username
    
    # Validate username
    if [[ ! "$username" =~ ^[a-z_][a-z0-9_-]*$ ]]; then
        echo -e "${RED}❌ Username can only contain lowercase letters, numbers, hyphens, and underscores${NC}"
        return 1
    fi
    
    read -p "Enter password: " -s password
    echo

    if [ -z "$username" ] || [ -z "$password" ]; then
        echo -e "${RED}❌ Username or password cannot be empty${NC}"
        return 1
    fi

    if id "$username" &>/dev/null; then
        echo -e "${RED}❌ User $username already exists${NC}"
        return 1
    fi

    # Create user with NO SHELL ACCESS (tunnel only)
    if useradd -m -s /usr/sbin/nologin "$username" 2>/dev/null; then
        if echo "$username:$password" | chpasswd 2>/dev/null; then
            # Get server address (IP or Domain)
            SERVER_ADDR=$(get_server_address)
            local port=$(get_listening_port)
            
            echo
            echo -e "${GREEN}✅ User $username successfully created!${NC}"
            echo
            echo -e "${WHITE}🔧 CONNECTION DETAILS${NC}"
            echo -e "${CYAN}───────────────────────────────────────────────────────────${NC}"
            echo -e "${BLUE}📍 WebSocket Endpoint: ${WHITE}ws://$SERVER_ADDR:$port${NC}"
            echo -e "${BLUE}🔌 SSH Server: ${WHITE}$SERVER_ADDR${NC}"
            echo -e "${BLUE}🔑 SSH Port: ${WHITE}22${NC}"
            echo -e "${BLUE}👤 SSH Username: ${WHITE}$username${NC}"
            echo -e "${BLUE}🔒 SSH Password: ${WHITE}[hidden]${NC}"
            echo
            echo -e "${WHITE}📱 FOR NPV APPS${NC}"
            echo -e "${CYAN}───────────────────────────────────────────────────────────${NC}"
            echo -e "${YELLOW}SSH Host: ${WHITE}$SERVER_ADDR${NC}"
            echo -e "${YELLOW}SSH Port: ${WHITE}22${NC}"
            echo -e "${YELLOW}Username: ${WHITE}$username${NC}"
            echo -e "${YELLOW}Password: ${WHITE}[your_password]${NC}"
            echo -e "${YELLOW}Proxy Host: ${WHITE}$SERVER_ADDR${NC}"
            echo -e "${YELLOW}Proxy Port: ${WHITE}$port${NC}"
            echo
            echo -e "${WHITE}🌊 UDP GATEWAY${NC}"
            echo -e "${CYAN}───────────────────────────────────────────────────────────${NC}"
            echo -e "${PURPLE}UDPGw Host: ${WHITE}$SERVER_ADDR${NC}"
            echo -e "${PURPLE}UDPGw Port: ${WHITE}$UDPGW_PORT${NC}"
            return 0
        else
            echo -e "${RED}❌ Failed to set password for user $username${NC}"
            userdel -r "$username" 2>/dev/null
            return 1
        fi
    else
        echo -e "${RED}❌ Failed to create user $username${NC}"
        return 1
    fi
}

# Function to remove SSH user
remove_ssh_user() {
   echo -e "${WHITE}🗑️ REMOVE TUNNEL USER${NC}"
   echo -e "${CYAN}───────────────────────────────────────────────────────────${NC}"
   
   read -p "Enter username to remove: " username

   if ! id "$username" &>/dev/null; then
       echo -e "${RED}❌ User $username does not exist${NC}"
       return 1
   fi

   # Check if user has home directory and UID >= 1000 (regular user)
   user_uid=$(id -u "$username")
   if [ "$user_uid" -ge 1000 ]; then
       read -p "Are you sure you want to remove user $username? (y/n): " confirm
       if [[ $confirm =~ ^[Yy]$ ]]; then
           if userdel -r "$username" 2>/dev/null; then
               echo -e "${GREEN}✅ User $username removed${NC}"
           else
               echo -e "${RED}❌ Failed to remove user $username${NC}"
               return 1
           fi
       else
           echo -e "${YELLOW}❕ User removal cancelled${NC}"
       fi
   else
       echo -e "${RED}❌ Cannot remove system user $username${NC}"
       return 1
   fi
}

# Function to list SSH users
list_ssh_users() {
   echo -e "${WHITE}👥 TUNNEL USERS${NC}"
   echo -e "${CYAN}───────────────────────────────────────────────────────────${NC}"
   
   # Show tunnel users (regular users with nologin shell, UID >= 1000)
   local tunnel_users=$(awk -F: '$3 >= 1000 && $7 ~ /(\/usr\/sbin\/nologin)/ { print $1 }' /etc/passwd)
   if [ -n "$tunnel_users" ]; then
       echo -e "${GREEN}🔐 Tunnel Users (Secure - No Shell):${NC}"
       echo -e "${WHITE}$tunnel_users${NC}"
   else
       echo -e "${YELLOW}🔐 Tunnel Users: None${NC}"
   fi
   echo
   
   # Show shell users (regular users with shell access, UID >= 1000)
   local shell_users=$(awk -F: '$3 >= 1000 && $7 ~ /(\/bin\/bash|\/bin\/sh)/ { print $1 }' /etc/passwd)
   if [ -n "$shell_users" ]; then
       echo -e "${BLUE}💻 Shell Users (Full Access):${NC}"
       echo -e "${WHITE}$shell_users${NC}"
   else
       echo -e "${YELLOW}💻 Shell Users: None${NC}"
   fi
   
   # Count and display totals
   local tunnel_count=$(echo "$tunnel_users" | wc -w)
   local shell_count=$(echo "$shell_users" | wc -w)
   
   echo
   echo -e "${WHITE}📊 SUMMARY${NC}"
   echo -e "${CYAN}───────────────────────────────────────────────────────────${NC}"
   echo -e "${GREEN}Tunnel Users: ${WHITE}$tunnel_count${NC}"
   echo -e "${BLUE}Shell Users: ${WHITE}$shell_count${NC}"
   echo -e "${YELLOW}Total Users: ${WHITE}$((tunnel_count + shell_count))${NC}"
}

# Function to manage SSH users
manage_ssh_users() {
   while true; do
       show_header
       echo -e "${WHITE}👥 TUNNEL USER MANAGEMENT${NC}"
       echo -e "${CYAN}───────────────────────────────────────────────────────────${NC}"
       echo -e "  ${YELLOW}1. ${GREEN}➕ Add Tunnel User${NC}"
       echo -e "  ${YELLOW}2. ${RED}🗑️ Remove Tunnel User${NC}"
       echo -e "  ${YELLOW}3. ${BLUE}📋 List Tunnel Users${NC}"
       echo -e "  ${YELLOW}4. ${YELLOW}↩️ Back to Main Menu${NC}"
       echo -e "${CYAN}───────────────────────────────────────────────────────────${NC}"
       echo

       read -p "Enter your choice: " choice

       case $choice in
           1) add_ssh_user ;;
           2) remove_ssh_user ;;
           3) list_ssh_users ;;
           4) break ;;
           *) echo -e "${RED}❌ Invalid choice${NC}" ;;
       esac

       echo
       read -n 1 -s -r -p "Press any key to continue..."
       echo
   done
}

# Function to change listening port
change_listening_port() {
   local current_port=$(get_listening_port)
   echo -e "${WHITE}🔧 CHANGE LISTENING PORT${NC}"
   echo -e "${CYAN}───────────────────────────────────────────────────────────${NC}"
   echo -e "${YELLOW}Current listening port: ${WHITE}$current_port${NC}"
   read -p "Enter new WebSocket listening port: " new_port

   if ! [[ "$new_port" =~ ^[0-9]+$ ]]; then
       echo -e "${RED}❌ Please enter a valid integer port number${NC}"
       return
   fi

   if [ "$new_port" -lt 1024 ] || [ "$new_port" -gt 65535 ]; then
       echo -e "${RED}❌ Port must be between 1024 and 65535${NC}"
       return
   fi

   if [ -f "$PYTHON_SCRIPT_PATH" ]; then
       # Stop service first
       systemctl stop $AGN_WEBSOCKET_SERVICE 2>/dev/null
       
       # Update port in Python script
       sed -i "s/LISTENING_PORT = [0-9]\+/LISTENING_PORT = $new_port/" "$PYTHON_SCRIPT_PATH"
       echo -e "${GREEN}✅ WebSocket listening port changed to $new_port${NC}"

       # Restart WebSocket service
       restart_websocket_service
   else
       echo -e "${RED}❌ File $PYTHON_SCRIPT_PATH not found${NC}"
   fi
}

# Function to restart WebSocket service
restart_websocket_service() {
   echo -e "${WHITE}🔄 RESTARTING GX TUNNEL SERVICE${NC}"
   echo -e "${CYAN}───────────────────────────────────────────────────────────${NC}"
   systemctl daemon-reload
   systemctl restart $AGN_WEBSOCKET_SERVICE
   sleep 2
   echo -e "${GREEN}✅ Service restarted${NC}"
   echo
   systemctl status $AGN_WEBSOCKET_SERVICE --no-pager
}

# Function to stop WebSocket service
stop_websocket_service() {
   echo -e "${WHITE}🛑 STOPPING GX TUNNEL SERVICE${NC}"
   echo -e "${CYAN}───────────────────────────────────────────────────────────${NC}"
   systemctl stop $AGN_WEBSOCKET_SERVICE
   echo -e "${GREEN}✅ Service stopped${NC}"
   echo
   systemctl status $AGN_WEBSOCKET_SERVICE --no-pager
}

# Function to start WebSocket service
start_websocket_service() {
   echo -e "${WHITE}🚀 STARTING GX TUNNEL SERVICE${NC}"
   echo -e "${CYAN}───────────────────────────────────────────────────────────${NC}"
   systemctl start $AGN_WEBSOCKET_SERVICE
   sleep 2
   echo -e "${GREEN}✅ Service started${NC}"
   echo
   systemctl status $AGN_WEBSOCKET_SERVICE --no-pager
}

# Function to view connection stats
view_connection_stats() {
   echo -e "${WHITE}📈 CONNECTION STATISTICS${NC}"
   echo -e "${CYAN}───────────────────────────────────────────────────────────${NC}"
   
   if [ -f "$LOG_FILE" ]; then
       echo -e "${GREEN}📊 Recent Connections:${NC}"
       grep "New tunnel" "$LOG_FILE" | tail -5
       echo
       echo -e "${BLUE}📈 Active Connections:${NC}"
       grep "active_connections" "$LOG_FILE" | tail -3
       echo
       echo -e "${RED}❌ Recent Errors:${NC}"
       grep -E "(error|Error|ERROR)" "$LOG_FILE" | tail -5
   else
       echo -e "${RED}❌ Log file not found: $LOG_FILE${NC}"
   fi
}

# Function to view service logs
view_service_logs() {
   echo -e "${WHITE}📜 SERVICE LOGS${NC}"
   echo -e "${CYAN}───────────────────────────────────────────────────────────${NC}"
   
   if [ -f "$LOG_FILE" ]; then
       echo -e "${YELLOW}Last 20 lines of log file:${NC}"
       echo -e "${CYAN}───────────────────────────────────────────────────────────${NC}"
       tail -20 "$LOG_FILE"
   else
       echo -e "${RED}❌ Log file not found: $LOG_FILE${NC}"
       echo -e "${YELLOW}💡 To view systemd logs:${NC}"
       journalctl -u $AGN_WEBSOCKET_SERVICE -n 20 --no-pager
   fi
}

# Function to install UDPGw
install_udpgw() {
    echo -e "${WHITE}📦 INSTALLING UDP GATEWAY${NC}"
    echo -e "${CYAN}───────────────────────────────────────────────────────────${NC}"
    
    # Check if already installed
    if [ -f "/usr/local/bin/badvpn-udpgw" ]; then
        echo -e "${YELLOW}ℹ️ UDPGw is already installed${NC}"
        return 0
    fi
    
    # Install dependencies
    echo -e "${BLUE}📥 Installing dependencies...${NC}"
    apt-get update > /dev/null 2>&1
    apt-get install -y build-essential cmake git > /dev/null 2>&1
    
    # Download and compile badvpn
    echo -e "${BLUE}🔨 Compiling UDP Gateway...${NC}"
    cd /tmp
    git clone https://github.com/ambrop72/badvpn.git > /dev/null 2>&1
    if [ $? -ne 0 ]; then
        echo -e "${RED}❌ Failed to download badvpn${NC}"
        return 1
    fi
    
    cd badvpn
    mkdir build
    cd build
    cmake .. -DBUILD_NOTHING_BY_DEFAULT=1 -DBUILD_UDPGW=1 > /dev/null 2>&1
    if [ $? -ne 0 ]; then
        echo -e "${RED}❌ CMake configuration failed${NC}"
        return 1
    fi
    
    make > /dev/null 2>&1
    if [ $? -ne 0 ]; then
        echo -e "${RED}❌ Compilation failed${NC}"
        return 1
    fi
    
    sudo cp udpgw/badvpn-udpgw /usr/local/bin/
    
    # Create systemd service
    sudo tee /etc/systemd/system/udpgw.service > /dev/null <<EOF
[Unit]
Description=UDP Gateway for VPN
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/badvpn-udpgw --listen-addr 0.0.0.0:$UDPGW_PORT
Restart=always
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable udpgw > /dev/null 2>&1
    sudo systemctl start udpgw
    
    echo -e "${GREEN}✅ UDP Gateway installed and started on port $UDPGW_PORT${NC}"
    echo -e "${BLUE}🌊 UDP Gateway allows UDP traffic (gaming, VoIP, DNS) through the tunnel${NC}"
}

# Function to check UDPGw status
check_udpgw_status() {
    echo -e "${WHITE}🌊 UDP GATEWAY STATUS${NC}"
    if systemctl is-active udpgw &>/dev/null; then
        echo -e "${GREEN}✅ Status: ${WHITE}Active${NC}"
        echo -e "${BLUE}📍 Port: ${WHITE}$UDPGW_PORT${NC}"
        echo -e "${BLUE}🔧 Protocol: ${WHITE}UDP-over-TCP${NC}"
        echo -e "${BLUE}🎯 Purpose: ${WHITE}Gaming, VoIP, DNS support${NC}"
    elif [ -f "/usr/local/bin/badvpn-udpgw" ]; then
        echo -e "${YELLOW}❌ Status: ${WHITE}Installed but not running${NC}"
        echo -e "${YELLOW}💡 Run: systemctl start udpgw${NC}"
    else
        echo -e "${RED}❌ Status: ${WHITE}Not installed${NC}"
        echo -e "${YELLOW}💡 Install from main menu option 9${NC}"
    fi
}

# Function to start UDPGw
start_udpgw() {
    echo -e "${WHITE}🚀 STARTING UDP GATEWAY${NC}"
    echo -e "${CYAN}───────────────────────────────────────────────────────────${NC}"
    systemctl start udpgw
    sleep 2
    systemctl status udpgw --no-pager
}

# Function to stop UDPGw
stop_udpgw() {
    echo -e "${WHITE}🛑 STOPPING UDP GATEWAY${NC}"
    echo -e "${CYAN}───────────────────────────────────────────────────────────${NC}"
    systemctl stop udpgw
    systemctl status udpgw --no-pager
}

# Function to restart UDPGw
restart_udpgw() {
    echo -e "${WHITE}🔄 RESTARTING UDP GATEWAY${NC}"
    echo -e "${CYAN}───────────────────────────────────────────────────────────${NC}"
    systemctl restart udpgw
    sleep 2
    systemctl status udpgw --no-pager
}

# Function to uninstall UDPGw
uninstall_udpgw() {
    read -p "Are you sure you want to uninstall UDP Gateway? (y/n): " confirm
    if [[ ! $confirm =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}❕ Uninstall cancelled${NC}"
        return
    fi
    
    echo -e "${WHITE}🗑️ UNINSTALLING UDP GATEWAY${NC}"
    echo -e "${CYAN}───────────────────────────────────────────────────────────${NC}"
    systemctl stop udpgw
    systemctl disable udpgw
    rm -f /etc/systemd/system/udpgw.service
    rm -f /usr/local/bin/badvpn-udpgw
    systemctl daemon-reload
    echo -e "${GREEN}✅ UDP Gateway uninstalled${NC}"
}

# Function to manage UDP Gateway
manage_udpgw() {
   while true; do
       show_header
       echo -e "${WHITE}🌊 UDP GATEWAY MANAGEMENT${NC}"
       echo -e "${CYAN}───────────────────────────────────────────────────────────${NC}"
       echo -e "${BLUE}UDP Gateway allows UDP traffic (gaming, VoIP, DNS) through tunnel${NC}"
       echo
       echo -e "  ${YELLOW}1. ${GREEN}📦 Install UDP Gateway${NC}"
       echo -e "  ${YELLOW}2. ${GREEN}🚀 Start UDP Gateway${NC}"
       echo -e "  ${YELLOW}3. ${RED}🛑 Stop UDP Gateway${NC}"
       echo -e "  ${YELLOW}4. ${GREEN}🔄 Restart UDP Gateway${NC}"
       echo -e "  ${YELLOW}5. ${BLUE}📊 Check UDP Gateway Status${NC}"
       echo -e "  ${YELLOW}6. ${RED}🗑️ Uninstall UDP Gateway${NC}"
       echo -e "  ${YELLOW}7. ${YELLOW}↩️ Back to Main Menu${NC}"
       echo -e "${CYAN}───────────────────────────────────────────────────────────${NC}"
       echo

       read -p "Enter your choice: " choice

       case $choice in
           1) install_udpgw ;;
           2) start_udpgw ;;
           3) stop_udpgw ;;
           4) restart_udpgw ;;
           5) check_udpgw_status ;;
           6) uninstall_udpgw ;;
           7) break ;;
           *) echo -e "${RED}❌ Invalid choice${NC}" ;;
       esac

       echo
       read -n 1 -s -r -p "Press any key to continue..."
       echo
   done
}

# Function to configure domain and Cloudflare
configure_domain() {
    clear
    show_header
    echo -e "${WHITE}🌐 DOMAIN & CLOUDFLARE CONFIGURATION${NC}"
    echo -e "${CYAN}───────────────────────────────────────────────────────────${NC}"
    
    echo -e "${BLUE}Current Configuration:${NC}"
    echo -e "Domain Name: ${WHITE}${DOMAIN_NAME:-Not set}${NC}"
    echo -e "Use Domain: ${WHITE}$USE_DOMAIN${NC}"
    echo -e "Cloudflare API: ${WHITE}${CLOUDFLARE_EMAIL:-Not configured}${NC}"
    echo
    
    echo -e "  ${YELLOW}1. ${GREEN}Set Domain Name${NC}"
    echo -e "  ${YELLOW}2. ${GREEN}Configure Cloudflare API${NC}"
    echo -e "  ${YELLOW}3. ${BLUE}Enable/Disable Domain Usage${NC}"
    echo -e "  ${YELLOW}4. ${YELLOW}Test Domain Resolution${NC}"
    echo -e "  ${YELLOW}5. ${GREEN}Update Cloudflare DNS${NC}"
    echo -e "  ${YELLOW}6. ${YELLOW}↩️ Back to Main Menu${NC}"
    echo -e "${CYAN}───────────────────────────────────────────────────────────${NC}"
    echo
    
    read -p "Enter your choice: " choice
    
    case $choice in
        1)
            read -p "Enter domain name (e.g., vpn.example.com): " DOMAIN_NAME
            save_config
            echo -e "${GREEN}✅ Domain name set to: $DOMAIN_NAME${NC}"
            ;;
        2)
            echo -e "${WHITE}📝 Cloudflare API Configuration${NC}"
            read -p "Cloudflare Email: " CLOUDFLARE_EMAIL
            read -p "Cloudflare API Key: " CLOUDFLARE_API_KEY
            read -p "Cloudflare Zone ID: " CLOUDFLARE_ZONE_ID
            save_config
            echo -e "${GREEN}✅ Cloudflare API configured${NC}"
            ;;
        3)
            if [ "$USE_DOMAIN" = "true" ]; then
                USE_DOMAIN=false
                echo -e "${YELLOW}✅ Domain usage disabled - Using IP address${NC}"
            else
                if [ -n "$DOMAIN_NAME" ]; then
                    USE_DOMAIN=true
                    echo -e "${GREEN}✅ Domain usage enabled - Using: $DOMAIN_NAME${NC}"
                else
                    echo -e "${RED}❌ Please set a domain name first${NC}"
                fi
            fi
            save_config
            ;;
        4)
            check_domain_resolution
            ;;
        5)
            update_cloudflare_dns
            ;;
        6)
            return
            ;;
        *)
            echo -e "${RED}❌ Invalid choice${NC}"
            ;;
    esac
    
    echo
    read -n 1 -s -r -p "Press any key to continue..."
    echo
}

# Function to uninstall proxy script
uninstall_proxy_script() {
   read -p "Are you sure you want to uninstall GX Tunnel? (y/n): " confirm
   if [[ ! $confirm =~ ^[Yy]$ ]]; then
       echo -e "${YELLOW}❕ Uninstall cancelled${NC}"
       return
   fi

   echo -e "${WHITE}🗑️ UNINSTALLING GX TUNNEL${NC}"
   echo -e "${CYAN}───────────────────────────────────────────────────────────${NC}"
   
   echo -e "${RED}🛑 Stopping $AGN_WEBSOCKET_SERVICE service...${NC}"
   systemctl stop $AGN_WEBSOCKET_SERVICE

   echo -e "${RED}❌ Disabling $AGN_WEBSOCKET_SERVICE service...${NC}"
   systemctl disable $AGN_WEBSOCKET_SERVICE

   echo -e "${RED}🗑️ Removing Python proxy files...${NC}"
   rm -rf "/opt/agn_websocket"
   rm -f /usr/local/bin/websocket

   echo -e "${RED}🗑️ Removing systemd service file...${NC}"
   rm -f "/etc/systemd/system/$AGN_WEBSOCKET_SERVICE.service"

   echo -e "${BLUE}🔄 Reloading systemd...${NC}"
   systemctl daemon-reload

   echo -e "${GREEN}✅ GX Tunnel uninstalled successfully${NC}"
}

# Function to display server information
server_information() {
    echo -e "${WHITE}ℹ️ SERVER INFORMATION${NC}"
    echo -e "${CYAN}───────────────────────────────────────────────────────────${NC}"

    # System information
    echo -e "${BLUE}💻 System:${NC}"
    echo -e "  OS: ${WHITE}$(lsb_release -d | cut -f2 2>/dev/null || echo "Unknown")${NC}"
    echo -e "  Kernel: ${WHITE}$(uname -r)${NC}"
    echo -e "  Uptime: ${WHITE}$(uptime -p)${NC}"

    # Check if service is active
    if systemctl is-active --quiet $AGN_WEBSOCKET_SERVICE; then
        echo -e "${GREEN}✅ WebSocket Service Status: ${WHITE}Active${NC}"
        
        # Check if process is actually running
        if pgrep -f "agn_websocket.py" > /dev/null; then
            echo -e "${GREEN}✅ WebSocket Process: ${WHITE}Running${NC}"
        else
            echo -e "${RED}❌ WebSocket Process: ${WHITE}Not running (service issue)${NC}"
        fi
    else
        echo -e "${RED}❌ WebSocket Service Status: ${WHITE}Inactive${NC}"
    fi

    # Display current listening port
    local current_port=$(get_listening_port)
    echo -e "${BLUE}📍 Current Listening Port: ${WHITE}$current_port${NC}"

    # Display server address
    SERVER_ADDR=$(get_server_address)
    if [ "$USE_DOMAIN" = "true" ] && [ -n "$DOMAIN_NAME" ]; then
        echo -e "${BLUE}🌐 Server Domain: ${WHITE}$SERVER_ADDR${NC}"
        check_domain_resolution
    else
        echo -e "${BLUE}🌐 Server IPv4: ${WHITE}$SERVER_ADDR${NC}"
    fi

    # Display number of SSH users
    local tunnel_count=$(awk -F: '$3 >= 1000 && $7 ~ /(\/usr\/sbin\/nologin)/ { count++ } END { print count }' /etc/passwd)
    local shell_count=$(awk -F: '$3 >= 1000 && $7 ~ /(\/bin\/bash|\/bin\/sh)/ { count++ } END { print count }' /etc/passwd)
    echo -e "${BLUE}👥 Users:${NC}"
    echo -e "  Tunnel Users: ${WHITE}$tunnel_count${NC}"
    echo -e "  Shell Users: ${WHITE}$shell_count${NC}"
    echo -e "  Total Users: ${WHITE}$((tunnel_count + shell_count))${NC}"
    
    # Show UDP Gateway status
    echo
    check_udpgw_status
    
    # Show service logs hint
    echo
    echo -e "${YELLOW}🔧 Debug Info:${NC}"
    echo -e "  To check service logs: ${WHITE}journalctl -u $AGN_WEBSOCKET_SERVICE -n 20${NC}"
    echo -e "  To check proxy logs: ${WHITE}tail -f $LOG_FILE${NC}"
}

# Function to generate client config
generate_client_config() {
    local port=$(get_listening_port)
    SERVER_ADDR=$(get_server_address)
    
    if [ "$SERVER_ADDR" = "IP_NOT_FOUND" ]; then
        echo -e "${RED}❌ Could not detect server address${NC}"
        return 1
    fi
    
    echo -e "${WHITE}🌐 CLIENT CONFIGURATION GENERATOR${NC}"
    echo -e "${CYAN}───────────────────────────────────────────────────────────${NC}"
    echo
    echo -e "${BLUE}📍 Server Address: ${WHITE}$SERVER_ADDR${NC}"
    echo -e "${BLUE}🔌 WebSocket Port: ${WHITE}$port${NC}"
    echo -e "${BLUE}🌊 UDP Gateway Port: ${WHITE}$UDPGW_PORT${NC}"
    echo
    
    # HTTP Injector config
    echo -e "${GREEN}📱 HTTP Injector Configuration${NC}"
    echo -e "${CYAN}───────────────────────────────────────────────────────────${NC}"
    echo -e "${WHITE}SSH Host: $SERVER_ADDR${NC}"
    echo -e "${WHITE}SSH Port: 22${NC}"
    echo -e "${WHITE}Proxy Host: $SERVER_ADDR${NC}"
    echo -e "${WHITE}Proxy Port: $port${NC}"
    echo -e "${WHITE}UDP Gateway: Enable${NC}"
    echo -e "${WHITE}UDPGw Host: $SERVER_ADDR${NC}"
    echo -e "${WHITE}UDPGw Port: $UDPGW_PORT${NC}"
    echo -e "${YELLOW}Payload:${NC}"
    echo -e "${WHITE}CONNECT [host_port] HTTP/1.1${NC}"
    echo -e "${WHITE}Host: $SERVER_ADDR:$port${NC}"
    echo -e "${WHITE}X-Online-Host: $SERVER_ADDR:$port${NC}"
    echo -e "${WHITE}X-Forward-Host: $SERVER_ADDR:$port${NC}"
    echo -e "${WHITE}Connection: keep-alive${NC}"
    echo
    
    # KPN Tunnel config
    echo -e "${BLUE}🔧 KPN Tunnel Configuration${NC}"
    echo -e "${CYAN}───────────────────────────────────────────────────────────${NC}"
    echo -e "${WHITE}Host: $SERVER_ADDR${NC}"
    echo -e "${WHITE}Port: 22${NC}"
    echo -e "${WHITE}Proxy: Enable${NC}"
    echo -e "${WHITE}Proxy Host: $SERVER_ADDR${NC}"
    echo -e "${WHITE}Proxy Port: $port${NC}"
    echo -e "${WHITE}UDP Gateway: Enable${NC}"
    echo -e "${WHITE}UDPGw Host: $SERVER_ADDR${NC}"
    echo -e "${WHITE}UDPGw Port: $UDPGW_PORT${NC}"
    echo
    
    # Direct SSH command
    echo -e "${PURPLE}💻 Direct SSH Tunnel${NC}"
    echo -e "${CYAN}───────────────────────────────────────────────────────────${NC}"
    echo -e "${WHITE}ssh -L 8080:localhost:$port username@$SERVER_ADDR${NC}"
    echo -e "${WHITE}Then connect to: http://localhost:8080${NC}"
    echo
    
    # Postern config
    echo -e "${YELLOW}🔧 Postern Configuration${NC}"
    echo -e "${CYAN}───────────────────────────────────────────────────────────${NC}"
    echo -e "${WHITE}Rule Type: HTTP/HTTPS${NC}"
    echo -e "${WHITE}Server: $SERVER_ADDR${NC}"
    echo -e "${WHITE}Port: $port${NC}"
    echo -e "${WHITE}SSH Tunnel: Enable${NC}"
    echo -e "${WHITE}SSH Server: $SERVER_ADDR${NC}"
    echo -e "${WHITE}SSH Port: 22${NC}"
    echo -e "${WHITE}SSH Username: [your_username]${NC}"
    echo -e "${WHITE}SSH Password: [your_password]${NC}"
    echo -e "${WHITE}UDP Gateway: Enable${NC}"
    echo -e "${WHITE}UDPGw Host: $SERVER_ADDR${NC}"
    echo -e "${WHITE}UDPGw Port: $UDPGW_PORT${NC}"
}

# Main function
main() {
   # Load configuration
   load_config
   
   if [ "$1" = "menu" ]; then
       while true; do
           show_menu
           read -p "$(echo -e ${YELLOW}Enter your choice: ${NC})" choice

           case $choice in
               1) check_server_status ;;
               2) manage_ssh_users ;;
               3) change_listening_port ;;
               4) restart_websocket_service ;;
               5) view_connection_stats ;;
               6) view_service_logs ;;
               7) stop_websocket_service ;;
               8) start_websocket_service ;;
               9) manage_udpgw ;;
               10) configure_domain ;;
               11) generate_client_config ;;
               12) server_information ;;
               13) uninstall_proxy_script ;;
               14) echo -e "${GREEN}👋 Exiting GX Tunnel Manager...${NC}"; break ;;
               *) echo -e "${RED}❌ Invalid choice${NC}" ;;
           esac

           echo
           read -n 1 -s -r -p "$(echo -e ${YELLOW}Press any key to continue...${NC})"
           echo
       done
   else
       echo -e "${WHITE}Usage: $0 menu${NC}"
       echo -e "${YELLOW}Available commands:${NC}"
       echo -e "  ${GREEN}menu${NC} - Show GX Tunnel management menu"
   fi
}

# Run main function with arguments
main "$@"
