"""
Network Scanner Service
Scans IP range and identifies devices by their open ports
"""

import socket
import threading
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import serial.tools.list_ports

# Port signatures for device identification
PORT_SIGNATURES = {
    80: "Web Server",
    443: "HTTPS",
    502: "Modbus TCP",
    554: "RTSP Camera",
    6000: "RFID Reader",
    5555: "RFID Reader",
    8080: "HTTP Alt",
    1883: "MQTT",
    9001: "MQTT-WS",
    22: "SSH",
    23: "Telnet",
}

# Priority ports to scan
SCAN_PORTS = [80, 443, 502, 554, 6000, 5555, 8080, 1883, 9001, 22, 23, 8000, 8900, 37777, 34567]


logger = logging.getLogger(__name__)

class NetworkScanner:
    def __init__(self):
        self.scan_results = []
        self.scan_status = {
            "running": False,
            "progress": 0,
            "total": 0,
            "current_ip": "",
            "found": 0
        }
        self.com_ports = []
    
    def get_local_ip(self):
        """Get the local IP address of this machine"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            return local_ip
        except Exception as e:
            logger.info(f"[NetworkScanner] Error getting local IP: {e}")
            return "192.168.1.100"
    
    def get_suggested_ip_range(self):
        """Get suggested IP range based on local IP"""
        local_ip = self.get_local_ip()
        parts = local_ip.split('.')
        
        if len(parts) == 4:
            base = '.'.join(parts[:3])
            return {
                "local_ip": local_ip,
                "start_ip": f"{base}.1",
                "end_ip": f"{base}.254"
            }
        
        return {
            "local_ip": "192.168.1.100",
            "start_ip": "192.168.1.1",
            "end_ip": "192.168.1.254"
        }
    
    def get_status(self):
        """Get current scan status"""
        return self.scan_status
    
    def get_results(self):
        """Get scan results"""
        return {
            "network_devices": self.scan_results,
            "com_ports": self.com_ports
        }
    
    def parse_ip_range(self, start_ip, end_ip):
        """Parse IP range and return list of IPs to scan"""
        ips = []
        
        try:
            # Parse start and end IPs
            start_parts = list(map(int, start_ip.split('.')))
            end_parts = list(map(int, end_ip.split('.')))
            
            # Validate IPs
            if len(start_parts) != 4 or len(end_parts) != 4:
                return []
            
            # Generate IP range
            # Assuming same subnet (first 3 octets same)
            if start_parts[:3] == end_parts[:3]:
                base = '.'.join(map(str, start_parts[:3]))
                for i in range(start_parts[3], end_parts[3] + 1):
                    ips.append(f"{base}.{i}")
            else:
                # Different subnets - just scan between the two
                # This is a simplified version
                base = '.'.join(map(str, start_parts[:3]))
                for i in range(start_parts[3], 255):
                    ips.append(f"{base}.{i}")
        
        except Exception as e:
            logger.info(f"[NetworkScanner] Error parsing IP range: {e}")
        
        return ips
    
    def scan_port(self, ip, port, timeout=0.5):
        """Check if a specific port is open"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((ip, port))
            sock.close()
            return result == 0
        except:
            return False
    
    def scan_single_ip(self, ip):
        """Scan a single IP address"""
        result = {
            "ip": ip,
            "online": False,
            "open_ports": [],
            "device_type": "Unknown",
            "services": {}
        }
        
        open_ports = []
        for port in SCAN_PORTS:
            if self.scan_port(ip, port, timeout=0.3):
                open_ports.append(port)
                result["online"] = True
                result["services"][port] = PORT_SIGNATURES.get(port, f"Port {port}")
        
        if result["online"]:
            result["open_ports"] = open_ports
            result["device_type"] = self.identify_device(open_ports)
        
        return result
    
    def identify_device(self, open_ports):
        """Identify device type based on open ports"""
        # Treat both 6000 and 5555 as RFID reader ports
        if 6000 in open_ports or 5555 in open_ports:
            return "RFID Reader"
        if 554 in open_ports or 37777 in open_ports or 34567 in open_ports:
            return "IP Camera"
        if 502 in open_ports:
            return "Modbus I/O Module"
        if 1883 in open_ports or 9001 in open_ports:
            return "MQTT Broker"
        if 80 in open_ports or 443 in open_ports or 8080 in open_ports:
            return "Web Device"
        if 22 in open_ports:
            return "SSH Device"
        return "Unknown"
    
    def scan_network(self, start_ip, end_ip, max_threads=50):
        """Scan network range"""
        logger.info(f"[NetworkScanner] Starting scan from {start_ip} to {end_ip}")
        
        ips = self.parse_ip_range(start_ip, end_ip)
        
        if not ips:
            return {"error": "Invalid IP range"}
        
        self.scan_results = []
        self.scan_status = {
            "running": True,
            "progress": 0,
            "total": len(ips),
            "current_ip": "",
            "found": 0
        }
        
        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            futures = {executor.submit(self.scan_single_ip, ip): ip for ip in ips}
            
            for i, future in enumerate(as_completed(futures)):
                ip = futures[future]
                self.scan_status["current_ip"] = ip
                self.scan_status["progress"] = i + 1
                
                try:
                    result = future.result()
                    if result["online"]:
                        self.scan_results.append(result)
                        self.scan_status["found"] = len(self.scan_results)
                except Exception as e:
                    logger.info(f"[NetworkScanner] Error scanning {ip}: {e}")
        
        self.scan_status["running"] = False
        self.scan_status["current_ip"] = "Complete"
        
        # Sort results by IP
        self.scan_results.sort(key=lambda x: tuple(map(int, x["ip"].split('.'))))
        
        logger.info(f"[NetworkScanner] Scan complete. Found {len(self.scan_results)} devices")
        return self.scan_results
    
    def scan_com_ports(self):
        """Scan for available COM ports"""
        logger.info("[NetworkScanner] Scanning COM ports...")
        self.com_ports = []
        
        try:
            ports = serial.tools.list_ports.comports()
            for port in ports:
                self.com_ports.append({
                    "port": port.device,      # For JS compatibility
                    "device": port.device,    # Legacy field
                    "description": port.description,
                    "hwid": port.hwid
                })
            logger.info(f"[NetworkScanner] Found {len(self.com_ports)} COM ports")
        except Exception as e:
            logger.info(f"[NetworkScanner] Error scanning COM ports: {e}")
        
        return self.com_ports
    
    def get_devices_by_type(self, device_type):
        """Get devices matching a specific type"""
        return [d for d in self.scan_results if d["device_type"] == device_type]
    
    def get_devices_with_port(self, port):
        """Get devices with a specific port open"""
        return [d for d in self.scan_results if port in d["open_ports"]]
    
    def get_rfid_candidates(self):
        """Get potential RFID devices (ports 6000 or 5555)"""
        # Collect devices with either RFID-related port open
        candidates = []
        candidates.extend(self.get_devices_with_port(6000))
        candidates.extend(self.get_devices_with_port(5555))
        # Remove duplicates by IP
        unique = []
        seen = set()
        for dev in candidates:
            ip = dev.get("ip")
            if ip and ip not in seen:
                seen.add(ip)
                unique.append(dev)
        return unique
    
    def get_camera_candidates(self):
        """Get potential camera devices (port 554)"""
        cameras = self.get_devices_with_port(554)
        cameras.extend(self.get_devices_with_port(37777))
        cameras.extend(self.get_devices_with_port(34567))
        # Remove duplicates
        seen = set()
        unique = []
        for c in cameras:
            if c["ip"] not in seen:
                seen.add(c["ip"])
                unique.append(c)
        return unique
    
    def get_modbus_candidates(self):
        """Get potential Modbus devices (port 502)"""
        return self.get_devices_with_port(502)
    
    def get_server_candidates(self):
        """Get potential server devices (port 80, 8080, 8000)"""
        servers = []
        for device in self.scan_results:
            if any(p in device["open_ports"] for p in [80, 443, 8080, 8000, 8900]):
                servers.append(device)
        return servers
    
    def get_all_ips(self):
        """Get all discovered IPs"""
        return [d["ip"] for d in self.scan_results]

