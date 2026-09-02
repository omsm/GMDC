import requests
import paho.mqtt.client as mqtt
import threading
import time
from requests.exceptions import RequestException, Timeout
import logging

logger = logging.getLogger(__name__)

class DisplayService:
    def __init__(self):
        self.mqtt_client = None
        self.mqtt_connected = False
        self.mqtt_echo_received = False
        self.mqtt_echo_data = None
        self.mqtt_test_message = "Hello, World!"
    
    def check_connection(self, display_type, display_ip, display_port=None):
        """Check display connectivity based on type"""
        if display_type == "api":
            return self._check_api(display_ip, display_port)
        elif display_type == "mqtt":
            return self._check_mqtt(display_ip)
        else:
            return {
                "status": 400,
                "message": f"Unknown display type: {display_type}"
            }
    
    def _check_api(self, display_ip, display_port=None):
        """Check display via API"""
        if not display_ip:
            return {
                "status": 400,
                "message": "Display IP is required"
            }

        port = str(display_port or "8000").strip()
        if not port.isdigit():
            return {
                "status": 400,
                "message": "Display Port must be numeric"
            }

        url = f"http://{display_ip}:{port}/display_data"
        display_payload = {"data": "Hello World"}
        
        try:
            response = requests.post(
                url,
                json=display_payload,
                timeout=10
            )
            
            if response.status_code == 200:
                return {
                    "status": 200,
                    "message": "Display connected successfully via API"
                }
            else:
                return {
                    "status": response.status_code,
                    "message": f"Display responded with status: {response.status_code}"
                }
        
        except Timeout:
            return {
                "status": 408,
                "message": "Connection timed out. Display not responding."
            }
        
        except RequestException as e:
            logger.exception("Display API connectivity check failed for %s:%s", display_ip, port)
            return {
                "status": 500,
                "message": "Unable to connect to Display API. Please verify display IP/port and API availability."
            }
    
    def _check_mqtt(self, display_ip):
        """Check display via MQTT"""
        self.mqtt_echo_received = False
        self.mqtt_echo_data = None
        
        try:
            # Create MQTT client
            self.mqtt_client = mqtt.Client()
            self.mqtt_client.on_connect = self._on_mqtt_connect
            self.mqtt_client.on_message = self._on_mqtt_message
            
            # Connect to broker (localhost:1883)
            self.mqtt_client.connect("localhost", 1883, 60)
            self.mqtt_client.loop_start()
            
            # Wait for connection
            timeout = time.time() + 5
            while not self.mqtt_connected and time.time() < timeout:
                time.sleep(0.1)
            
            if not self.mqtt_connected:
                self._cleanup_mqtt()
                return {
                    "status": 500,
                    "message": "Failed to connect to MQTT broker at localhost:1883"
                }
            
            # Subscribe to response topic
            self.mqtt_client.subscribe("iot_display/display_to_application")
            
            # Publish test message
            test_msg = self.mqtt_test_message
            self.mqtt_client.publish("iot_display/application_to_display", test_msg)
            
            # Wait for echo response (5 seconds)
            timeout = time.time() + 5
            while not self.mqtt_echo_received and time.time() < timeout:
                time.sleep(0.1)
            
            self._cleanup_mqtt()
            
            if self.mqtt_echo_received and self.mqtt_echo_data == test_msg:
                return {
                    "status": 200,
                    "message": "Display connected successfully via MQTT (echo verified)"
                }
            elif self.mqtt_echo_received:
                return {
                    "status": 200,
                    "message": "Display connected via MQTT (received response)"
                }
            else:
                return {
                    "status": 408,
                    "message": "No echo received from display within 5 seconds"
                }
                
        except Exception as e:
            self._cleanup_mqtt()
            logger.exception("Display MQTT connectivity check failed")
            return {
                "status": 500,
                "message": "MQTT validation failed. Please verify broker status and topic configuration."
            }
    
    def _on_mqtt_connect(self, client, userdata, flags, rc):
        """MQTT connection callback"""
        if rc == 0:
            self.mqtt_connected = True
    
    def _on_mqtt_message(self, client, userdata, msg):
        """MQTT message callback"""
        try:
            self.mqtt_echo_data = msg.payload.decode()
            self.mqtt_echo_received = True
        except:
            pass
    
    def _cleanup_mqtt(self):
        """Cleanup MQTT connection"""
        try:
            if self.mqtt_client:
                self.mqtt_client.loop_stop()
                self.mqtt_client.disconnect()
                self.mqtt_client = None
            self.mqtt_connected = False
        except:
            pass
    
    def disconnect(self):
        """Disconnect from display (cleanup all connections)"""
        self._cleanup_mqtt()
        return {"status": 200, "message": "Display disconnected"}

