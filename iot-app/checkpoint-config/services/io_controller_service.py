"""
I/O Controller Service for Modbus TCP/RTU communication.
Supports both direct and relay output modes.
Uses pymodbus for TCP and minimalmodbus for Serial (RTU) communication.
"""

from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException
import serial.tools.list_ports
import time
import logging

from utils.timeout_config_loader import load_timeout_config_module

try:
    from gmdc_common.utils.pymodbus_compat import (
        read_coils_compat,
        read_discrete_inputs_compat,
        read_holding_registers_compat,
        write_coil_compat,
        write_register_compat,
    )
except ImportError:
    # Fallback if gmdc_common not installed - will still fail on new pymodbus
    def read_coils_compat(client, address, count, slave_id=1):
        return client.read_coils(address, count, unit=slave_id)
    def read_discrete_inputs_compat(client, address, count, slave_id=1):
        return client.read_discrete_inputs(address, count, unit=slave_id)
    def read_holding_registers_compat(client, address, count, slave_id=1):
        return client.read_holding_registers(address, count, unit=slave_id)
    def write_coil_compat(client, address, value, slave_id=1):
        return client.write_coil(address, value, unit=slave_id)
    def write_register_compat(client, address, value, slave_id=1):
        return client.write_register(address, value, unit=slave_id)

logger = logging.getLogger(__name__)

_PYMODBUS_LOGGER_NAMES = ("pymodbus", "pymodbus.logging", "pymodbus.client")


class _SuppressPymodbusLogging:
    """Temporarily silence pymodbus ERROR logs during disconnect cleanup."""

    def __enter__(self):
        self._saved = {}
        for name in _PYMODBUS_LOGGER_NAMES:
            log = logging.getLogger(name)
            self._saved[name] = log.level
            log.setLevel(logging.CRITICAL)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        for name, level in self._saved.items():
            logging.getLogger(name).setLevel(level)
        return False


def _load_io_defaults():
    """Load I/O defaults from shared timeout_config.py beside EXE."""
    defaults = {
        "ethernet_port": 502,
        "ethernet_timeout": 1.0,
        "serial_timeout": 0.5,
    }
    module = load_timeout_config_module()
    if module is not None:
        timeouts = getattr(module, "TIMEOUTS", None)
        if timeouts is not None:
            try:
                defaults["ethernet_port"] = int(
                    getattr(timeouts, "IO_CONTROLLER_ETHERNET_PORT", defaults["ethernet_port"])
                )
                defaults["ethernet_timeout"] = float(
                    getattr(timeouts, "IO_CONTROLLER_ETHERNET_TIMEOUT", defaults["ethernet_timeout"])
                )
                defaults["serial_timeout"] = float(
                    getattr(
                        timeouts,
                        "IO_CONTROLLER_SERIAL_TIMEOUT",
                        getattr(timeouts, "SERIAL_TIMEOUT", defaults["serial_timeout"]),
                    )
                )
            except (TypeError, ValueError):
                pass
    return defaults


IO_DEFAULTS = _load_io_defaults()

# Try to import minimalmodbus for serial communication
try:
    import minimalmodbus
    MINIMALMODBUS_AVAILABLE = True
except ImportError:
    MINIMALMODBUS_AVAILABLE = False
    logger.info("[IO] Warning: minimalmodbus not installed. Serial communication will be limited.")


class IOControllerService:
    def __init__(self):
        self.client = None  # For TCP (pymodbus)
        self.instrument = None  # For Serial (minimalmodbus)
        self.connected = False
        self.connection_type = None  # 'tcp' or 'serial'
        self.output_mode = "direct"  # "direct" or "relay"
        self.slave_id = 1
        self.serial_port = None
        self.inter_frame_delay = 0.1  # 100ms delay between frames
    
    
    def get_available_ports(self):
        """Get list of available serial ports"""
        ports = []
        for port in serial.tools.list_ports.comports():
            ports.append({
                "device": port.device,
                "description": port.description
            })
        return ports
    
    def check_connection(self, config):
        """
        Check I/O controller connectivity.
        
        Config format (matching weighbridge_app):
        {
            "type": "ethernet" | "serial",
            "output_mode": "direct" | "relay",
            "connection": {
                "ethernet": { "ip": "", "port": "502", "timeout": "1" },
                "serial": { "port": "", "baud_rate": "9600", ... }
            },
            "slave_id": "1"
        }
        """
        connection_type = config.get('type', 'ethernet')
        self.output_mode = config.get('output_mode', 'direct')
        self.slave_id = int(config.get('slave_id', 1))
        
        # Close existing connection
        self.disconnect()
        
        try:
            if connection_type == 'ethernet':
                return self._connect_tcp(config)
            else:
                return self._connect_serial(config)
        except Exception as e:
            logger.exception("[IO] Connection setup failed")
            return {
                "status": 500,
                "message": "I/O controller connection failed. Please verify communication settings and try again."
            }
    
    def _connect_tcp(self, config):
        """Connect via MODBUS TCP using pymodbus"""
        connection = config.get('connection', {}).get('ethernet', {})
        ip = connection.get('ip', '')
        port = int(connection.get('port', IO_DEFAULTS["ethernet_port"]))
        timeout = float(connection.get('timeout', IO_DEFAULTS["ethernet_timeout"]))
        
        if not ip:
            return {
                "status": 400,
                "message": "IP address is required for Ethernet connection"
            }
        
        try:
            self.client = ModbusTcpClient(host=ip, port=port, timeout=timeout)
            
            if self.client.connect():
                self.connected = True
                self.connection_type = 'tcp'
                
                # Try to read a coil to verify communication
                try:
                    result = read_coils_compat(self.client, 0, 1, self.slave_id)
                    if result.isError():
                        return {
                            "status": 200,
                            "message": "Connected to I/O Controller (verify slave ID)",
                            "type": "MODBUS TCP",
                            "output_mode": self.output_mode,
                            "warning": "Could not read coils - check slave ID"
                        }
                except:
                    pass
                
                # Initialize all relays to LOW/OFF state on connection
                # This prevents relays from being stuck in HIGH state from previous sessions
                try:
                    time.sleep(0.1)  # Small delay after connection
                    # Set all 8 coils (DO1-DO8) to False (LOW/OFF)
                    for coil_addr in range(8):
                        try:
                            write_coil_compat(self.client, coil_addr, False, self.slave_id)
                            time.sleep(0.05)  # Small delay between writes
                        except Exception as e:
                            logger.info(f"[IO] Warning: Could not initialize coil {coil_addr}: {e}")
                    logger.info("[IO] All relays initialized to LOW/OFF state")
                except Exception as e:
                    logger.info(f"[IO] Warning: Could not initialize relays: {e}")
                
                return {
                    "status": 200,
                    "message": "Connected to I/O Controller via MODBUS TCP",
                    "type": "MODBUS TCP",
                    "output_mode": self.output_mode
                }
            else:
                return {
                    "status": 500,
                    "message": f"Failed to connect to {ip}:{port}"
                }
                
        except Exception as e:
            logger.exception("[IO] MODBUS TCP connection failed for %s:%s", ip, port)
            return {
                "status": 500,
                "message": "MODBUS TCP connection failed. Please verify IP, port, slave ID, and network."
            }
    
    def _connect_serial(self, config):
        """Connect via MODBUS RTU using minimalmodbus"""
        if not MINIMALMODBUS_AVAILABLE:
            return {
                "status": 500,
                "message": "minimalmodbus library not installed. Run: pip install minimalmodbus"
            }
        
        connection = config.get('connection', {}).get('serial', {})
        serial_port = connection.get('port', '')
        baud_rate = int(connection.get('baud_rate', 9600))
        bytesize = int(connection.get('bytesize', 8))
        parity = connection.get('parity', 'N')
        stopbits = int(connection.get('stopbits', 1))
        timeout = float(connection.get('timeout', IO_DEFAULTS["serial_timeout"]))
        
        if not serial_port:
            return {
                "status": 400,
                "message": "Serial port is required for Serial connection"
            }
        
        try:
            # Create minimalmodbus instrument
            self.instrument = minimalmodbus.Instrument(serial_port, self.slave_id)
            self.instrument.serial.baudrate = baud_rate
            self.instrument.serial.bytesize = bytesize
            self.instrument.serial.stopbits = stopbits
            self.instrument.serial.timeout = timeout
            self.instrument.mode = minimalmodbus.MODE_RTU
            self.instrument.close_port_after_each_call = False
            
            # Set parity
            if parity == 'N':
                self.instrument.serial.parity = 'N'
            elif parity == 'E':
                self.instrument.serial.parity = 'E'
            elif parity == 'O':
                self.instrument.serial.parity = 'O'
            
            self.serial_port = serial_port
            self.connection_type = 'serial'
            
            # Clear any pending data in the buffer
            self._clear_serial_buffer()
            
            # Verify this is actually an I/O Controller by reading Modbus registers
            # Try multiple reads to ensure it's a real Modbus device
            verification_passed = False
            verification_error = None
            
            try:
                time.sleep(0.1)  # Wait before first read
                
                # Try to read a coil (Function Code 1) - this verifies Modbus communication
                try:
                    value = self.instrument.read_bit(0, functioncode=1)
                    logger.info(f"[IO] Serial connection verified, coil 0 = {value}")
                    verification_passed = True
                except Exception as e1:
                    # If coil read fails, try reading discrete inputs (Function Code 2)
                    try:
                        # Try reading discrete inputs starting from address 0
                        values = self.instrument.read_bits(0, 1, functioncode=2)
                        logger.info(f"[IO] Serial connection verified via discrete inputs, input 0 = {values}")
                        verification_passed = True
                    except Exception as e2:
                        # Both failed - this is likely not an I/O Controller
                        verification_error = f"Coil read failed: {str(e1)}. Discrete input read failed: {str(e2)}"
                        logger.info(f"[IO] Verification failed: {verification_error}")
                
                if verification_passed:
                    self.connected = True
                    return {
                        "status": 200,
                        "message": f"Connected to I/O Controller via MODBUS RTU on {serial_port}",
                        "type": "MODBUS RTU (minimalmodbus)",
                        "output_mode": self.output_mode
                    }
                else:
                    # Verification failed - close connection and return error
                    self.instrument.serial.close()
                    self.instrument = None
                    self.connected = False
                    return {
                        "status": 500,
                        "message": f"COM port {serial_port} opened but Modbus communication failed. This may not be an I/O Controller. Please check that Correct COM port selected, Slave ID matches device ({self.slave_id}), Wiring is correct. Error: {verification_error}"
                    }
                    
            except Exception as e:
                # Unexpected error during verification
                logger.exception("[IO] Serial verification error on %s", serial_port)
                if self.instrument and self.instrument.serial.is_open:
                    self.instrument.serial.close()
                self.instrument = None
                self.connected = False
                return {
                    "status": 500,
                    "message": f"Failed to verify I/O Controller on {serial_port}. Please check COM port, slave ID ({self.slave_id}), and wiring."
                }
                
        except Exception as e:
            logger.exception("[IO] MODBUS RTU setup failed on port %s", serial_port)
            self.connected = False
            self.instrument = None
            return {
                "status": 500,
                "message": "MODBUS RTU connection failed. Please verify COM port, baud rate, slave ID, and wiring."
            }
    
    def _clear_serial_buffer(self):
        """Clear serial buffer"""
        if self.instrument and self.instrument.serial.is_open:
            try:
                self.instrument.serial.reset_input_buffer()
                self.instrument.serial.reset_output_buffer()
            except:
                pass
    
    def _wait_inter_frame_delay(self):
        """Wait between Modbus frames"""
        time.sleep(self.inter_frame_delay)
    
    def test_pin(self, config):
        """
        Test a specific I/O pin using register address.
        
        Config format:
        {
            "pin_type": "input" | "output",
            "register_type": "coil" | "discrete" | "holding",
            "register_address": 0,
            "slave_id": 1,
            "action": "read" | "on" | "off" | "toggle",
            "output_mode": "direct" | "relay",
            "device_type": "traffic_light" | "boom_barrier" | "sensor",
            "device_action": "red" | "green" | "open" | "close"
        }
        """
        if not self.connected:
            return {
                "status": 400,
                "message": "Not connected to I/O controller"
            }
        
        if self.connection_type == 'tcp' and not self.client:
            return {
                "status": 400,
                "message": "TCP client not initialized"
            }
        
        if self.connection_type == 'serial' and not self.instrument:
            return {
                "status": 400,
                "message": "Serial instrument not initialized"
            }
        
        pin_type = config.get('pin_type', 'output')
        register_type = config.get('register_type', 'coil')
        action = config.get('action', 'read')
        output_mode = config.get('output_mode', self.output_mode)
        device_type = config.get('device_type', '')
        device_action = config.get('device_action', '')
        
        # Safe parsing of register_address with validation
        try:
            raw_addr = config.get('register_address')
            if raw_addr is None or raw_addr == '' or raw_addr == 'null':
                return {
                    "status": 400,
                    "message": "Invalid register address: value is empty or null"
                }
            register_address = int(float(raw_addr))
            if register_address < 0 or register_address > 65535:
                return {
                    "status": 400,
                    "message": f"Invalid register address: {register_address} (must be 0-65535)"
                }
        except (ValueError, TypeError) as e:
            logger.exception("[IO] Invalid register address input: %s", config.get('register_address'))
            return {
                "status": 400,
                "message": f"Invalid register address: {config.get('register_address')}. Please enter a numeric value between 0 and 65535."
            }
        
        # Safe parsing of slave_id
        try:
            raw_slave = config.get('slave_id', self.slave_id)
            if raw_slave is None:
                raw_slave = self.slave_id
            slave_id = int(float(raw_slave))
            if slave_id < 1 or slave_id > 247:
                return {
                    "status": 400,
                    "message": f"Invalid slave ID: {slave_id} (must be 1-247)"
                }
        except (ValueError, TypeError):
            slave_id = self.slave_id
        
        try:
            # Log the test_pin operation details
            function_code = config.get('function_code')
            logger.debug(f"[Modbus test_pin] Pin Type: {pin_type}, Register Type: {register_type}, Register Address: {register_address}, Pin Number: {register_address}, Slave ID: {slave_id}, Action: {action}, Function Code: {function_code}")
            
            if pin_type == 'input':
                # Allow function_code to override register_type for sensors
                return self._read_input(register_type, register_address, slave_id, function_code=function_code)
            else:
                # Handle relay mode logic for outputs
                if output_mode == 'relay' and device_type and device_action:
                    return self._test_relay_output(
                        register_address, slave_id, device_type, device_action
                    )
                else:
                    return self._test_direct_output(
                        register_type, register_address, slave_id, action
                    )
                    
        except Exception as e:
            logger.exception("[IO] test_pin failed")
            return {
                "status": 500,
                "message": "Pin test failed. Please verify pin mapping and controller connectivity."
            }
    
    def _read_input(self, register_type, register_address, slave_id, function_code=None):
        """
        Read input register.
        
        Args:
            register_type: 'coil' or 'discrete' (used if function_code not provided)
            register_address: Modbus address to read
            slave_id: Modbus slave ID
            function_code: Optional function code (1=Read Coils, 2=Read Discrete Inputs)
                         If provided, overrides register_type
        """
        try:
            # Determine function code: use provided function_code, or derive from register_type
            if function_code is not None:
                fc = int(function_code)
                if fc not in [1, 2]:
                    fc = 2  # Default to 2 if invalid
                use_coils = (fc == 1)
            else:
                # Fallback to register_type if function_code not provided
                use_coils = (register_type == 'coil')
                fc = 1 if use_coils else 2
            
            # Log the Modbus operation details
            logger.debug(f"[Modbus Read] Function Code: {fc}, Register Address: {register_address}, Slave ID: {slave_id}, Register Type: {register_type}, Pin Number: {register_address}")
            
            if self.connection_type == 'serial':
                # Use minimalmodbus for serial
                self._wait_inter_frame_delay()
                self._clear_serial_buffer()
                
                # Update slave address if different
                if self.instrument.address != slave_id:
                    self.instrument.address = slave_id
                
                # Use read_bits() instead of read_bit() for better RS485 reliability
                start_address = int(register_address)
                
                if use_coils:
                    # Function code 1: Read coils
                    # For outputs, keep the original behavior (read from 0)
                    read_count = max(start_address + 1, 3)
                    all_bits = self.instrument.read_bits(0, read_count, functioncode=1)
                    # Extract the specific bit we need
                    if start_address < len(all_bits):
                        value = all_bits[start_address]
                    else:
                        # Fallback
                        value = self.instrument.read_bit(register_address, functioncode=1)
                else:
                    # Function code 2: Read discrete inputs
                    # For inputs: read starting from the requested address
                    # If register_address = 0, read_bits(0, 1, functioncode=2)
                    # If register_address = 1, read_bits(1, 2, functioncode=2)
                    # If register_address = 2, read_bits(2, 3, functioncode=2)
                    read_count = start_address + 1
                    all_bits = self.instrument.read_bits(start_address, read_count, functioncode=2)
                    # The first bit in the result is the one we need
                    value = all_bits[0] if len(all_bits) > 0 else False
                
                logger.info(f"[IO Serial] Read input address {register_address} using function code {fc}: {value}")
                if not use_coils:  # Only print for discrete inputs
                    logger.info(f"[IO Serial] All bits read ({start_address}-{start_address + read_count - 1}): {all_bits}")
                
                return {
                    "status": 200,
                    "message": f"Input address {register_address} state: {'HIGH' if value else 'LOW'} (FC{fc})",
                    "value": bool(value)
                }
            else:
                # Use pymodbus for TCP
                if use_coils:
                    # Function Code 1: Read Coils
                    result = read_coils_compat(self.client, register_address, 1, slave_id)
                else:
                    # Function Code 2: Read Discrete Inputs
                    result = read_discrete_inputs_compat(self.client, register_address, 1, slave_id)
                
                if result.isError():
                    return {
                        "status": 500,
                        "message": f"Failed to read input at address {register_address} using function code {fc}: {result}"
                    }
                
                value = result.bits[0]
                logger.info(f"[IO TCP] Read input address {register_address} using function code {fc}: {value}")
                
                return {
                    "status": 200,
                    "message": f"Input address {register_address} state: {'HIGH' if value else 'LOW'} (FC{fc})",
                    "value": value
                }
                
        except Exception as e:
            logger.exception("[IO] Failed reading input at address %s", register_address)
            return {
                "status": 500,
                "message": f"Failed to read input at address {register_address}. Please verify function code and address mapping."
            }
    
    def _test_direct_output(self, register_type, register_address, slave_id, action):
        """Test output in direct mode (separate pins for each light/action)"""
        try:
            if self.connection_type == 'serial':
                return self._test_direct_output_serial(register_type, register_address, slave_id, action)
            else:
                return self._test_direct_output_tcp(register_type, register_address, slave_id, action)
        except Exception as e:
            logger.exception("[IO] Direct output test failed at address %s", register_address)
            return {
                "status": 500,
                "message": "Output test failed. Please verify output pin mapping and controller connectivity."
            }
    
    def _test_direct_output_serial(self, register_type, register_address, slave_id, action):
        """Test output using minimalmodbus (serial)"""
        # Determine function code based on register_type
        if register_type == 'holding':
            fc = 3  # Read Holding Registers
        else:
            fc = 5 if action != 'read' else 1  # Write Single Coil (5) or Read Coils (1)
        logger.debug(f"[Modbus Serial Output] Function Code: {fc}, Register Address: {register_address}, Pin Number: {register_address}, Slave ID: {slave_id}, Action: {action}, Register Type: {register_type}")
        
        self._wait_inter_frame_delay()
        self._clear_serial_buffer()
        
        # Update slave address if different
        if self.instrument.address != slave_id:
            self.instrument.address = slave_id
        
        if action == 'read':
            if register_type == 'holding':
                value = self.instrument.read_register(register_address, functioncode=3)
                return {
                    "status": 200,
                    "message": f"Output address {register_address} value: {value}",
                    "value": value > 0
                }
            else:
                # Use read_bits() for better RS485 reliability
                # Read from 0 to cover the requested address
                read_count = max(int(register_address) + 1, 3)
                all_bits = self.instrument.read_bits(0, read_count, functioncode=1)
                value = all_bits[int(register_address)] if int(register_address) < len(all_bits) else False
                return {
                    "status": 200,
                    "message": f"Output address {register_address} state: {'ON' if value else 'OFF'}",
                    "value": bool(value)
                }
        
        elif action == 'on':
            if register_type == 'holding':
                self.instrument.write_register(register_address, 1, functioncode=6)
            else:
                self.instrument.write_bit(register_address, 1, functioncode=5)
            
            logger.info(f"[IO Serial] Write ON to address {register_address}")
            return {
                "status": 200,
                "message": f"Output address {register_address} turned ON"
            }
        
        elif action == 'off':
            if register_type == 'holding':
                self.instrument.write_register(register_address, 0, functioncode=6)
            else:
                self.instrument.write_bit(register_address, 0, functioncode=5)
            
            logger.info(f"[IO Serial] Write OFF to address {register_address}")
            return {
                "status": 200,
                "message": f"Output address {register_address} turned OFF"
            }
        
        elif action == 'toggle':
            current_value = self.instrument.read_bit(register_address, functioncode=1)
            new_state = 0 if current_value else 1
            
            self._wait_inter_frame_delay()
            self.instrument.write_bit(register_address, new_state, functioncode=5)
            
            logger.info(f"[IO Serial] Toggle address {register_address} to {new_state}")
            return {
                "status": 200,
                "message": f"Output address {register_address} toggled to {'ON' if new_state else 'OFF'}"
            }
        
        return {"status": 400, "message": f"Unknown action: {action}"}
    
    def _test_direct_output_tcp(self, register_type, register_address, slave_id, action):
        """Test output using pymodbus (TCP)"""
        # Determine function code based on register_type
        if register_type == 'holding':
            fc = 3  # Read Holding Registers
        else:
            fc = 1  # Read Coils
        logger.debug(f"[Modbus TCP Output] Function Code: {fc}, Register Address: {register_address}, Pin Number: {register_address}, Slave ID: {slave_id}, Action: {action}, Register Type: {register_type}")
        
        if action == 'read':
            if register_type == 'holding':
                result = read_holding_registers_compat(self.client, register_address, 1, slave_id)
                if result.isError():
                    return {
                        "status": 500,
                        "message": f"Failed to read output at address {register_address}"
                    }
                return {
                    "status": 200,
                    "message": f"Output address {register_address} value: {result.registers[0]}",
                    "value": result.registers[0] > 0
                }
            else:
                result = read_coils_compat(self.client, register_address, 1, slave_id)
                if result.isError():
                    return {
                        "status": 500,
                        "message": f"Failed to read output at address {register_address}"
                    }
                return {
                    "status": 200,
                    "message": f"Output address {register_address} state: {'ON' if result.bits[0] else 'OFF'}",
                    "value": result.bits[0]
                }
        
        elif action == 'on':
            if register_type == 'holding':
                result = write_register_compat(self.client, register_address, 1, slave_id)
            else:
                result = write_coil_compat(self.client, register_address, True, slave_id)
            
            logger.info(f"[IO TCP] Write ON to address {register_address}: {result}")
            
            if result.isError():
                # Some devices return minimal responses that pymodbus can't parse, but the write still succeeds
                # Check for specific parsing errors - if it's a parsing error, assume success (user will verify)
                error_str = str(result).lower()
                if "unpack" in error_str or "unable to decode" in error_str or "buffer" in error_str:
                    # Parsing error but command was sent - return success, user will verify manually
                    logger.info(f"[IO TCP] Write ON command sent (parsing error ignored - user will verify)")
                    return {
                        "status": 200,
                        "message": f"Output address {register_address} turned ON (command sent - please verify)"
                    }
                return {
                    "status": 500,
                    "message": f"Failed to turn ON address {register_address}"
                }
            return {
                "status": 200,
                "message": f"Output address {register_address} turned ON"
            }
        
        elif action == 'off':
            if register_type == 'holding':
                result = write_register_compat(self.client, register_address, 0, slave_id)
            else:
                result = write_coil_compat(self.client, register_address, False, slave_id)
            
            logger.info(f"[IO TCP] Write OFF to address {register_address}: {result}")
            
            if result.isError():
                # Some devices return minimal responses that pymodbus can't parse, but the write still succeeds
                # Check for specific parsing errors - if it's a parsing error, assume success (user will verify)
                error_str = str(result).lower()
                if "unpack" in error_str or "unable to decode" in error_str or "buffer" in error_str:
                    # Parsing error but command was sent - return success, user will verify manually
                    logger.info(f"[IO TCP] Write OFF command sent (parsing error ignored - user will verify)")
                    return {
                        "status": 200,
                        "message": f"Output address {register_address} turned OFF (command sent - please verify)"
                    }
                return {
                    "status": 500,
                    "message": f"Failed to turn OFF address {register_address}"
                }
            return {
                "status": 200,
                "message": f"Output address {register_address} turned OFF"
            }
        
        elif action == 'toggle':
            result = read_coils_compat(self.client, register_address, 1, slave_id)
            if result.isError():
                return {
                    "status": 500,
                    "message": f"Failed to read address {register_address} for toggle"
                }
            new_state = not result.bits[0]
            result = write_coil_compat(self.client, register_address, new_state, slave_id)
            
            logger.info(f"[IO TCP] Toggle address {register_address} to {new_state}: {result}")
            
            if result.isError():
                # Some devices return minimal responses that pymodbus can't parse, but the write still succeeds
                # Check for specific parsing errors - if it's a parsing error, assume success (user will verify)
                error_str = str(result).lower()
                if "unpack" in error_str or "unable to decode" in error_str or "buffer" in error_str:
                    # Parsing error but command was sent - return success, user will verify manually
                    logger.info(f"[IO TCP] Toggle command sent (parsing error ignored - user will verify)")
                    return {
                        "status": 200,
                        "message": f"Output address {register_address} toggled to {'ON' if new_state else 'OFF'} (command sent - please verify)"
                    }
                return {
                    "status": 500,
                    "message": f"Failed to toggle address {register_address}"
                }
            
            return {
                "status": 200,
                "message": f"Output address {register_address} toggled to {'ON' if new_state else 'OFF'}"
            }
        
        return {"status": 400, "message": f"Unknown action: {action}"}
    
    def _test_relay_output(self, register_address, slave_id, device_type, device_action):
        """
        Test output in relay mode (single pin controls relay with NO/NC contacts).
        
        Relay logic:
        - Traffic Light: Relay ON (HIGH) = RED (NO contact), Relay OFF (LOW) = GREEN (NC contact)
        - Boom Barrier: Relay ON (HIGH) = OPEN (NO contact), Relay OFF (LOW) = CLOSE (NC contact)
        """
        if device_type == 'traffic_light':
            if device_action == 'red':
                coil_value = True
                state_name = "RED (Relay ON)"
            else:  # green
                coil_value = False
                state_name = "GREEN (Relay OFF)"
        
        elif device_type == 'boom_barrier':
            if device_action == 'open':
                coil_value = True
                state_name = "OPEN (Relay ON)"
            else:  # close
                coil_value = False
                state_name = "CLOSE (Relay OFF)"
        
        else:
            return {
                "status": 400,
                "message": f"Unknown device type: {device_type}"
            }
        
        try:
            if self.connection_type == 'serial':
                self._wait_inter_frame_delay()
                self._clear_serial_buffer()
                
                if self.instrument.address != slave_id:
                    self.instrument.address = slave_id
                
                self.instrument.write_bit(register_address, 1 if coil_value else 0, functioncode=5)
                logger.info(f"[IO Serial] Relay mode: Set address {register_address} to {coil_value} ({state_name})")
            else:
                result = write_coil_compat(self.client, register_address, coil_value, slave_id)
                logger.info(f"[IO TCP] Relay mode: Set address {register_address} to {coil_value} ({state_name})")
                
                if result.isError():
                    # Some devices return minimal responses that pymodbus can't parse, but the write still succeeds
                    # Check for specific parsing errors - if it's a parsing error, assume success (user will verify)
                    error_str = str(result).lower()
                    if "unpack" in error_str or "unable to decode" in error_str or "buffer" in error_str:
                        # Parsing error but command was sent - return success, user will verify manually
                        logger.info(f"[IO TCP] Relay write command sent (parsing error ignored - user will verify)")
                    else:
                        return {
                            "status": 500,
                            "message": f"Failed to set {device_type} to {device_action}"
                        }
            
            return {
                "status": 200,
                "message": f"{device_type.replace('_', ' ').title()} set to {state_name}"
            }
            
        except Exception as e:
            logger.exception("[IO] Relay output test failed for %s:%s", device_type, device_action)
            return {
                "status": 500,
                "message": f"Failed to set {device_type} to {device_action}. Please verify relay mapping and device wiring."
            }
    
    def test_traffic_light(self, config):
        """
        Test traffic light with mode awareness.
        
        Config:
        {
            "mode": "direct" | "relay",
            "location": "entry" | "exit",
            "action": "red" | "green" | "off",
            "pins": { "red_pin": 0, "green_pin": 1 } | { "pin": 0 },
            "slave_id": 1
        }
        """
        if not self.connected:
            return {
                "status": 400,
                "message": "Not connected to I/O controller"
            }
        
        mode = config.get('mode', 'direct')
        location = config.get('location', 'entry')
        action = config.get('action', 'red')
        pins = config.get('pins', {})
        slave_id = int(config.get('slave_id', self.slave_id))
        
        try:
            if mode == 'relay':
                pin = int(pins.get('pin', 0))
                
                if action == 'red':
                    coil_value = 0
                    state = "RED (Relay OFF → NC contact)"
                elif action == 'green':
                    coil_value = 1
                    state = "GREEN (Relay ON → NO contact)"
                else:  # off
                    coil_value = 0
                    state = "OFF (Relay OFF)"
                
                if self.connection_type == 'serial':
                    self._wait_inter_frame_delay()
                    self._clear_serial_buffer()
                    if self.instrument.address != slave_id:
                        self.instrument.address = slave_id
                    self.instrument.write_bit(pin, coil_value, functioncode=5)
                else:
                    result = write_coil_compat(self.client, pin, bool(coil_value), slave_id)
                    if result.isError():
                        # Some devices return minimal responses that pymodbus can't parse, but the write still succeeds
                        # Check for specific parsing errors - if it's a parsing error, assume success (user will verify)
                        error_str = str(result).lower()
                        if "unpack" in error_str or "unable to decode" in error_str or "buffer" in error_str:
                            # Parsing error but command was sent - return success, user will verify manually
                            logger.info(f"[IO TCP] Traffic light command sent (parsing error ignored - user will verify)")
                        else:
                            return {"status": 500, "message": f"Failed to set {location} traffic light"}
                
                return {
                    "status": 200,
                    "message": f"{location.title()} Traffic Light: {state}"
                }
            
            else:  # direct mode
                red_pin = int(pins.get('red_pin', 0))
                green_pin = int(pins.get('green_pin', 1))
                
                if self.connection_type == 'serial':
                    self._wait_inter_frame_delay()
                    self._clear_serial_buffer()
                    if self.instrument.address != slave_id:
                        self.instrument.address = slave_id
                    
                    if action == 'red':
                        self.instrument.write_bit(red_pin, 1, functioncode=5)
                        self._wait_inter_frame_delay()
                        self.instrument.write_bit(green_pin, 0, functioncode=5)
                        state = "RED (red_pin=ON, green_pin=OFF)"
                    elif action == 'green':
                        self.instrument.write_bit(red_pin, 0, functioncode=5)
                        self._wait_inter_frame_delay()
                        self.instrument.write_bit(green_pin, 1, functioncode=5)
                        state = "GREEN (red_pin=OFF, green_pin=ON)"
                    else:  # off
                        self.instrument.write_bit(red_pin, 0, functioncode=5)
                        self._wait_inter_frame_delay()
                        self.instrument.write_bit(green_pin, 0, functioncode=5)
                        state = "OFF (all pins OFF)"
                else:
                    if action == 'red':
                        result1 = write_coil_compat(self.client, red_pin, True, slave_id)
                        result2 = write_coil_compat(self.client, green_pin, False, slave_id)
                        # Check for parsing errors and verify if needed
                        if result1.isError() or result2.isError():
                            error1_str = str(result1).lower() if result1.isError() else ""
                            error2_str = str(result2).lower() if result2.isError() else ""
                            # If it's a parsing error, ignore it (user will verify)
                            if not (("unpack" in error1_str or "unable to decode" in error1_str or "buffer" in error1_str) and
                                    ("unpack" in error2_str or "unable to decode" in error2_str or "buffer" in error2_str or not result2.isError())):
                                # Real error, not just parsing
                                if result1.isError() and not ("unpack" in error1_str or "unable to decode" in error1_str or "buffer" in error1_str):
                                    return {"status": 500, "message": f"Failed to set {location} traffic light to RED"}
                                if result2.isError() and not ("unpack" in error2_str or "unable to decode" in error2_str or "buffer" in error2_str):
                                    return {"status": 500, "message": f"Failed to set {location} traffic light to RED"}
                        state = "RED (red_pin=ON, green_pin=OFF)"
                    elif action == 'green':
                        result1 = write_coil_compat(self.client, red_pin, False, slave_id)
                        result2 = write_coil_compat(self.client, green_pin, True, slave_id)
                        # Check for parsing errors and verify if needed
                        if result1.isError() or result2.isError():
                            error1_str = str(result1).lower() if result1.isError() else ""
                            error2_str = str(result2).lower() if result2.isError() else ""
                            # If it's a parsing error, ignore it (user will verify)
                            if not (("unpack" in error1_str or "unable to decode" in error1_str or "buffer" in error1_str) and
                                    ("unpack" in error2_str or "unable to decode" in error2_str or "buffer" in error2_str or not result2.isError())):
                                # Real error, not just parsing
                                if result1.isError() and not ("unpack" in error1_str or "unable to decode" in error1_str or "buffer" in error1_str):
                                    return {"status": 500, "message": f"Failed to set {location} traffic light to GREEN"}
                                if result2.isError() and not ("unpack" in error2_str or "unable to decode" in error2_str or "buffer" in error2_str):
                                    return {"status": 500, "message": f"Failed to set {location} traffic light to GREEN"}
                        state = "GREEN (red_pin=OFF, green_pin=ON)"
                    else:  # off
                        result1 = write_coil_compat(self.client, red_pin, False, slave_id)
                        result2 = write_coil_compat(self.client, green_pin, False, slave_id)
                        # Check for parsing errors and verify if needed
                        if result1.isError() or result2.isError():
                            error1_str = str(result1).lower() if result1.isError() else ""
                            error2_str = str(result2).lower() if result2.isError() else ""
                            # If it's a parsing error, ignore it (user will verify)
                            if not (("unpack" in error1_str or "unable to decode" in error1_str or "buffer" in error1_str) and
                                    ("unpack" in error2_str or "unable to decode" in error2_str or "buffer" in error2_str or not result2.isError())):
                                # Real error, not just parsing
                                if result1.isError() and not ("unpack" in error1_str or "unable to decode" in error1_str or "buffer" in error1_str):
                                    return {"status": 500, "message": f"Failed to set {location} traffic light to OFF"}
                                if result2.isError() and not ("unpack" in error2_str or "unable to decode" in error2_str or "buffer" in error2_str):
                                    return {"status": 500, "message": f"Failed to set {location} traffic light to OFF"}
                        state = "OFF (all pins OFF)"
                
                return {
                    "status": 200,
                    "message": f"{location.title()} Traffic Light: {state}"
                }
                
        except Exception as e:
            logger.exception("[IO] Traffic light test failed")
            return {"status": 500, "message": "Traffic light test failed. Please verify pin mapping and output mode."}
    
    def test_boom_barrier(self, config):
        """
        Test boom barrier with mode awareness.
        
        Config:
        {
            "mode": "direct" | "relay",
            "location": "entry" | "exit",
            "action": "open" | "close",
            "pins": { "open_pin": 4, "close_pin": 5 } | { "pin": 2 },
            "slave_id": 1
        }
        """
        if not self.connected:
            return {
                "status": 400,
                "message": "Not connected to I/O controller"
            }
        
        mode = config.get('mode', 'direct')
        location = config.get('location', 'entry')
        action = config.get('action', 'open')
        pins = config.get('pins', {})
        slave_id = int(config.get('slave_id', self.slave_id))
        
        try:
            if mode == 'relay':
                pin = int(pins.get('pin', 0))
                
                if action == 'open':
                    coil_value = 1
                    state = "OPEN (Relay ON → NO contact)"
                else:  # close
                    coil_value = 0
                    state = "CLOSE (Relay OFF → NC contact)"
                
                if self.connection_type == 'serial':
                    self._wait_inter_frame_delay()
                    self._clear_serial_buffer()
                    if self.instrument.address != slave_id:
                        self.instrument.address = slave_id
                    self.instrument.write_bit(pin, coil_value, functioncode=5)
                else:
                    result = write_coil_compat(self.client, pin, bool(coil_value), slave_id)
                    if result.isError():
                        # Some devices return minimal responses that pymodbus can't parse, but the write still succeeds
                        # Check for specific parsing errors - if it's a parsing error, assume success (user will verify)
                        error_str = str(result).lower()
                        if "unpack" in error_str or "unable to decode" in error_str or "buffer" in error_str:
                            # Parsing error but command was sent - return success, user will verify manually
                            logger.info(f"[IO TCP] Boom barrier command sent (parsing error ignored - user will verify)")
                        else:
                            return {"status": 500, "message": f"Failed to {action} {location} barrier"}
                
                return {
                    "status": 200,
                    "message": f"{location.title()} Boom Barrier: {state}"
                }
            
            else:  # direct mode
                open_pin = int(pins.get('open_pin', 0))
                close_pin_val = pins.get('close_pin')
                if close_pin_val is None:
                    close_pin = open_pin + 1  # Default to next pin if not specified
                else:
                    close_pin = int(close_pin_val)
                
                if self.connection_type == 'serial':
                    self._wait_inter_frame_delay()
                    self._clear_serial_buffer()
                    if self.instrument.address != slave_id:
                        self.instrument.address = slave_id
                    
                    if action == 'open':
                        self.instrument.write_bit(open_pin, 1, functioncode=5)
                        self._wait_inter_frame_delay()
                        self.instrument.write_bit(close_pin, 0, functioncode=5)
                        state = "OPEN (open_pin=ON, close_pin=OFF)"
                    else:  # close
                        self.instrument.write_bit(open_pin, 0, functioncode=5)
                        self._wait_inter_frame_delay()
                        self.instrument.write_bit(close_pin, 1, functioncode=5)
                        state = "CLOSE (open_pin=OFF, close_pin=ON)"
                else:
                    if action == 'open':
                        result1 = write_coil_compat(self.client, open_pin, True, slave_id)
                        result2 = write_coil_compat(self.client, close_pin, False, slave_id)
                        # Check for parsing errors and ignore if it's just a parsing issue
                        if result1.isError():
                            error1_str = str(result1).lower()
                            if not ("unpack" in error1_str or "unable to decode" in error1_str or "buffer" in error1_str):
                                return {"status": 500, "message": f"Failed to open {location} barrier"}
                        if result2.isError():
                            error2_str = str(result2).lower()
                            if not ("unpack" in error2_str or "unable to decode" in error2_str or "buffer" in error2_str):
                                return {"status": 500, "message": f"Failed to open {location} barrier"}
                        state = "OPEN (open_pin=ON, close_pin=OFF)"
                    else:  # close
                        result1 = write_coil_compat(self.client, open_pin, False, slave_id)
                        result2 = write_coil_compat(self.client, close_pin, True, slave_id)
                        # Check for parsing errors and ignore if it's just a parsing issue
                        if result1.isError():
                            error1_str = str(result1).lower()
                            if not ("unpack" in error1_str or "unable to decode" in error1_str or "buffer" in error1_str):
                                return {"status": 500, "message": f"Failed to close {location} barrier"}
                        if result2.isError():
                            error2_str = str(result2).lower()
                            if not ("unpack" in error2_str or "unable to decode" in error2_str or "buffer" in error2_str):
                                return {"status": 500, "message": f"Failed to close {location} barrier"}
                        state = "CLOSE (open_pin=OFF, close_pin=ON)"
                
                return {
                    "status": 200,
                    "message": f"{location.title()} Boom Barrier: {state}"
                }
                
        except Exception as e:
            logger.exception("[IO] Boom barrier test failed")
            return {"status": 500, "message": "Boom barrier test failed. Please verify pin mapping and output mode."}
    
    def test_sensor(self, config):
        """
        Test sensor reading.
        
        Config:
        {
            "name": "sensor1",
            "pin": 0,
            "default_signal": "low",
            "slave_id": 1,
            "function_code": 1 or 2  # 1 = Read Coils, 2 = Read Discrete Inputs (default: 2)
        }
        """
        if not self.connected:
            return {
                "status": 400,
                "message": "Not connected to I/O controller"
            }
        
        name = config.get('name', 'sensor')
        pin = int(config.get('pin', 0))
        default_signal = config.get('default_signal', 'low')
        slave_id = int(config.get('slave_id', self.slave_id))
        
        # Get function_code from config (default to 2 for backward compatibility)
        # Function Code 1 = Read Coils, Function Code 2 = Read Discrete Inputs
        function_code = int(config.get('function_code', 2))
        if function_code not in [1, 2]:
            function_code = 2  # Default to 2 if invalid
        
        # Log the sensor test operation details
        logger.debug(f"[Modbus test_sensor] Sensor Name: {name}, Pin Number: {pin}, Register Address: {pin}, Function Code: {function_code}, Slave ID: {slave_id}, Default Signal: {default_signal}")
        
        try:
            if self.connection_type == 'serial':
                self._wait_inter_frame_delay()
                self._clear_serial_buffer()
                
                if self.instrument.address != slave_id:
                    self.instrument.address = slave_id
                
                # Use read_bits() for better RS485 reliability
                # Use configured function code: 1 for read_coils, 2 for read_discrete_inputs
                if function_code == 1:
                    # Function Code 1: Read Coils
                    # For coils: read from address 0, then extract the specific bit
                    # This matches the behavior in _read_input for consistency
                    read_count = max(pin + 1, 3)
                    all_bits = self.instrument.read_bits(0, read_count, functioncode=1)
                    # Extract the specific bit we need
                    if pin < len(all_bits):
                        value = all_bits[pin]
                    else:
                        # Fallback: read single bit
                        value = self.instrument.read_bit(pin, functioncode=1)
                    value = bool(value)
                else:
                    # Function Code 2: Read Discrete Inputs
                    # For discrete inputs: read starting from the requested pin address
                    # If pin = 0, read_bits(0, 1, functioncode=2)
                    # If pin = 1, read_bits(1, 2, functioncode=2)
                    read_count = pin + 1
                    all_bits = self.instrument.read_bits(pin, read_count, functioncode=2)
                    # The first bit in the result is the one we need
                    value = all_bits[0] if len(all_bits) > 0 else False
                    value = bool(value)
                
                logger.info(f"[IO Serial] Read sensor {name} at pin {pin} using function code {function_code}: {value}")
            else:
                # Use pymodbus for TCP
                # Use configured function code: 1 for read_coils, 2 for read_discrete_inputs
                if function_code == 2:
                    # Function Code 2: Read Discrete Inputs
                    result = read_discrete_inputs_compat(self.client, pin, 1, slave_id)
                else:
                    # Function Code 1: Read Coils
                    result = read_coils_compat(self.client, pin, 1, slave_id)
                
                if result.isError():
                    return {
                        "status": 500,
                        "message": f"Failed to read {name} at address {pin} using function code {function_code}"
                    }
                
                value = result.bits[0]
                logger.info(f"[IO TCP] Read sensor {name} at pin {pin} using function code {function_code}: {value}")
            
            # Determine if sensor is triggered based on default signal
            if default_signal == 'low':
                triggered = value  # HIGH = triggered
            else:
                triggered = not value  # LOW = triggered
            
            fc_name = "Read Coils (FC1)" if function_code == 1 else "Read Discrete Inputs (FC2)"
            return {
                "status": 200,
                "message": f"{name}: {'TRIGGERED' if triggered else 'NORMAL'} (raw: {'HIGH' if value else 'LOW'}, {fc_name})",
                "value": value,
                "triggered": triggered,
                "function_code": function_code
            }
            
        except Exception as e:
            logger.exception("[IO] Sensor test failed for %s", name)
            return {"status": 500, "message": "Sensor test failed. Please verify sensor pin and default signal settings."}
    
    def reset_all_relays(self):
        """Reset all relays to LOW/OFF state"""
        try:
            if not self.connected:
                return {"status": 400, "message": "Not connected to I/O controller"}
            
            if self.connection_type == 'tcp' and self.client:
                # Set all 8 coils (DO1-DO8) to False (LOW/OFF)
                for coil_addr in range(8):
                    try:
                        result = write_coil_compat(self.client, coil_addr, False, self.slave_id)
                        if result.isError():
                            logger.info(f"[IO] Warning: Could not reset coil {coil_addr}: {result}")
                        time.sleep(0.05)  # Small delay between writes
                    except Exception as e:
                        logger.info(f"[IO] Warning: Error resetting coil {coil_addr}: {e}")
                logger.info("[IO] All relays reset to LOW/OFF state")
                return {"status": 200, "message": "All relays reset to LOW/OFF"}
            
            elif self.connection_type == 'serial' and self.instrument:
                # Set all coils to LOW
                for coil_addr in range(8):
                    try:
                        self.instrument.write_bit(coil_addr, 0, functioncode=5)
                        time.sleep(0.05)
                    except Exception as e:
                        logger.info(f"[IO] Warning: Error resetting coil {coil_addr}: {e}")
                logger.info("[IO] All relays reset to LOW/OFF state")
                return {"status": 200, "message": "All relays reset to LOW/OFF"}
            
            return {"status": 400, "message": "No active connection"}
        except Exception as e:
            logger.exception("[IO] Relay reset failed")
            return {"status": 500, "message": "Failed to reset relays. Please reconnect I/O controller and retry."}
    
    def disconnect(self):
        """Disconnect from I/O controller"""
        try:
            # Before disconnecting, set all relays to LOW/OFF to prevent stuck states
            if self.connected:
                with _SuppressPymodbusLogging():
                    if self.connection_type == 'tcp' and self.client:
                        try:
                            for coil_addr in range(8):
                                try:
                                    write_coil_compat(self.client, coil_addr, False, self.slave_id)
                                    time.sleep(0.05)
                                except (ModbusException, OSError, Exception):
                                    pass
                            logger.info("[IO] All relays set to LOW/OFF before disconnect")
                        except Exception:
                            pass
                    elif self.connection_type == 'serial' and self.instrument:
                        try:
                            for coil_addr in range(8):
                                try:
                                    self.instrument.write_bit(coil_addr, 0, functioncode=5)
                                    time.sleep(0.05)
                                except Exception:
                                    pass
                            logger.info("[IO] All relays set to LOW/OFF before disconnect")
                        except Exception:
                            pass
            
            if self.client:
                try:
                    # In pymodbus 3.x, close() should properly close the socket
                    self.client.close()
                    # Additional cleanup: ensure socket is closed
                    if hasattr(self.client, 'socket') and self.client.socket:
                        try:
                            self.client.socket.close()
                        except:
                            pass
                except:
                    pass
                self.client = None
            
            if self.instrument:
                try:
                    self.instrument.serial.close()
                except:
                    pass
                self.instrument = None
            
            self.connected = False
            self.connection_type = None
            return {"status": 200, "message": "Disconnected from I/O controller"}
        except Exception as e:
            logger.exception("[IO] Disconnect failed")
            return {"status": 500, "message": "Failed to disconnect I/O controller cleanly."}
