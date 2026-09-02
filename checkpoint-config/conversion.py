"""
Data Conversion Module for Weighbridge Automation System.

This module handles site-specific data conversion for RFID and Digitizer.
Modify these classes based on the specific hardware at each client site.

When debugging new hardware:
1. Run the application and observe raw data in logs
2. Modify the conversion methods to parse the specific format
3. Test and verify the output

RFID_Convert: Converts raw RFID data to 24-char hex string
Digitizer_Convert: Converts raw serial data to weight in KGs

Version: 2.3.5.4
"""
__version__ = "2.3.5.4"

import logging
import re
from typing import Optional, List

logger = logging.getLogger("weighbridge.conversion")


class RFID_Convert:
    """
    RFID Data Conversion Class.
    
    Converts raw RFID data from the reader to a standardized format.
    
    Modify this class based on the specific RFID reader at the client site.
    
    Usage:
        converter = RFID_Convert()
        rfid = converter.convert(raw_bytes)
        # Returns: "E200001234567890ABCDEF12" or None if invalid
    
    Debugging Steps:
        1. Enable debug logging to see raw data
        2. Check the format of raw_data in logs
        3. Modify convert() method to parse your specific format
        4. Test with actual RFID cards
    """
    
    def __init__(self):
        """Initialize RFID converter"""
        self._last_raw_data: bytes = b""
        self._last_converted: str = ""
        self._manual_match_start: int = -1
        self._manual_match_length: int = 0
        logger.debug("RFID_Convert initialized")

    def set_manual_match(self, start: Optional[int], length: Optional[int]) -> None:
        """Set optional fixed substring coordinates for raw-hex extraction."""
        self._manual_match_start = int(start) if start is not None else -1
        self._manual_match_length = int(length) if length is not None else 0
        if self._manual_match_start >= 0 and self._manual_match_length > 0:
            logger.info(
                "RFID manual match configured: start=%s length=%s",
                self._manual_match_start,
                self._manual_match_length,
            )
        else:
            logger.info("RFID manual match disabled")
    
    def convert(self, raw_data: bytes) -> Optional[str]:
        """
        Convert raw RFID data to 24-character hex string.
        
        This is the main conversion method. Modify this based on your RFID reader format.
        
        Args:
            raw_data: Raw bytes received from RFID reader socket
            
        Returns:
            24-character hex string (e.g., "E200001234567890ABCDEF12")
            or None if conversion fails
        
        Common RFID Formats:
            - Binary with E2 prefix (UHF ISO 18000-6C)
            - STX/ETX framed ASCII
            - Plain ASCII hex string
            - Custom vendor format
        """
        # Store for debugging
        self._last_raw_data = raw_data
        
        # Log raw data for debugging (INFO level so it shows in console)
        logger.debug(f"RFID raw data received - Hex: {raw_data.hex()}, Length: {len(raw_data)} bytes")
        
        try:
            # Try to decode as string for logging
            try:
                raw_str = raw_data.decode('ascii', errors='replace')
                logger.debug(f"RFID raw data (ascii): {raw_str}")
            except:
                pass
            
            # =================================================================
            # CONVERSION LOGIC - SUPPORTS MULTIPLE RFID READER FORMATS
            # =================================================================
            # 
            # Supported Readers:
            # - Identium IDS-002: Header (36 chars) + RFID (24 chars) + Suffix (2 chars)
            # - Zebra: Direct 24/32 char hex output
            # - Secureye: Direct 24/32 char hex output
            # - Generic UHF readers with E2 prefix
            #
            # RFID Tag Formats:
            # - 96-bit  = 24 hex chars = 12 bytes (most common)
            # - 128-bit = 32 hex chars = 16 bytes
            # =================================================================
            
            rfid = None
            
            # Check if raw_data is already an ASCII hex string (common for some readers)
            # If so, use it directly; otherwise convert bytes to hex
            try:
                # Try to decode as ASCII - if successful and looks like hex, use it directly
                ascii_str = raw_data.decode('ascii', errors='strict').strip()
                # Remove any whitespace, CRLF, etc.
                ascii_str = ascii_str.replace('\r', '').replace('\n', '').replace(' ', '').replace('\t', '')
                # Check if it's a valid hex string (24 or 32 chars, or longer with valid hex)
                if all(c in '0123456789ABCDEFabcdef' for c in ascii_str):
                    if len(ascii_str) == 24:
                        # Perfect 24-char hex string - use it directly
                        hex_str = ascii_str.upper()
                    elif len(ascii_str) == 32:
                        # 32-char hex string - use it directly
                        hex_str = ascii_str.upper()
                    elif len(ascii_str) > 24:
                        # Longer than expected - check for special patterns before truncating
                        hex_chars_only = ''.join(c for c in ascii_str if c in '0123456789ABCDEFabcdef')
                        
                        # Check for leading zeros followed by E2-prefixed RFID (common pattern)
                        e2_pos = hex_chars_only.find('E2')
                        if e2_pos > 0 and e2_pos < len(hex_chars_only) - 10:
                            # Check if there are leading zeros before E2
                            leading_portion = hex_chars_only[:e2_pos]
                            if all(c == '0' for c in leading_portion) and len(leading_portion) > 0:
                                # Found leading zeros + E2 pattern - preserve full hex string for format handlers
                                hex_str = hex_chars_only.upper()
                            else:
                                # Not the leading zeros pattern, take first 24 chars
                                hex_str = hex_chars_only[:24].upper()
                        elif len(hex_chars_only) >= 24:
                            # No E2 found, take first 24 chars of valid hex
                            hex_str = hex_chars_only[:24].upper()
                        else:
                            # Not enough hex chars, convert bytes to hex
                            hex_str = raw_data.hex().upper()
                    else:
                        # Too short, convert bytes to hex
                        hex_str = raw_data.hex().upper()
                else:
                    # Not a valid hex string, convert bytes to hex
                    hex_str = raw_data.hex().upper()
            except (UnicodeDecodeError, AttributeError):
                # Not ASCII, convert bytes to hex
                hex_str = raw_data.hex().upper()
            
            logger.debug(f"Processing hex string: {hex_str} (length: {len(hex_str)} chars)")

            # Manual extraction override from IoT-Configuration calibration.
            if self._manual_match_start >= 0 and self._manual_match_length > 0:
                start = self._manual_match_start
                end = start + self._manual_match_length
                if end <= len(hex_str):
                    manual_rfid = hex_str[start:end]
                    if all(c in '0123456789ABCDEF' for c in manual_rfid):
                        self._last_converted = manual_rfid
                        logger.debug(
                            "RFID decoded [Manual substring match %s:%s]: %s",
                            start,
                            end,
                            manual_rfid,
                        )
                        return manual_rfid
                    logger.warning(
                        "Manual RFID substring contains non-hex characters at %s:%s",
                        start,
                        end,
                    )
                else:
                    logger.warning(
                        "Manual RFID substring out of range: start=%s length=%s raw_len=%s",
                        start,
                        self._manual_match_length,
                        len(hex_str),
                    )
            
            # -----------------------------------------------------------------
            # FORMAT 1: Identium Reader Format
            # -----------------------------------------------------------------
            # Pattern: FF0100140300000000003000010101XX050C + RFID(24) + 00
            # Header is 36 chars, RFID starts at position 36
            # Examples:
            #   ff0100140300000000003000010101e3050ce200001d7507013115006bb900
            #   ff0100140300000000003000010101cf050c34161fa820328ee8303efaa000
            
            if hex_str.startswith('FF01') and len(hex_str) >= 62:
                # Identium format detected
                # Extract RFID from position 36, take 24 chars (96-bit)
                rfid = hex_str[36:60]
                logger.debug(f"RFID decoded [Identium FF01 format]: {rfid}")
            
            # -----------------------------------------------------------------
            # FORMAT 1B: CF Prefix Reader Format (26 bytes total)
            # -----------------------------------------------------------------
            # Pattern: CF 00 00 01 12 00 FD XX 01 00 0C + RFID(12 bytes) + Checksum(2 bytes)
            # Header is 22 hex chars (11 bytes), RFID starts at position 22
            # Total = 52 hex chars (26 bytes)
            # Examples:
            #   cf0000011200fd3a01000ce28069950000400a8f3981330a1d
            #   cf0000011200fd9e01000ce28069950000400a8f398133Mk
            
            elif hex_str.startswith('CF') and len(hex_str) >= 46:
                # CF prefix format detected
                # Header: 11 bytes = 22 hex chars
                # RFID: 12 bytes = 24 hex chars (position 22-46)
                # Suffix: 2 bytes = 4 hex chars (checksum)
                rfid = hex_str[22:46]
                logger.debug(f"RFID decoded [CF prefix format]: {rfid}")
            
            # -----------------------------------------------------------------
            # FORMAT 1C: 11 00 EE 00 FE Prefix Reader Format (18 bytes total)
            # -----------------------------------------------------------------
            # Pattern: 11 00 EE 00 FE + RFID(12 bytes) + Checksum(2 bytes)
            # Header is 10 hex chars (5 bytes), RFID starts at position 10
            # Total = 36 hex chars (18 bytes)
            # Example: 1100EE00FED7383354314CBA00001590A284
            #          |--header(10)--||----RFID(24)-----||suffix(4)|
            
            elif hex_str.startswith('1100EE00FE') and len(hex_str) >= 34:
                # 11 00 EE 00 FE prefix format detected (variant 1: with FE)
                # Header: 5 bytes = 10 hex chars (1100EE00FE)
                # RFID: 12 bytes = 24 hex chars (position 10-34)
                # Suffix: 2 bytes = 4 hex chars (checksum)
                rfid = hex_str[10:34]
                logger.debug(f"RFID decoded [11 00 EE 00 FE prefix format]: {rfid}")
            
            # -----------------------------------------------------------------
            # FORMAT 1C2: 11 00 EE 00 Prefix Reader Format (17-18 bytes total)
            # -----------------------------------------------------------------
            # Pattern: 11 00 EE 00 + RFID(12 bytes) + Checksum(1-2 bytes)
            # Header is 8 hex chars (4 bytes), RFID starts at position 8
            # Total = 34 hex chars (17 bytes) or 36 hex chars (18 bytes)
            # Example: 1100EE0034161FA820328EE82AAE5D600AEC
            #          |--header(8)--||----RFID(24)-----||suffix(2)|
            # RFID: 34161FA820328EE82AAE5D600A (removing prefix 1100EE00 and suffix EC)
            
            elif hex_str.startswith('1100EE00') and len(hex_str) >= 32:
                # 11 00 EE 00 prefix format detected (variant 2: without FE)
                # Header: 4 bytes = 8 hex chars (1100EE00)
                # RFID: 12 bytes = 24 hex chars (position 8-32)
                # Suffix: 1-2 bytes = 2-4 hex chars (checksum, e.g., EC)
                rfid = hex_str[8:32]
                logger.debug(f"RFID decoded [11 00 EE 00 prefix format]: {rfid}")
            
            # -----------------------------------------------------------------
            # FORMAT 1D: FastTag Format (CCFFFF prefix, 25 bytes total)
            # -----------------------------------------------------------------
            # Pattern: CC FF FF XX XX XX XX XX XX + RFID(12 bytes) + Checksum(4 bytes)
            # Header is 18 hex chars (9 bytes), RFID starts at position 18
            # Total = 50 hex chars (25 bytes)
            # Example: CCFFFF20051200340034161FA820328A522B629740A704B6C7
            #          |--header(18)--||----RFID(24)-----||suffix(8)|
            # RFID: 34161FA820328A522B629740
            # 
            # Variant: CCFFFF with E2-prefixed RFID tag
            # Example: CCFFFF200512003400E28011700000021B09926B1705CCBA23
            #          |--header(18)--||----RFID(24)-----||suffix(8)|
            # RFID: E28011700000021B09926B17
            
            elif hex_str.startswith('CCFFFF') and len(hex_str) >= 24:
                # FastTag format detected - try multiple extraction methods
                rfid_extracted = False
                
                # Method 1: Look for E2-prefixed RFID tag (EPC Gen2 indicator)
                # This is more reliable as E2 is a standard prefix for UHF tags
                e2_pos = hex_str.find('E2', 6)  # Search after CCFFFF (6 hex chars)
                if e2_pos >= 6 and e2_pos + 24 <= len(hex_str):
                    # Found E2 tag, extract 24 hex chars starting from E2
                    rfid = hex_str[e2_pos:e2_pos+24]
                    logger.debug(f"RFID decoded [FastTag CCFFFF format, E2 at pos {e2_pos}]: {rfid}")
                    rfid_extracted = True
                
                # Method 2: Standard format (9-byte header, RFID at position 18)
                # Use this if E2 not found or if we want to try standard position
                if not rfid_extracted and len(hex_str) >= 42:
                    # Standard FastTag format: CCFFFF + 6 bytes header + 12 bytes RFID + 4 bytes suffix
                    rfid = hex_str[18:42]
                    logger.debug(f"RFID decoded [FastTag CCFFFF format, standard position 18]: {rfid}")
                    rfid_extracted = True
                
                # Method 3: Try to extract any 24-char sequence that looks valid
                if not rfid_extracted and len(hex_str) >= 30:
                    # Try position 18 even if total length is less than 42
                    if len(hex_str) >= 42:
                        rfid = hex_str[18:42]
                        logger.debug(f"RFID decoded [FastTag CCFFFF format, fallback]: {rfid}")
                    else:
                        # Extract available data from position 18, pad if needed
                        available = hex_str[18:]
                        if len(available) >= 24:
                            rfid = available[:24]
                            logger.debug(f"RFID decoded [FastTag CCFFFF format, partial]: {rfid}")
            
            # -----------------------------------------------------------------
            # FORMAT 2: Direct output with E2 prefix (EPC Gen2 tags)
            # -----------------------------------------------------------------
            # Used by: Zebra, Secureye, and many other readers
            # Pattern: E2XXXXXXXXXXXXXXXXXXXXXX (24 chars for 96-bit)
            # Example: e200001d7507013115006bb9
            # Note: Some readers may send the tag twice (48 chars), extract only first 24
            
            elif hex_str.startswith('E2') and len(hex_str) >= 24:
                # Direct EPC Gen2 tag
                # Check if tag is duplicated (e.g., "E200001D...E200001D...")
                if len(hex_str) >= 48:
                    # Likely duplicated tag - check if first 24 chars repeat
                    first_24 = hex_str[:24]
                    second_24 = hex_str[24:48] if len(hex_str) >= 48 else ""
                    if second_24 == first_24:
                        # Tag is duplicated, take only first 24 chars
                        rfid = first_24
                        logger.debug(f"RFID decoded [EPC Gen2 96-bit, duplicated tag filtered]: {rfid}")
                    else:
                        # Not duplicated, might be 128-bit or concatenated data
                        rfid = hex_str[:24]  # Take first 24 for 96-bit
                        logger.debug(f"RFID decoded [EPC Gen2 96-bit, long data]: {rfid}")
                elif len(hex_str) >= 32:
                    rfid = hex_str[:32]  # 128-bit
                    logger.debug(f"RFID decoded [EPC Gen2 128-bit]: {rfid}")
                else:
                    rfid = hex_str[:24]  # 96-bit
                    logger.debug(f"RFID decoded [EPC Gen2 96-bit]: {rfid}")
            
            # -----------------------------------------------------------------
            # FORMAT 3: Direct output without E2 prefix (proprietary tags)
            # -----------------------------------------------------------------
            # Used by: Some readers output raw tag data
            # Pattern: XXXXXXXXXXXXXXXXXXXXXXXX (24 chars for 96-bit)
            # Example: 34161fa820328ee8303efaa0
            
            elif len(hex_str) == 24 and all(c in '0123456789ABCDEF' for c in hex_str):
                # Exactly 24 hex chars - likely 96-bit direct output
                rfid = hex_str
                logger.debug(f"RFID decoded [Direct 96-bit]: {rfid}")
            
            elif len(hex_str) == 32 and all(c in '0123456789ABCDEF' for c in hex_str):
                # Exactly 32 hex chars - likely 128-bit direct output
                rfid = hex_str
                logger.debug(f"RFID decoded [Direct 128-bit]: {rfid}")
            
            # -----------------------------------------------------------------
            # FORMAT 3B: Leading zeros followed by E2-prefixed RFID
            # -----------------------------------------------------------------
            # Pattern: Leading zeros (padding) + E2-prefixed RFID (24 or 32 chars)
            # Examples:
            #   "00000000000000000000E28069150000600F6946A8B0DDC2" -> Extract "E28069150000600F6946A8B0DDC2" (32 chars)
            #   "000000000000000000E200001d7507013115006bb9" -> Extract "E200001d7507013115006bb9" (24 chars)
            # This format is common when readers pad the RFID with leading zeros
            
            elif rfid is None:
                # Find E2 position in the hex string
                e2_pos = hex_str.find('E2')
                if e2_pos > 0 and e2_pos < len(hex_str) - 10:  # E2 found and not at the very end
                    # Check if there are leading zeros before E2
                    leading_portion = hex_str[:e2_pos]
                    if all(c == '0' for c in leading_portion) and len(leading_portion) > 0:
                        # Found leading zeros followed by E2 - extract RFID
                        rfid_portion = hex_str[e2_pos:]
                        
                        # Check if tag is duplicated (e.g., "E200001D...E200001D...")
                        if len(rfid_portion) >= 48:
                            first_24 = rfid_portion[:24]
                            second_24 = rfid_portion[24:48] if len(rfid_portion) >= 48 else ""
                            if second_24 == first_24:
                                # Tag is duplicated, take only first 24 chars
                                rfid = first_24
                                logger.debug(f"RFID decoded [Leading zeros + E2, duplicated tag filtered]: {rfid}")
                            elif len(rfid_portion) >= 32:
                                # Not duplicated, might be 128-bit (32 chars)
                                rfid = rfid_portion[:32]
                                logger.debug(f"RFID decoded [Leading zeros + E2, 128-bit]: {rfid}")
                            else:
                                rfid = rfid_portion[:24]
                                logger.debug(f"RFID decoded [Leading zeros + E2, 96-bit]: {rfid}")
                        elif len(rfid_portion) >= 32:
                            # 128-bit RFID (32 chars)
                            rfid = rfid_portion[:32]
                            logger.debug(f"RFID decoded [Leading zeros + E2, 128-bit]: {rfid}")
                        elif len(rfid_portion) >= 24:
                            # 96-bit RFID (24 chars)
                            rfid = rfid_portion[:24]
                            logger.debug(f"RFID decoded [Leading zeros + E2, 96-bit]: {rfid}")
            
            # -----------------------------------------------------------------
            # FORMAT 4: Find E2 prefix anywhere in the data
            # -----------------------------------------------------------------
            # Some readers add prefix/suffix around the E2 tag
            
            if rfid is None:
                e2_pos = hex_str.find('E2')
                if e2_pos >= 0 and len(hex_str) - e2_pos >= 24:
                    rfid_portion = hex_str[e2_pos:]
                    
                    # Check if tag is duplicated (e.g., "E200001D...E200001D...")
                    if len(rfid_portion) >= 48:
                        first_24 = rfid_portion[:24]
                        second_24 = rfid_portion[24:48] if len(rfid_portion) >= 48 else ""
                        if second_24 == first_24:
                            # Tag is duplicated, take only first 24 chars
                            rfid = first_24
                            logger.debug(f"RFID decoded [E2 found at pos {e2_pos}, duplicated tag filtered]: {rfid}")
                        else:
                            # Not duplicated, extract normally (prefer 96-bit = 24 chars)
                            rfid = rfid_portion[:24]
                    elif len(rfid_portion) >= 32:
                        rfid = rfid_portion[:32]  # 128-bit
                    else:
                        rfid = rfid_portion[:24]  # 96-bit
                    logger.debug(f"RFID decoded [E2 found at pos {e2_pos}]: {rfid}")
            
            # -----------------------------------------------------------------
            # FORMAT 5: STX/ETX framed (0x02 = STX, 0x03 = ETX)
            # -----------------------------------------------------------------
            
            if rfid is None and (b'\x02' in raw_data or b'\x03' in raw_data):
                stx_pos = raw_data.find(b'\x02')
                etx_pos = raw_data.find(b'\x03')
                if etx_pos > stx_pos and stx_pos >= 0:
                    content = raw_data[stx_pos + 1:etx_pos]
                    try:
                        # Remove any CRLF or whitespace
                        ascii_str = content.decode('ascii').strip().replace('\r', '').replace('\n', '')
                        if len(ascii_str) >= 24 and all(c in '0123456789ABCDEFabcdef' for c in ascii_str):
                            # Support 24, 26, or 32 char RFIDs
                            if len(ascii_str) >= 32:
                                rfid = ascii_str[:32].upper()
                            elif len(ascii_str) >= 26:
                                rfid = ascii_str[:26].upper()  # Some readers output 26 chars
                            else:
                                rfid = ascii_str[:24].upper()
                            logger.debug(f"RFID decoded [STX/ETX framed]: {rfid}")
                    except:
                        pass
            
            # -----------------------------------------------------------------
            # FORMAT 6: ASCII hex string with delimiters
            # -----------------------------------------------------------------
            
            if rfid is None:
                try:
                    ascii_str = raw_data.decode('ascii', errors='ignore').strip()
                    ascii_str = ascii_str.replace('\r', '').replace('\n', '').replace(' ', '')
                    hex_chars = ''.join(c for c in ascii_str if c in '0123456789ABCDEFabcdef').upper()
                    
                    if len(hex_chars) >= 24:
                        # Check for E2 prefix
                        e2_pos = hex_chars.find('E2')
                        if e2_pos >= 0:
                            rfid_portion = hex_chars[e2_pos:]
                            
                            # Check if tag is duplicated
                            if len(rfid_portion) >= 48:
                                first_24 = rfid_portion[:24]
                                second_24 = rfid_portion[24:48] if len(rfid_portion) >= 48 else ""
                                if second_24 == first_24:
                                    # Tag is duplicated, take only first 24 chars
                                    rfid = first_24
                                else:
                                    # Not duplicated, extract normally
                                    rfid = rfid_portion[:24] if len(rfid_portion) < 32 else rfid_portion[:32]
                            else:
                                rfid = rfid_portion[:24] if len(rfid_portion) < 32 else rfid_portion[:32]
                        else:
                            # No E2 prefix, take first 24 or 32 chars
                            rfid = hex_chars[:24] if len(hex_chars) < 32 else hex_chars[:32]
                        logger.debug(f"RFID decoded [ASCII hex]: {rfid}")
                except:
                    pass
            
            # -----------------------------------------------------------------
            # FORMAT 7: Fallback - extract any 24+ hex chars
            # -----------------------------------------------------------------
            
            if rfid is None and len(hex_str) >= 24:
                # Last resort: take first 24 chars if valid hex
                rfid = hex_str[:24]
                logger.warning(f"RFID decoded [Fallback]: {rfid}")
            
            # =================================================================
            # END OF CONVERSION LOGIC
            # =================================================================
            
            # Validate result (support both 96-bit/24-char and 128-bit/32-char)
            if rfid and len(rfid) in (24, 32) and all(c in '0123456789ABCDEF' for c in rfid):
                self._last_converted = rfid
                bits = len(rfid) * 4
                logger.debug(f"RFID validated: {rfid} ({bits}-bit)")
                return rfid
            elif rfid:
                # RFID found but wrong length - log for debugging
                logger.warning(f"RFID invalid length ({len(rfid)} chars): {rfid}")
                logger.warning(f"Raw data was: {raw_data.hex()}")
                return None
            else:
                logger.warning(f"RFID conversion failed. Raw data: {raw_data.hex()}")
                return None
                
        except Exception as e:
            logger.error(f"RFID conversion error: {e}")
            logger.error(f"Raw data that caused error: {raw_data.hex()}")
            return None
    
    def get_last_raw_data(self) -> bytes:
        """Get the last raw data received (for debugging)"""
        return self._last_raw_data
    
    def get_last_converted(self) -> str:
        """Get the last successfully converted RFID"""
        return self._last_converted
    
    def debug_print(self, raw_data: bytes) -> None:
        """
        Print detailed debug information about raw data.
        
        Call this method to analyze unknown RFID data formats.
        """
        # print("\n" + "=" * 60)
        # print("RFID DEBUG INFORMATION")
        # print("=" * 60)
        # print(f"Raw bytes length: {len(raw_data)}")
        # print(f"Raw bytes (hex): {raw_data.hex()}")
        # print(f"Raw bytes (repr): {repr(raw_data)}")
        
        # try:
        #     print(f"ASCII decode: {raw_data.decode('ascii', errors='replace')}")
        # except:
        #     print("ASCII decode: Failed")
        
        # try:
        #     print(f"UTF-8 decode: {raw_data.decode('utf-8', errors='replace')}")
        # except:
        #     print("UTF-8 decode: Failed")
        
        # print("\nByte-by-byte breakdown:")
        for i, b in enumerate(raw_data):
            char_repr = chr(b) if 32 <= b <= 126 else '.'
            # print(f"  [{i:3d}] 0x{b:02X} ({b:3d}) '{char_repr}'")
        
        # print("=" * 60 + "\n")


class Digitizer_Convert:
    """
    Digitizer (Weight Scale) Data Conversion Class.
    
    Converts raw serial data from digitizer to weight in KGs.
    
    Modify this class based on the specific digitizer at the client site.
    
    Usage:
        converter = Digitizer_Convert()
        weight = converter.convert(raw_bytes)
        # Returns: 30000 (weight in kg) or None if invalid
    
    Debugging Steps:
        1. Enable debug logging to see raw data
        2. Check the format of raw_data in logs
        3. Modify convert() method to parse your specific format
        4. Test with actual weight readings
    
    Common Digitizer Formats:
        - STX + data + ETX + CR/LF
        - Plain ASCII with spaces
        - Fixed-width numeric fields
        - Character-by-character streaming
    """

    # STX/ETX continuous stream: "  50 kg    G 028289 A" (G field is a sequence counter, not weight)
    _KG_GA_FRAME_RE = re.compile(
        r'([+-]?\d+)\s*kg\s+G\s*\d+\s*A',
        re.IGNORECASE,
    )
    # STX + ')' + status digit + gross weight + tail + CR  (e.g. STX)0  56440    00<CR>)
    _PAREN_WEIGHT_FRAME_RE = re.compile(
        r'\)\s*\d\s+(\d{3,})\s+\d+\s*(?:\r|\n)',
    )
    # Partial frame before CR arrives (device check / fragmented reads)
    _PAREN_WEIGHT_PARTIAL_RE = re.compile(
        r'\)\s*\d\s+(\d{4,})(?:\s+\d*)?$',
    )
    # STX+ status digit + gross weight continuous stream (e.g. STX STX 0 11900 STX STX 0 11900)
    _STX_STATUS_WEIGHT_FRAME_RE = re.compile(rb'\x02+\s*\d\s+(\d{3,})')
    # Euro-sign (0x80 CP1252 / HyperTerminal) framed weight stream.
    _EURO_WEIGHT_BYTE = rb'(?:\x80|\xe2\x82\xac)'
    _EURO_WEIGHT_DELIM = rb'(?:\x80|\xe2\x82\xac)+'
    _EURO_WEIGHT_PAD = rb'[\x20\xa0]*'
    _EURO_WEIGHT_NUM = rb'([+-]?\d{3,7})'
    _EURO_WEIGHT_FRAME_RE = re.compile(
        _EURO_WEIGHT_DELIM + _EURO_WEIGHT_PAD + _EURO_WEIGHT_NUM + rb'(?=' + _EURO_WEIGHT_DELIM + rb')',
    )
    _EURO_WEIGHT_PARTIAL_RE = re.compile(
        _EURO_WEIGHT_DELIM + _EURO_WEIGHT_PAD + _EURO_WEIGHT_NUM + rb'$'
    )
    _EURO_WEIGHT_LIVE_TAIL_RE = re.compile(
        _EURO_WEIGHT_DELIM + _EURO_WEIGHT_PAD + rb'([+-]?\d{1,7})$'
    )
    _EURO_WEIGHT_DIGITS_RE = re.compile(
        _EURO_WEIGHT_PAD + _EURO_WEIGHT_NUM
    )
    _EURO_GLUED_DIGITS_RE = re.compile(r'(?:\d{4,7}){2,}')
    _EURO_SIGNED_GLUED_RE = re.compile(r'(?:[+-]?\d{4,7}){2,}')

    # Central source for method selection order and labels used by UI preview.
    # Keep this list in conversion.py so site-specific updates only require
    # replacing conversion.py (without rebuilding the executable).
    PREVIEW_METHOD_ORDER = [
        ("bracket", "Method 1 - Bracket [000000] format"),
        ("stx_paren", "Method 2 - STX)N  NNNNN  NN<CR> format"),
        ("kg", "Method 3 - Number + 'kg' format"),
        ("ga", "Method 4 - G ... A garbled format"),
        ("wt", "Method 5 - 'Wt:' + ETX (0x03) framed stream"),
        ("st_gs", "Method 6 - ST,GS,+0000000kg format"),
        ("prefix", "Method 7 - Number prefix format"),
        ("hyper_1bh", "Method 8 - HyperTerminal 1BH0 frame format"),
        ("plain_ascii", "Method 9 - Plain ASCII digits"),
        ("p_at_pct", "Method 10 - HyperTerminal stream (50eP@%p, 50ePF!r, 0`PF!w, 80hPG!v)"),
        ("stx_status", "Method 11 - STX STX status WEIGHT stream"),
        ("euro_weight", "Method 12 - Euro (0x80) framed WEIGHT stream"),
    ]

    @classmethod
    def get_preview_method_order(cls):
        """Return ordered (method_id, label) tuples for conversion preview UI."""
        return list(cls.PREVIEW_METHOD_ORDER)
    
    def __init__(self):
        """Initialize Digitizer converter"""
        self._buffer: str = ""  # Buffer for accumulating character-by-character data
        self._line_ascii_buffer: str = ""  # Buffer for line-oriented plain-ASCII digitizers
        self._raw_buffer: bytes = b""  # Buffer for accumulating raw bytes until we find "Wt:"
        self._wt_stream_buffer: bytes = b""  # Dedicated buffer for conversion_method "wt"
        # Buffer for HyperTerminal-style continuous frames (e.g., "1BH086800<ETX><STX>...")
        self._hb_stream_buffer: str = ""
        self._pat_pct_buffer: str = ""
        # Rolling raw bytes for STX/ETX "NN kg    G NNNNNN A" continuous streams
        self._kg_stream_buffer: bytes = b""
        # Rolling buffer for STX)N  NNNNN  NN<CR> streams
        self._paren_stream_buffer: bytes = b""
        # Rolling buffer for STX+ status WEIGHT streams (e.g. STX STX 0 11900)
        self._stx_status_stream_buffer: bytes = b""
        # Rolling buffer for Euro (0x80) framed WEIGHT streams
        self._euro_weight_stream_buffer: bytes = b""
        self._last_raw_data: bytes = b""
        self._last_weight: Optional[float] = None
        # Preferred conversion method ID (configured via iot_configuration.json)
        # Supported IDs:
        #   bracket, stx_paren, kg, ga, wt, st_gs, prefix, hyper_1bh,
        #   p_at_pct, stx_status, euro_weight, plain_ascii, index_based
        self._preferred_method: Optional[str] = None
        self._indexing_dict: Optional[dict] = None
        self._index_config_ready: bool = False
        logger.debug("Digitizer_Convert initialized")

    def set_preferred_method(self, method_id: Optional[str]) -> None:
        """
        Select a single conversion method by ID.

        When set, convert() uses strict calibration: only this method runs and
        auto-detect fallback is disabled (Weighbridge-App runtime).
        """
        if method_id:
            self._preferred_method = str(method_id).strip().lower()
            logger.info(f"Digitizer_Convert preferred method set to: {self._preferred_method}")
        else:
            self._preferred_method = None
            logger.info("Digitizer_Convert preferred method cleared (auto-detect enabled)")

    def set_index_config(self, indexing) -> bool:
        """Load index_based calibration from iot_configuration.json indexing block."""
        if not indexing or not isinstance(indexing, dict):
            self._indexing_dict = None
            self._index_config_ready = False
            return False
        try:
            from digitizer_index_engine import config_from_indexing

            config_from_indexing(indexing)
            self._indexing_dict = dict(indexing)
            self._index_config_ready = True
            logger.info("Digitizer index_based calibration loaded")
            return True
        except Exception as exc:
            logger.error("Failed to load index_based calibration: %s", exc)
            self._indexing_dict = None
            self._index_config_ready = False
            return False

    def is_index_calibration_ready(self) -> bool:
        return self._index_config_ready

    def has_strict_calibration(self) -> bool:
        return bool((self._preferred_method or "").strip())

    def _convert_strict(self, raw_data: bytes, text: str) -> Optional[float]:
        """Parse using only the configured conversion method (no auto-detect)."""
        method = (self._preferred_method or "").strip().lower()
        if method == "index_based":
            if not self._index_config_ready or not self._indexing_dict:
                logger.warning(
                    "index_based calibration not loaded — rejecting digitizer packet"
                )
                return None
            from digitizer_index_engine import extract_weight_from_indexing

            weight = extract_weight_from_indexing(raw_data, self._indexing_dict)
            if weight is not None:
                return self._finalize_weight(weight, raw_data)
            return None
        weight = self._convert_by_method(method, raw_data, text)
        if weight is not None:
            return self._finalize_weight(weight, raw_data)
        return None
    
    
    def convert(self, raw_data: bytes) -> Optional[float]:
        """
        Convert raw digitizer data to weight in KGs.
        
        This is the main conversion method. Modify this based on your digitizer format.
        
        Args:
            raw_data: Raw bytes received from serial port
            
        Returns:
            Weight in KG as float (e.g., 30000.0)
            or None if conversion fails
        
        Common Digitizer Formats:
            - STX (0x02) + space + digits + ETX (0x03) + CR/LF
            - Plain ASCII: "  12345" (space-padded)
            - Continuous stream: one character at a time
        """
        # Store for debugging
        self._last_raw_data = raw_data
        
        # Log raw data for debugging
        # Show first 50 hex chars to avoid flooding
        # hex_preview = raw_data.hex()[:50] + "..." if len(raw_data) > 25 else raw_data.hex()
        # logger.debug(f"Digitizer raw data - Hex: {hex_preview}, Length: {len(raw_data)} bytes")  # Removed to reduce log spam
        
        try:
            # Try to decode as string for logging
            try:
                raw_str = raw_data.decode('ascii', errors='replace')
                # Show control characters clearly for debugging
                visible_str = ""
                for c in raw_str:
                    if ord(c) == 0x02:
                        visible_str += "<STX>"
                    elif ord(c) == 0x03:
                        visible_str += "<ETX>"
                    elif ord(c) == 0x0D:
                        visible_str += "<CR>"
                    elif ord(c) == 0x0A:
                        visible_str += "<LF>"
                    elif ord(c) == 0x20:
                        visible_str += " "  # Space
                    elif ord(c) < 32:
                        visible_str += f"<{ord(c):02X}>"
                    else:
                        visible_str += c
                logger.debug(f"Digitizer raw data: '{visible_str}' (hex: {raw_data.hex()[:60]}...)")
            except:
                logger.debug(f"Digitizer raw data (hex): {raw_data.hex()[:60]}...")
            
            # =================================================================
            # CONVERSION LOGIC - MODIFY THIS SECTION FOR YOUR DIGITIZER
            # =================================================================
            
            weight = None
            
            # First, decode to string
            try:
                text = raw_data.decode('ascii', errors='ignore')
            except:
                text = ""

            if self.has_strict_calibration():
                return self._convert_strict(raw_data, text)

            _pref = (self._preferred_method or "").strip().lower()

            # -------------------------------------------------------------
            # EURO (0x80) FRAMED WEIGHT STREAM (e.g. \x80 70060\x80 70060)
            # -------------------------------------------------------------
            if self._is_euro_weight_stream_context(raw_data, text):
                self._accumulate_euro_weight_stream_buffer(raw_data)
                w_euro = self._method_euro_weight_stream_scan()
                if w_euro is not None:
                    if _pref != "euro_weight":
                        self.set_preferred_method("euro_weight")
                    return self._finalize_weight(w_euro, raw_data)
                if not raw_data:
                    live = self.get_live_weight(fresh_only=True)
                    if live is not None:
                        return live
                w_glued = self._method_euro_glued_digits_recovery(text)
                if w_glued is not None:
                    if _pref != "euro_weight":
                        self.set_preferred_method("euro_weight")
                    return self._finalize_weight(w_glued, raw_data)
                if (
                    b"\x80" in self._euro_weight_stream_buffer
                    or b"\xe2\x82\xac" in self._euro_weight_stream_buffer
                    or self._euro_weight_stream_established()
                    or _pref == "euro_weight"
                ):
                    return None

            # -------------------------------------------------------------
            # STX+ STATUS  WEIGHT STREAM (e.g. STX STX 0 11900)
            # -------------------------------------------------------------
            if self._is_stx_status_weight_stream_context(raw_data, text):
                self._accumulate_stx_status_stream_buffer(raw_data)
                w_stx_status = self._method_stx_status_weight_stream_scan()
                if w_stx_status is not None:
                    if _pref != "stx_status":
                        self.set_preferred_method("stx_status")
                    return self._finalize_weight(w_stx_status, raw_data)
                if self._stx_status_stream_established():
                    if self._last_weight is not None:
                        return self._last_weight
                    return None

            # -------------------------------------------------------------
            # STX)N  WEIGHT  NN<CR> STREAM (e.g. STX)0  56440    00<CR>)
            # -------------------------------------------------------------
            if self._is_paren_weight_stream_context(raw_data, text):
                self._accumulate_paren_stream_buffer(raw_data)
                w_paren = self._method_paren_weight_stream_scan()
                if w_paren is not None:
                    if _pref != "stx_paren":
                        self.set_preferred_method("stx_paren")
                    return self._finalize_weight(w_paren, raw_data)
                if self._paren_stream_established():
                    if self._last_weight is not None:
                        return self._last_weight
                    return None

            # -------------------------------------------------------------
            # CONTINUOUS KG+G+A STREAM (STX/ETX framed, optional CRLF)
            # -------------------------------------------------------------
            if self._is_kg_stream_context(raw_data, text):
                self._accumulate_kg_stream_buffer(raw_data)
                w_kg = self._method_kg_stream_scan()
                if w_kg is not None:
                    if _pref != "kg":
                        self.set_preferred_method("kg")
                    return self._finalize_weight(w_kg, raw_data)

            if text:
                self._pat_pct_buffer += text
                if len(self._pat_pct_buffer) > 500:
                    self._pat_pct_buffer = self._pat_pct_buffer[-500:]

            # -------------------------------------------------------------
            # SITE-SPECIFIC FORMAT: HyperTerminal continuous frames "1BH0xxxxx"
            # -------------------------------------------------------------
            # Observed stream example:
            #   "1BH086800\x03\x02 1BH086800\x03\x02 ... 1BH086750 ..."
            # Where:
            #   - Frame token: "1BH0" + 5 digits (weight)
            #   - Control chars between frames: ETX (0x03) + STX (0x02)
            #   - Noise tokens may appear (e.g., "?P`@")
            #
            # Strategy:
            #   - Accumulate a small rolling ASCII buffer
            #   - Extract the most recent "1BH0" weight frame
            if weight is None and text:
                self._hb_stream_buffer += text
                if len(self._hb_stream_buffer) > 500:
                    self._hb_stream_buffer = self._hb_stream_buffer[-500:]

                # Match exact frame token: "1BH0" + 5 digits.
                # Important: keep this strict to avoid swallowing the first digit
                # of the next concatenated frame (e.g., "...1BH0830001BH0...").
                hb_matches = list(re.finditer(r'1BH0(\d{5})(?!\d)', self._hb_stream_buffer))
                if hb_matches:
                    digits = hb_matches[-1].group(1)
                    if digits.isdigit():
                        try:
                            weight = float(digits)
                            logger.info(
                                "Weight decoded via HyperTerminal 1BH0 frame: %s kg (frame=%s)",
                                weight,
                                f"1BH0{digits}",
                            )
                        except ValueError:
                            weight = None

            # -------------------------------------------------------------
            # SITE-SPECIFIC FORMAT: P/Q marker HyperTerminal stream (Method 9)
            # -------------------------------------------------------------
            if weight is None and self._pat_pct_buffer:
                wpat = self._method_p_at_pct_scan()
                if wpat is not None:
                    weight = wpat

            # -------------------------------------------------------------
            # SITE-SPECIFIC FORMAT: Plain digits with trailing CR/LF
            # -------------------------------------------------------------
            # New site sends weight as: "12890\n\r" (digits followed by newline+carriage)
            # or minor variants with CR/LF ordering. This handler checks for a string
            # that is only digits plus optional CR/LF characters and decodes it.
            # Skip when preferred method is "kg" or euro glued frames would false-match.
            if weight is None and _pref != "kg" and not self._euro_ascii_fallback_blocked(raw_data, text):
                raw_text_for_log = text
                # Strip only CR/LF characters from both ends
                stripped = raw_text_for_log.strip('\r\n')
                # If the remaining content is pure digits, treat as weight
                if stripped.isdigit():
                    try:
                        weight = float(stripped)
                        logger.debug(
                            f"Weight decoded via plain CR/LF-terminated digits format: "
                            f"{weight} kg from repr='{raw_text_for_log!r}'"
                        )
                    except ValueError:
                        # Fall through to normal chain if conversion fails
                        weight = None

            # -------------------------------------------------------------
            # SITE-SPECIFIC FORMAT: "$WT:      0" (HyperTerminal / digitizer)
            # -------------------------------------------------------------
            # Digitizer sends one line per reading: optional '$', "WT", ':', spaces, digits.
            # Example raw data (HyperTerminal): "$WT:      0" repeated per line; or "$WT:   47560".
            # No space required before colon; multiple lines in one chunk use the last (most recent).
            if weight is None:
                wt_pattern = re.compile(r'(?i)\$?\s*WT\s*:\s*([+-]?\d+(?:\.\d+)?)')
                wt_matches = list(wt_pattern.finditer(text))
                if wt_matches:
                    wt_match = wt_matches[-1]  # use last reading when multiple lines
                    try:
                        weight = float(wt_match.group(1))
                        logger.debug(
                            f"Weight decoded via WT label format: {weight} kg from '{wt_match.group(0).strip()}'"
                        )
                    except ValueError:
                        weight = None

            # -------------------------------------------------------------
            # PREFERRED METHOD SHORT-CIRCUIT (used by Weighbridge-App)
            # -------------------------------------------------------------
            # Do not override an already-detected site-specific parse (e.g., BH stream).
            if self._preferred_method and weight is None:
                weight = self._convert_by_method(self._preferred_method, raw_data, text)
                if weight is not None:
                    # Apply standard validation/sanity logic and return
                    return self._finalize_weight(weight, raw_data)
                # If the selected method couldn't decode this packet, fall
                # back to the existing auto-detect chain below.
            
            # Method 7: Bracketed format - CHECK THIS FIRST (highest priority)
            # Format: [000000][000000][000000]... (multiple weight readings in brackets, single line)
            # Examples:
            #   "[000000][000000][000000][000000][000000]" -> extract "0" (0kg)
            #   "[000080][000080][000080][000080][000080]" -> extract "80" (80g = 0.08kg)
            # Pattern: [digits] repeated multiple times, extract the last (most recent) value
            if weight is None:
                # Find all bracketed values: [digits]
                bracket_matches = re.findall(r'\[(\d+)\]', text)
                if bracket_matches:
                    # Use the last (most recent) bracketed value
                    # All values should be the same, but use last one to be safe
                    weight_str = bracket_matches[-1]
                    weight = float(weight_str)  # Convert grams to kg (000080 = 80g = 0.08kg)
                    logger.info(f"Weight decoded via bracketed format (PRIORITY): {weight} kg from '[{weight_str}]' (found {len(bracket_matches)} brackets, using last)")
            
            # Method 6: "kg" format - CHECK THIS SECOND
            # Format: {spaces}{number} kg    G 000000 A
            # Examples:
            #   "     20 kg    G 000000 A" -> extract "20"
            #   "     00 kg    G 000000 A" -> extract "0"
            #   "    -40 kg    G 000000 A" -> extract "-40"
            #   "11290kg" -> extract "11290" (no space before kg)
            # Pattern: optional spaces, optional minus sign, digits, optional space, "kg" (case-insensitive)
            if weight is None:
                # Try to find pattern: {spaces}{optional_sign}{digits} {optional_space}kg
                # Use \s* to allow zero or more spaces (handles both "11290kg" and "11290 kg")
                match = re.search(r'([+-]?\d+)\s*kg\b', text, re.IGNORECASE)
                if match:
                    weight = float(match.group(1))
                    logger.debug(f"Weight decoded via 'kg' format (PRIORITY): {weight} kg from '{match.group(0)}'")
            
            # Method 6B: Garbled/Corrupted data format with "G" and "A" markers
            # Format: {garbage}G{spaces}{digits}{spaces}A{garbage}
            # Examples:
            #   "‚  ´66¸0 ëç    G 000000 A" -> extract "0" (from "000000")
            #   "‚  ´66¸0 ëç    G 004200 A" -> extract "4200"
            #   "‚  ´66¸0 ëç    G 123456 A" -> extract "123456"
            # Pattern: Look for "G" followed by optional spaces, then digits, then optional spaces, then "A"
            if weight is None:
                # Try to find pattern: G{spaces}{digits}{spaces}A
                # This handles corrupted data where control characters are present
                match = re.search(r'G\s*([+-]?\d+)\s*A', text, re.IGNORECASE)
                if match:
                    weight_str = match.group(1)
                    weight = float(weight_str)
                    logger.info(f"Weight decoded via garbled G...A format: {weight} kg from 'G {weight_str} A' (raw: {repr(text[:50])})")
            
            # Method 6C: Binary/corrupted data - extract any numeric pattern after "G"
            # This is a more aggressive fallback for heavily corrupted data
            if weight is None:
                # Try to find "G" followed by any sequence of digits (even with garbage in between)
                # Look for "G" then extract the first valid numeric sequence
                g_pos = text.find('G')
                if g_pos >= 0 and g_pos < len(text) - 5:
                    # Extract text after "G"
                    after_g = text[g_pos + 1:]
                    # Try to find a sequence of digits (allowing some garbage characters)
                    # Look for at least 3 consecutive digits
                    digit_match = re.search(r'(\d{3,})', after_g)
                    if digit_match:
                        weight_str = digit_match.group(1)
                        weight = float(weight_str)
                        logger.info(f"Weight decoded via binary/corrupted G format: {weight} kg from 'G...{weight_str}...' (raw hex: {raw_data.hex()[:60]})")
            
            # Method 5: Wt: format - CHECK THIS SECOND
            # Format: Wt:     {spaces}{weight_digits}{non-digit}Wt:...
            # Examples:
            #   "Wt:  58940♥0⚠Wt:" -> extract "58940" (stop at ♥)
            #   "Wt:     50G0GWt:" -> extract "50" (stop at G)
            # Logic:
            #   1. Accumulate data in buffer until we find "Wt:"
            #   2. After "Wt:" (after the colon), skip spaces
            #   3. Extract all consecutive digits until first non-digit (like ♥, G, etc.)
            #   4. Return the weight as-is (no auto-division)
            
            # Add current data to buffer
            self._raw_buffer += raw_data
            
            # Limit buffer size to prevent memory issues (keep last 200 bytes to handle multiple Wt: patterns)
            if len(self._raw_buffer) > 200:
                self._raw_buffer = self._raw_buffer[-200:]
            
            # Find the LAST "Wt:" in the buffer (most recent reading)
            # Check if "Wt:" exists in the accumulated buffer (case insensitive)
            wt_pattern = b'Wt:'
            wt_pos = -1
            search_pos = 0
            # Find the last occurrence of "Wt:"
            while True:
                pos = self._raw_buffer.find(wt_pattern, search_pos)
                if pos == -1:
                    break
                wt_pos = pos
                search_pos = pos + 1
            
            # If not found, try lowercase
            if wt_pos == -1:
                wt_pattern = b'wt:'
                search_pos = 0
                while True:
                    pos = self._raw_buffer.find(wt_pattern, search_pos)
                    if pos == -1:
                        break
                    wt_pos = pos
                    search_pos = pos + 1
            
            if wt_pos >= 0:
                # Found "Wt:", now read after the colon
                # Position after "Wt:" is wt_pos + 3 (W, t, :)
                after_colon_pos = wt_pos + 3
                
                if after_colon_pos < len(self._raw_buffer):
                    # Extract portion after "Wt:"
                    after_wt = self._raw_buffer[after_colon_pos:]
                    
                    # Decode to string (control characters will be handled)
                    after_str = after_wt.decode('ascii', errors='ignore')
                    
                    # Skip ONLY spaces at the start (not tabs, newlines, etc.)
                    # Find the first non-space character
                    start_idx = 0
                    while start_idx < len(after_str) and after_str[start_idx] == ' ':
                        start_idx += 1
                    
                    # Now extract all consecutive digits from this position
                    weight_digits = ""
                    found_separator = False
                    for i in range(start_idx, len(after_str)):
                        char = after_str[i]
                        if char.isdigit():
                            weight_digits += char
                        else:
                            # Stop at first non-digit character (could be ♥, G, space, letter, symbol, etc.)
                            found_separator = True
                            break
                    
                    # Only extract if we have digits AND we found a non-digit separator after them
                    # This ensures we have the complete number (e.g., "5950♥" not just "595")
                    # Exception: if there's another "Wt:" pattern after this one, it means this reading is complete
                    if weight_digits and found_separator:
                        # Convert to float and return as-is (no auto-division)
                        weight = float(weight_digits)
                        logger.debug(f"Weight decoded via Wt: format (PRIORITY): {weight} kg from '{weight_digits}' (raw after colon: {repr(after_str[:40])})")
                        
                        # Clear buffer after successful extraction (keep last 30 bytes in case next "Wt:" starts soon)
                        if len(self._raw_buffer) > 30:
                            # Keep last 30 bytes to handle cases where next "Wt:" might be starting
                            self._raw_buffer = self._raw_buffer[-30:]
                        else:
                            # If buffer is small, clear it completely
                            self._raw_buffer = b""
                    elif weight_digits and not found_separator:
                        # We have digits but no separator - might be incomplete (e.g., "595" when "5950" is coming)
                        # Check if there's another "Wt:" pattern after this one (indicating this reading is complete)
                        next_wt_pos = self._raw_buffer.find(wt_pattern, wt_pos + 1)
                        if next_wt_pos >= 0:
                            # There's another "Wt:" after this one, so this reading is complete
                            # Extract the digits we have
                            weight = float(weight_digits)
                            logger.debug(f"Weight decoded via Wt: format (PRIORITY): {weight} kg from '{weight_digits}' (no separator but next Wt: found, raw: {repr(after_str[:40])})")
                            
                            # Clear buffer after successful extraction
                            if len(self._raw_buffer) > 30:
                                self._raw_buffer = self._raw_buffer[-30:]
                            else:
                                self._raw_buffer = b""
                        # else: don't extract yet, wait for more data or separator
            
            # Method 1: STX/ETX framed data (only if Method 5 didn't find "Wt:")
            # Format: STX (0x02) + data + ETX (0x03)
            # Also handles:
            #   - STX STX + spaces + digits (e.g., "\x02\x02 0049510")
            #   - spaces + digits + STX STX (e.g., " 0044050\x02\x02" or "0000050\x02\x02")
            # Check both raw_data and buffer to handle fragmented reads
            if weight is None and (b'\x02' in raw_data or b'\x02' in self._raw_buffer or b'\x03' in raw_data or b'\x03' in self._raw_buffer):
                logger.debug(f"STX pattern detected - raw_data length: {len(raw_data)}, buffer length: {len(self._raw_buffer)}, raw_data hex: {raw_data.hex()[:40]}")
                # First, check the buffer (accumulated data) for complete patterns
                # This handles cases where data comes in fragments
                buffer_to_check = self._raw_buffer if len(self._raw_buffer) > len(raw_data) else raw_data
                
                # Check for STX at the beginning: STX STX + spaces + digits (e.g., "\x02\x02 0049510")
                if buffer_to_check.startswith(b'\x02'):
                    # Count consecutive STX characters
                    stx_count = 0
                    pos = 0
                    while pos < len(buffer_to_check) and buffer_to_check[pos] == 0x02:
                        stx_count += 1
                        pos += 1
                    
                    # Skip spaces after STX
                    while pos < len(buffer_to_check) and buffer_to_check[pos] in (0x20, 0x00):  # Space or null
                        pos += 1
                    
                    # Extract digits from this position
                    if pos < len(buffer_to_check):
                        remaining = buffer_to_check[pos:]
                        try:
                            remaining_str = remaining.decode('ascii', errors='ignore')
                            # Match digits (with optional leading zeros, e.g., "0049510" -> 49510)
                            # Stop at first non-digit (like STX character)
                            digit_match = re.match(r'([+-]?\d+)', remaining_str)
                            if digit_match:
                                weight_str = digit_match.group(1)
                                weight = float(weight_str)  # float() automatically handles leading zeros
                                logger.debug(f"Weight decoded via STX+spaces+digits format: {weight} kg from '{weight_str}' (STX count: {stx_count})")
                                # Clear buffer after successful extraction
                                if len(self._raw_buffer) > 30:
                                    self._raw_buffer = self._raw_buffer[-30:]
                                else:
                                    self._raw_buffer = b""
                        except:
                            pass
                
                # Check for STX at the end: digits + STX STX (e.g., "0000050\x02\x02" or " 0044050\x02\x02")
                if weight is None and buffer_to_check.endswith(b'\x02'):
                    # Find the last STX position
                    last_stx_pos = buffer_to_check.rfind(b'\x02')
                    if last_stx_pos > 0:
                        # Check if there are multiple STX at the end (need at least 2 STX)
                        stx_count = 0
                        pos = last_stx_pos
                        while pos >= 0 and buffer_to_check[pos] == 0x02:
                            stx_count += 1
                            pos -= 1
                        stx_start = pos + 1
                        
                        # Need at least 2 STX characters to consider this a valid pattern
                        if stx_count >= 2:
                            # Extract data before STX
                            data_before_stx = buffer_to_check[:stx_start]
                            
                            # Skip leading spaces (but keep leading zeros - they're part of the number)
                            digit_start = 0
                            while digit_start < len(data_before_stx) and data_before_stx[digit_start] == 0x20:  # Space only, not null or zero
                                digit_start += 1
                            
                            # Extract digits (including leading zeros, e.g., "0000050" -> 50.0, "0000000" -> 0.0)
                            if digit_start < len(data_before_stx):
                                remaining = data_before_stx[digit_start:]
                                try:
                                    remaining_str = remaining.decode('ascii', errors='ignore')
                                    # Match digits (with optional leading zeros, e.g., "0000050" -> 50.0, "0000000" -> 0.0)
                                    # The regex will match all consecutive digits, and float() will handle leading zeros correctly
                                    digit_match = re.match(r'([+-]?\d+)', remaining_str)
                                    if digit_match:
                                        weight_str = digit_match.group(1)
                                        weight = float(weight_str)  # float() automatically handles leading zeros (0000050 -> 50.0)
                                        logger.debug(f"Weight decoded via digits+STX format: {weight} kg from '{weight_str}' (STX count: {stx_count} at end)")
                                        # Clear buffer after successful extraction
                                        if len(self._raw_buffer) > 30:
                                            self._raw_buffer = self._raw_buffer[-30:]
                                        else:
                                            self._raw_buffer = b""
                                except:
                                    pass
                
                # Also check raw_data directly (for immediate matches)
                if weight is None and (b'\x02' in raw_data or b'\x03' in raw_data):
                    # Check for STX at the beginning: STX STX + spaces + digits (e.g., "\x02\x02 0049510")
                    if raw_data.startswith(b'\x02'):
                        # Count consecutive STX characters
                        stx_count = 0
                        pos = 0
                        while pos < len(raw_data) and raw_data[pos] == 0x02:
                            stx_count += 1
                            pos += 1
                        
                        # Skip spaces after STX
                        while pos < len(raw_data) and raw_data[pos] in (0x20, 0x00):  # Space or null
                            pos += 1
                        
                        # Extract digits from this position
                        if pos < len(raw_data):
                            remaining = raw_data[pos:]
                            try:
                                remaining_str = remaining.decode('ascii', errors='ignore')
                                # Match digits (with optional leading zeros, e.g., "0049510" -> 49510)
                                digit_match = re.match(r'([+-]?\d+)', remaining_str)
                                if digit_match:
                                    weight_str = digit_match.group(1)
                                    weight = float(weight_str)  # float() automatically handles leading zeros
                                    logger.debug(f"Weight decoded via STX+spaces+digits format (raw_data): {weight} kg from '{weight_str}' (STX count: {stx_count})")
                            except:
                                pass
                    
                    # Check for STX at the end: spaces + digits + STX STX (e.g., " 0044050\x02\x02")
                    if weight is None and raw_data.endswith(b'\x02'):
                        # Find the last STX position
                        last_stx_pos = raw_data.rfind(b'\x02')
                        if last_stx_pos > 0:
                            # Check if there are multiple STX at the end
                            stx_count = 0
                            pos = last_stx_pos
                            while pos >= 0 and raw_data[pos] == 0x02:
                                stx_count += 1
                                pos -= 1
                            stx_start = pos + 1
                            
                            # Need at least 2 STX characters to consider this a valid pattern
                            if stx_count >= 2:
                                # Extract data before STX
                                data_before_stx = raw_data[:stx_start]
                                
                                # Skip leading spaces
                                digit_start = 0
                                while digit_start < len(data_before_stx) and data_before_stx[digit_start] in (0x20, 0x00):  # Space or null
                                    digit_start += 1
                                
                                # Extract digits
                                if digit_start < len(data_before_stx):
                                    remaining = data_before_stx[digit_start:]
                                    try:
                                        remaining_str = remaining.decode('ascii', errors='ignore')
                                        # Match digits (with optional leading zeros, e.g., "0044050" -> 44050)
                                        digit_match = re.match(r'([+-]?\d+)', remaining_str)
                                        if digit_match:
                                            weight_str = digit_match.group(1)
                                            weight = float(weight_str)  # float() automatically handles leading zeros
                                            logger.debug(f"Weight decoded via spaces+digits+STX format (raw_data): {weight} kg from '{weight_str}' (STX count: {stx_count} at end)")
                                    except:
                                        pass
                
                # Fallback to original STX/ETX method if STX patterns didn't work
                if weight is None:
                    # Remove STX/ETX
                    text = text.replace('\x02', '').replace('\x03', '')
                    text = text.replace('\r', '').replace('\n', '').strip()
                    
                    logger.debug(f"STX/ETX framed text after cleanup: '{text}' (len={len(text)})")  # Removed to reduce log spam
                    # Check if it's all spaces/empty (weight = 0)
                    if len(text) == 0 or text.strip() == '':
                        weight = 0.0
                        logger.debug("STX/ETX data is empty/spaces only, weight = 0")  # Removed to reduce log spam
                    else:
                        # Extract numeric value
                        match = re.search(r'[-+]?\s*(\d+(?:\.\d+)?)', text)
                        if match:
                            weight = float(match.group(1))
                            logger.debug(f"Weight decoded via STX/ETX method: {weight} kg")  # Removed to reduce log spam
                        # else:
                        #     logger.debug(f"STX/ETX: No numeric match in '{text}'")  # Removed to reduce log spam
            
            # Method 2: Character-by-character accumulation
            # Some digitizers send one character at a time
            # We accumulate in buffer until we get a complete reading
            elif len(raw_data) == 1 or len(raw_data) <= 3:
                # Accumulate characters
                self._buffer += text.replace('\r', '').replace('\n', '')
                
                # Check if we have a complete number (ends with newline or buffer is long enough)
                if '\n' in text or '\r' in text or len(self._buffer) >= 8:
                    # Try to extract weight from buffer
                    match = re.search(r'[-+]?\s*(\d+(?:\.\d+)?)', self._buffer)
                    if match:
                        weight = float(match.group(1))
                        logger.debug(f"Weight decoded via buffer method: {weight} kg")  # Removed to reduce log spam
                    # Clear buffer
                    self._buffer = ""
            
            # Method 3: ST,GS format (e.g., "ST,GS,+0040740kg")
            # Format: ST,GS,{sign}{digits}kg
            # Example: ST,GS,+0040740kg -> weight = 40740.0 kg
            if weight is None:
                text = text.replace('\r', '').replace('\n', '').strip()
                # Check for ST,GS format
                if text.startswith('ST,GS,') or 'ST,GS,' in text:
                    # Extract the numeric part after ST,GS,
                    # Pattern: ST,GS,+0040740kg or ST,GS,-0012345kg
                    match = re.search(r'ST,GS,([+-]?\d+(?:\.\d+)?)', text)
                    if match:
                        weight = float(match.group(1))
                        logger.debug(f"Weight decoded via ST,GS format: {weight} kg")  # Removed to reduce log spam
            
            # Method 4: Weight prefix format (e.g., "0`PF%q▒▒" or "50ePG%w▒▒")
            # Format: {weight}{control_chars}{trailing_chars}
            # Examples: "0`PF%q▒▒" -> 0 kg, "50ePG%w▒▒" -> 50 kg
            # Pattern: Weight number at the start, followed by control characters
            if weight is None:
                text = text.replace('\r', '').replace('\n', '').strip()
                # Try to match weight at the beginning of the string
                # Pattern: digits (with optional decimal) at the start, followed by non-numeric chars
                # This handles formats like "0`PF%q", "50ePG%w", etc.
                match = re.match(r'^([+-]?\d+(?:\.\d+)?)', text)
                if match:
                    weight = float(match.group(1))
                    logger.debug(f"Weight decoded via prefix format: {weight} kg (from '{text[:20]}...')")  # Removed to reduce log spam
            
            # Method 4B: Binary/Hex data with "G" marker in raw bytes
            # Format: {binary_data}G{spaces}{digits}{spaces}A{binary_data}
            # This handles cases where ASCII decoding fails but the pattern exists in raw bytes
            if weight is None:
                # Look for "G" (0x47) in raw bytes
                g_byte = b'G'
                g_pos = raw_data.find(g_byte)
                if g_pos >= 0 and g_pos < len(raw_data) - 5:
                    # Extract bytes after "G"
                    after_g_bytes = raw_data[g_pos + 1:]
                    try:
                        # Try to decode as ASCII with error handling
                        after_g_text = after_g_bytes.decode('ascii', errors='ignore')
                        # Look for digits followed by "A"
                        match = re.search(r'(\d+)\s*A', after_g_text, re.IGNORECASE)
                        if match:
                            weight_str = match.group(1)
                            weight = float(weight_str)
                            logger.info(f"Weight decoded via binary G...A format (raw bytes): {weight} kg from 'G {weight_str} A'")
                    except:
                        # If decoding fails, try to find ASCII digits in hex representation
                        hex_str = raw_data.hex()
                        # Look for "47" (G) followed by hex digits that represent ASCII numbers
                        # Pattern: 47 (G) then look for 30-39 (digits 0-9) in hex
                        g_hex_pos = hex_str.find('47')  # "G" in hex
                        if g_hex_pos >= 0:
                            # Look for sequence of hex pairs that represent ASCII digits (30-39)
                            after_g_hex = hex_str[g_hex_pos + 2:]
                            # Find sequence of hex pairs representing digits
                            digit_hex_pattern = r'(3[0-9])+'  # Hex pairs 30-39 represent ASCII '0'-'9'
                            digit_match = re.search(digit_hex_pattern, after_g_hex)
                            if digit_match:
                                # Convert hex pairs back to ASCII digits
                                hex_digits = digit_match.group(0)
                                weight_str = ""
                                for i in range(0, len(hex_digits), 2):
                                    hex_pair = hex_digits[i:i+2]
                                    ascii_val = int(hex_pair, 16)
                                    if 48 <= ascii_val <= 57:  # ASCII '0'-'9'
                                        weight_str += chr(ascii_val)
                                if weight_str:
                                    weight = float(weight_str)
                                    logger.info(f"Weight decoded via binary hex G format: {weight} kg from hex pattern")
            
            
            # Method 6: Plain ASCII with spaces/padding
            # Format: "  12345" or " 12345.00 kg" or " 0002000" (space + digits)
            if weight is None:
                # Don't strip leading spaces yet - we need them for the pattern
                text_no_crlf = text.replace('\r', '').replace('\n', '')
                # Remove common units
                text_clean = re.sub(r'[kKgG]', '', text_no_crlf)
                
                # Match pattern: optional sign, optional spaces, digits (e.g., " 0002000" or "  12345")
                # The regex should match even with leading spaces
                match = re.search(r'[-+]?\s*(\d+(?:\.\d+)?)', text_clean)
                if match:
                    weight_str = match.group(1)
                    weight = float(weight_str)  # float() handles leading zeros (0002000 -> 2000.0)
                    logger.debug(f"Weight decoded via plain ASCII method: {weight} kg from '{weight_str}' (raw: '{text_clean[:30]}...')")
                else:
                    # Avoid noisy warnings for packets that are only CR/LF or empty
                    if text_clean.strip() == "":
                        logger.debug(
                            f"Plain ASCII method skipped empty/CRLF-only text "
                            f"(len={len(text_clean)}, hex: {raw_data.hex()[:40]}...)"
                        )
                    else:
                        logger.warning(
                            f"Plain ASCII method failed - text: '{text_clean[:50]}...' "
                            f"(len={len(text_clean)}, hex: {raw_data.hex()[:40]}...)"
                        )
            
            # Method 6B: Heavily corrupted data - extract longest numeric sequence
            # This is a last resort for data that's too corrupted for other methods
            # Format: {garbage}{digits}{garbage}
            # Examples:
            #   "‚  ´66¸0 ëç    G 000000 A" -> extract "000000" or "66" or "0"
            #   "‚  ´4200¸0 ëç    G 004200 A" -> extract "4200" or "004200"
            if weight is None:
                # Extract all sequences of digits from the text (even if corrupted)
                all_digit_sequences = re.findall(r'\d+', text)
                if all_digit_sequences:
                    # Use the longest sequence (most likely to be the weight)
                    # If multiple sequences of same length, prefer the one that looks like a weight (6-7 digits)
                    longest = max(all_digit_sequences, key=len)
                    # Prefer sequences that are 6-7 digits (common weight format like "004200" or "000000")
                    weight_candidates = [seq for seq in all_digit_sequences if len(seq) >= 6]
                    if weight_candidates:
                        # Use the longest of the 6+ digit sequences
                        weight_str = max(weight_candidates, key=len)
                    else:
                        # No 6+ digit sequences, use the longest available
                        weight_str = longest
                    
                    weight = float(weight_str)
                    logger.info(f"Weight decoded via corrupted data extraction: {weight} kg from numeric sequence '{weight_str}' (found {len(all_digit_sequences)} sequences, raw: {repr(text[:60])})")
            
            # =================================================================
            # END OF CONVERSION LOGIC
            # =================================================================

            # Final pass: rolling buffer may hold a complete token even if this chunk alone did not match
            if weight is None and self._paren_stream_established():
                w_paren = self._method_paren_weight_stream_scan()
                if w_paren is not None:
                    weight = w_paren
            if weight is None and self._stx_status_stream_established():
                w_stx_status = self._method_stx_status_weight_stream_scan()
                if w_stx_status is not None:
                    weight = w_stx_status
            if weight is None and self._euro_weight_stream_established():
                w_euro = self._method_euro_weight_stream_scan()
                if w_euro is not None:
                    weight = w_euro
            if weight is None and self._kg_stream_established():
                w_kg = self._method_kg_stream_scan()
                if w_kg is not None:
                    weight = w_kg

            # Euro frames with 0x80 stripped decode as glued digits — recover last frame.
            if weight is None and self._euro_ascii_fallback_blocked(raw_data, text):
                w_glued = self._method_euro_glued_digits_recovery(text)
                if w_glued is not None:
                    if _pref != "euro_weight":
                        self.set_preferred_method("euro_weight")
                    weight = w_glued

            if weight is not None:
                return self._finalize_weight(weight, raw_data)

            # Stream digitizers: re-scan rolling buffers on framing-only / partial chunks.
            if self._paren_stream_established():
                w_paren = self._method_paren_weight_stream_scan()
                if w_paren is not None:
                    return self._finalize_weight(w_paren, raw_data)
            if self._stx_status_stream_established():
                w_stx_status = self._method_stx_status_weight_stream_scan()
                if w_stx_status is not None:
                    return self._finalize_weight(w_stx_status, raw_data)
                if self._last_weight is not None:
                    return self._last_weight
            if self._euro_weight_stream_established():
                w_euro = self._method_euro_weight_stream_scan()
                if w_euro is not None:
                    return self._finalize_weight(w_euro, raw_data)
                if not raw_data and self._last_weight is not None:
                    return self._last_weight
            if self._kg_stream_established():
                w_kg = self._method_kg_stream_scan()
                if w_kg is not None:
                    return self._finalize_weight(w_kg, raw_data)
                if self._last_weight is not None:
                    return self._last_weight

            logger.debug(f"Weight conversion returned None for data: {raw_data.hex()}")
            return None
                
        except Exception as e:
            logger.error(f"Digitizer conversion error: {e}")
            logger.error(f"Raw data that caused error: {raw_data.hex()}")
            return None

    # =====================================================================
    # STREAM DIGITIZER HELPERS (ported from conversion_old_success.py v1)
    # =====================================================================

    def _normalize_euro_weight_value(self, weight: float) -> Optional[float]:
        try:
            w = abs(float(weight))
        except (TypeError, ValueError):
            return None
        if 0 <= w <= 200000:
            return w
        return None

    @staticmethod
    def _normalize_kg_framing(text: str) -> str:
        if not text:
            return text
        return text.replace("\x02", " ").replace("\x03", " ")

    @staticmethod
    def _normalize_paren_framing(text: str) -> str:
        if not text:
            return text
        return text.replace("\x02", " ").replace("\x03", " ")

    def _euro_ascii_fallback_blocked(self, raw_data: bytes, text: str) -> bool:
        if (self._preferred_method or "").strip().lower() == "euro_weight":
            return True
        if self._is_euro_weight_stream_context(raw_data, text):
            return True
        probe = self._euro_weight_stream_buffer + (raw_data or b"")
        if b"\x80" in probe or b"\xe2\x82\xac" in probe:
            return True
        if text and re.search(r"(?:\d{5}){2,}", text):
            return True
        if text and self._EURO_SIGNED_GLUED_RE.search(text):
            return True
        return False

    def _is_euro_weight_stream_context(self, raw_data: bytes, text: str) -> bool:
        if (self._preferred_method or "").strip().lower() == "euro_weight":
            if raw_data or self._euro_weight_stream_buffer:
                return True
        if self._euro_weight_stream_established():
            return True
        probe = self._euro_weight_stream_buffer + (raw_data or b"")
        if not probe:
            return False
        if self._EURO_WEIGHT_FRAME_RE.search(probe):
            return True
        if self._EURO_WEIGHT_PARTIAL_RE.search(probe):
            return True
        if self._euro_weight_stream_buffer:
            return True
        if b"\x80" in probe or b"\xe2\x82\xac" in probe:
            if self._EURO_WEIGHT_DIGITS_RE.search(probe):
                return True
        if text and self._EURO_GLUED_DIGITS_RE.search(text) and self._euro_weight_stream_buffer:
            return True
        if text and self._EURO_SIGNED_GLUED_RE.search(text) and self._euro_weight_stream_buffer:
            return True
        return False

    def _euro_weight_stream_established(self) -> bool:
        if not self._euro_weight_stream_buffer:
            return False
        buf = self._euro_weight_stream_buffer
        return bool(
            self._EURO_WEIGHT_FRAME_RE.search(buf)
            or self._EURO_WEIGHT_PARTIAL_RE.search(buf)
            or self._EURO_WEIGHT_LIVE_TAIL_RE.search(buf)
        )

    def _accumulate_euro_weight_stream_buffer(self, raw_data: bytes) -> None:
        self._euro_weight_stream_buffer += raw_data
        if len(self._euro_weight_stream_buffer) > 256:
            self._euro_weight_stream_buffer = self._euro_weight_stream_buffer[-256:]

    def _euro_weight_trim_buffer_keep_tail(self) -> None:
        buf = self._euro_weight_stream_buffer
        if not buf:
            return
        last_pos = -1
        for marker in (b"\x80", b"\xe2\x82\xac"):
            pos = buf.rfind(marker)
            if pos > last_pos:
                last_pos = pos
        if last_pos > 0:
            self._euro_weight_stream_buffer = buf[last_pos:]
        elif len(buf) > 48:
            self._euro_weight_stream_buffer = buf[-48:]

    def _method_euro_signed_glued_recovery(self, text: str) -> Optional[float]:
        if not text or not self._EURO_SIGNED_GLUED_RE.search(text):
            return None
        matches = re.findall(r"[+-]?\d{4,7}", text)
        for token in reversed(matches):
            w = self._normalize_euro_weight_value(float(token))
            if w is not None:
                return w
        return None

    def _method_euro_glued_digits_recovery(self, text: str) -> Optional[float]:
        if not text:
            return None
        signed = self._method_euro_signed_glued_recovery(text)
        if signed is not None:
            return signed
        digits_only = re.sub(r"\D", "", text)
        if len(digits_only) < 8 or not self._EURO_GLUED_DIGITS_RE.search(digits_only):
            return None
        for frame_len in (5, 7, 6, 4, 3):
            if len(digits_only) < frame_len * 2 or len(digits_only) % frame_len != 0:
                continue
            frames = [
                digits_only[i * frame_len : (i + 1) * frame_len]
                for i in range(len(digits_only) // frame_len)
            ]
            try:
                w = float(frames[-1])
            except ValueError:
                continue
            if 0 <= w <= 200000:
                return w
        groups = re.findall(r"\d{4,7}", digits_only)
        if len(groups) >= 2:
            for group in reversed(groups):
                try:
                    w = float(group)
                except ValueError:
                    continue
                if 0 <= w <= 200000:
                    return w
        for tail_len in (5, 6, 7, 4):
            if len(digits_only) < tail_len:
                continue
            try:
                w = float(digits_only[-tail_len:])
            except ValueError:
                continue
            if 0 <= w <= 200000:
                return w
        return None

    def _method_euro_weight_token_split(self, buf: bytes) -> Optional[float]:
        if not buf or (b"\x80" not in buf and b"\xe2\x82\xac" not in buf):
            return None
        weights: List[float] = []
        for token in re.split(self._EURO_WEIGHT_DELIM, buf):
            if not token:
                continue
            match = self._EURO_WEIGHT_DIGITS_RE.search(token)
            if match is None:
                continue
            try:
                w = self._normalize_euro_weight_value(float(match.group(1).decode("ascii")))
            except ValueError:
                continue
            if w is not None:
                weights.append(w)
        if not weights:
            return None
        self._euro_weight_trim_buffer_keep_tail()
        return weights[-1]

    def _method_euro_weight_stream_scan(self) -> Optional[float]:
        if not self._euro_weight_stream_buffer:
            return None
        buf = self._euro_weight_stream_buffer
        token_w = self._method_euro_weight_token_split(buf)
        if token_w is not None:
            return token_w
        live_tail = self._EURO_WEIGHT_LIVE_TAIL_RE.search(buf)
        if live_tail:
            try:
                w = self._normalize_euro_weight_value(float(live_tail.group(1).decode("ascii")))
                if w is not None:
                    self._euro_weight_trim_buffer_keep_tail()
                    return w
            except ValueError:
                pass
        complete = list(self._EURO_WEIGHT_FRAME_RE.finditer(buf))
        partial = self._EURO_WEIGHT_PARTIAL_RE.search(buf)
        chosen = None
        if complete and partial:
            chosen = partial if partial.end() >= complete[-1].end() else complete[-1]
        elif partial:
            chosen = partial
        elif complete:
            chosen = complete[-1]
        if chosen:
            try:
                w = self._normalize_euro_weight_value(float(chosen.group(1).decode("ascii")))
                if w is not None:
                    drop = chosen.start()
                    if drop > 0:
                        self._euro_weight_stream_buffer = buf[drop:]
                    self._euro_weight_trim_buffer_keep_tail()
                    return w
            except ValueError:
                pass
        glued_w = self._method_euro_glued_digits_recovery(buf.decode("ascii", errors="ignore"))
        if glued_w is not None:
            self._euro_weight_trim_buffer_keep_tail()
        return glued_w

    def _is_paren_weight_stream_context(self, raw_data: bytes, text: str) -> bool:
        if self._is_euro_weight_stream_context(raw_data, text):
            return False
        if self._is_stx_status_weight_stream_context(raw_data, text):
            return False
        if self._paren_stream_established():
            return True
        if b"\x02)" in raw_data:
            return True
        if text and re.search(r"\)\s*\d\s+\d{3,}", text):
            return True
        return False

    def _paren_stream_established(self) -> bool:
        if not self._paren_stream_buffer:
            return False
        buf_text = self._normalize_paren_framing(
            self._paren_stream_buffer.decode("ascii", errors="ignore")
        )
        if self._PAREN_WEIGHT_FRAME_RE.search(buf_text):
            return True
        return bool(self._PAREN_WEIGHT_PARTIAL_RE.search(buf_text))

    def _accumulate_paren_stream_buffer(self, raw_data: bytes) -> None:
        self._paren_stream_buffer += raw_data
        if len(self._paren_stream_buffer) > 1024:
            self._paren_stream_buffer = self._paren_stream_buffer[-1024:]

    def _method_paren_weight_stream_scan(self) -> Optional[float]:
        if not self._paren_stream_buffer:
            return None
        text = self._normalize_paren_framing(
            self._paren_stream_buffer.decode("ascii", errors="ignore")
        )
        matches = list(self._PAREN_WEIGHT_FRAME_RE.finditer(text))
        if not matches:
            partial = list(self._PAREN_WEIGHT_PARTIAL_RE.finditer(text))
            if partial:
                matches = partial
        if not matches:
            loose = list(re.finditer(r"\)\s*\d\s+(\d{4,})", text))
            if loose:
                matches = loose
        if matches:
            try:
                w = float(matches[-1].group(1))
                if len(self._paren_stream_buffer) > 256:
                    self._paren_stream_buffer = self._paren_stream_buffer[-256:]
                return w
            except ValueError:
                pass
        return None

    def _is_stx_status_weight_stream_context(self, raw_data: bytes, text: str) -> bool:
        if self._is_euro_weight_stream_context(raw_data, text):
            return False
        if b"\x02)" in raw_data or (text and ")" in text and re.search(r"\)\s*\d\s+\d{3,}", text)):
            return False
        if self._stx_status_stream_established():
            return True
        probe = self._stx_status_stream_buffer + (raw_data or b"")
        if probe and self._STX_STATUS_WEIGHT_FRAME_RE.search(probe):
            return True
        if b"\x02" in (raw_data or b"") and re.search(rb"\x02+\s*\d\s+\d{3,}", probe):
            return True
        return False

    def _stx_status_stream_established(self) -> bool:
        if not self._stx_status_stream_buffer:
            return False
        return bool(self._STX_STATUS_WEIGHT_FRAME_RE.search(self._stx_status_stream_buffer))

    def _accumulate_stx_status_stream_buffer(self, raw_data: bytes) -> None:
        self._stx_status_stream_buffer += raw_data
        if len(self._stx_status_stream_buffer) > 1024:
            self._stx_status_stream_buffer = self._stx_status_stream_buffer[-1024:]

    def _method_stx_status_weight_stream_scan(self) -> Optional[float]:
        if not self._stx_status_stream_buffer:
            return None
        matches = list(self._STX_STATUS_WEIGHT_FRAME_RE.finditer(self._stx_status_stream_buffer))
        if matches:
            try:
                w = float(matches[-1].group(1).decode("ascii"))
                if len(self._stx_status_stream_buffer) > 512:
                    self._stx_status_stream_buffer = self._stx_status_stream_buffer[-512:]
                return w
            except ValueError:
                pass
        return None

    def _is_kg_stream_context(self, raw_data: bytes, text: str) -> bool:
        if self._is_paren_weight_stream_context(raw_data, text):
            return False
        if self._is_stx_status_weight_stream_context(raw_data, text):
            return False
        if self._is_euro_weight_stream_context(raw_data, text):
            return False
        if self._kg_stream_established():
            return True
        if b"kg" in raw_data.lower():
            return True
        if text and re.search(r"\d+\s*kg\b", text, re.IGNORECASE):
            return True
        if b"\x02" in raw_data and b"kg" not in raw_data.lower() and b"\x02)" not in raw_data:
            after_stx = text.split("\x02", 1)[-1] if text else ""
            if re.fullmatch(r"[\s\d]*", after_stx):
                return True
        return False

    def _kg_stream_established(self) -> bool:
        if not self._kg_stream_buffer:
            return False
        buf_text = self._normalize_kg_framing(
            self._kg_stream_buffer.decode("ascii", errors="ignore")
        )
        if self._KG_GA_FRAME_RE.search(buf_text):
            return True
        return bool(re.search(r"\d+\s*kg\b", buf_text, re.IGNORECASE))

    def _accumulate_kg_stream_buffer(self, raw_data: bytes) -> None:
        self._kg_stream_buffer += raw_data
        if len(self._kg_stream_buffer) > 1024:
            self._kg_stream_buffer = self._kg_stream_buffer[-1024:]

    def _method_kg_stream_scan(self) -> Optional[float]:
        if not self._kg_stream_buffer:
            return None
        text = self._normalize_kg_framing(
            self._kg_stream_buffer.decode("ascii", errors="ignore")
        )
        matches = list(self._KG_GA_FRAME_RE.finditer(text))
        if matches:
            try:
                w = float(matches[-1].group(1))
                if len(self._kg_stream_buffer) > 256:
                    self._kg_stream_buffer = self._kg_stream_buffer[-256:]
                return w
            except ValueError:
                pass
        return self._method_kg(text)

    def get_live_weight(self, fresh_only: bool = False) -> Optional[float]:
        """Return latest weight from rolling stream buffers without new serial bytes."""
        if self._paren_stream_established():
            w = self._method_paren_weight_stream_scan()
            if w is not None:
                return w
        if self._stx_status_stream_established():
            w = self._method_stx_status_weight_stream_scan()
            if w is not None:
                return w
        if self._euro_weight_stream_buffer and (
            self._euro_weight_stream_established() or b"\x80" in self._euro_weight_stream_buffer
        ):
            w = self._method_euro_weight_stream_scan()
            if w is not None:
                return w
        if self._kg_stream_established():
            w = self._method_kg_stream_scan()
            if w is not None:
                return w
        if fresh_only:
            return None
        return self._last_weight

    # =====================================================================
    # HELPER METHODS FOR CONFIGURABLE CONVERSION MODES
    # =====================================================================

    def _convert_by_method(self, method_id: str, raw_data: bytes, text: str) -> Optional[float]:
        """
        Dispatch to a specific conversion sub-method by ID.

        This is used by:
          - Weighbridge-App at runtime (single selected method)
          - IoT-Configuration preview endpoint (trying multiple methods)
        """
        method = (method_id or "").strip().lower()

        if method == "bracket":
            return self._method_bracket(text)
        if method == "stx_paren":
            self._accumulate_paren_stream_buffer(raw_data)
            return self._method_paren_weight_stream_scan()
        if method == "stx_status":
            self._accumulate_stx_status_stream_buffer(raw_data)
            return self._method_stx_status_weight_stream_scan()
        if method == "euro_weight":
            self._accumulate_euro_weight_stream_buffer(raw_data)
            return self._method_euro_weight_stream_scan()
        if method == "kg":
            self._accumulate_kg_stream_buffer(raw_data)
            return self._method_kg_stream_scan() or self._method_kg(text)
        if method == "ga":
            return self._method_ga(text)
        if method == "wt":
            return self._method_wt(raw_data)
        if method == "st_gs":
            return self._method_st_gs(text)
        if method == "prefix":
            return self._method_prefix(text)
        if method == "hyper_1bh":
            return self._method_hyper_1bh(text)
        if method == "p_at_pct":
            return self._method_p_at_pct_scan()
        if method == "plain_ascii":
            return self._method_plain_ascii(text)
        if method == "index_based":
            if not self._index_config_ready or not self._indexing_dict:
                return None
            from digitizer_index_engine import extract_weight_from_indexing

            return extract_weight_from_indexing(raw_data, self._indexing_dict)

        # Unknown method ID
        logger.warning(f"Unknown digitizer conversion method id: {method_id}")
        return None

    def _finalize_weight(self, weight: float, raw_data: bytes) -> Optional[float]:
        """
        Apply standard sanity checks and store last_weight.
        """
        weight = abs(float(weight))
        if weight > 200000:
            w_euro = self._method_euro_weight_stream_scan()
            if w_euro is not None and 0 <= w_euro <= 200000:
                weight = w_euro
            elif self._last_weight is not None and 0 <= self._last_weight <= 200000:
                return self._last_weight
            else:
                logger.warning(
                    "Weight out of range (likely glued euro frames): %s kg (raw: %s)",
                    weight,
                    raw_data.hex()[:80],
                )
                return None

        if 0 <= weight <= 200000:
            self._last_weight = weight
            logger.debug(f"Weight converted: {weight} kg")
            return weight

        logger.warning(f"Weight out of range: {weight} kg (raw: {raw_data.hex()})")
        return None

    # --- Individual method implementations used for previews / selection ---

    def _method_bracket(self, text: str) -> Optional[float]:
        """
        BRACKET FORMAT: [000000][000080]...[000080]
        Uses the last bracket value.
        """
        bracket_matches = re.findall(r'\[(\d+)\]', text)
        if not bracket_matches:
            return None
        weight_str = bracket_matches[-1]
        try:
            return float(weight_str)
        except ValueError:
            return None

    def _method_kg(self, text: str) -> Optional[float]:
        """
        "  20 kg    G 000000 A" style, or "11290kg" (no space).
        Uses the last "digits + kg" match in a stream buffer.
        """
        t = self._normalize_kg_framing(text)
        pat = re.compile(r'([+-]?\d+)\s*kg\b', re.IGNORECASE)
        last: Optional[re.Match] = None
        for m in pat.finditer(t):
            last = m
        if not last:
            return None
        try:
            return float(last.group(1))
        except ValueError:
            return None

    def _method_ga(self, text: str) -> Optional[float]:
        """
        Garbled G ... A format: G 000000 A, G 004200 A, etc.
        """
        match = re.search(r'G\s*([+-]?\d+)\s*A', text, re.IGNORECASE)
        if not match:
            return None
        try:
            return float(match.group(1))
        except ValueError:
            return None

    def _method_wt(self, raw_data: bytes) -> Optional[float]:
        """
        "WT:" / "Wt:" buffered format.

        Supports:
          - HyperTerminal style: "$WT:      0" or "$WT:   47560" (one per line, no space before colon).
          - Legacy: "Wt:  58940♥0⚠Wt:" (garbled); "$WT :              47560" (space before colon).
        """
        # Add current data to buffer
        self._raw_buffer += raw_data

        # Limit buffer size
        if len(self._raw_buffer) > 200:
            self._raw_buffer = self._raw_buffer[-200:]

        # Decode buffer to ASCII text for regex parsing
        buf_text = self._raw_buffer.decode('ascii', errors='ignore')

        # Case-insensitive match for optional '$', WT, ':', then a number
        # This also matches "Wt:" because of case-insensitive WT.
        pattern = re.compile(r'(?i)\$?\s*WT\s*:\s*([+-]?\d+(?:\.\d+)?)')
        last_match: Optional[re.Match] = None
        for m in pattern.finditer(buf_text):
            last_match = m

        if not last_match:
            return None

        try:
            weight = float(last_match.group(1))
        except ValueError:
            return None

        # Keep a small tail to allow next reading to be detected
        if len(self._raw_buffer) > 30:
            self._raw_buffer = self._raw_buffer[-30:]
        else:
            self._raw_buffer = b""

        return weight

    def _method_st_gs(self, text: str) -> Optional[float]:
        """
        ST,GS format: ST,GS,+0040740kg
        """
        clean = text.replace('\r', '').replace('\n', '').strip()
        if not (clean.startswith('ST,GS,') or 'ST,GS,' in clean):
            return None
        match = re.search(r'ST,GS,([+-]?\d+(?:\.\d+)?)', clean)
        if not match:
            return None
        try:
            return float(match.group(1))
        except ValueError:
            return None

    def _method_prefix(self, text: str) -> Optional[float]:
        """
        Prefix format: weight digits at start followed by garbage, e.g. "50ePG%w".
        """
        text_clean = text.replace('\r', '').replace('\n', '').strip()
        match = re.match(r'^([+-]?\d+(?:\.\d+)?)', text_clean)
        if not match:
            return None
        try:
            return float(match.group(1))
        except ValueError:
            return None

    def _method_hyper_1bh(self, text: str) -> Optional[float]:
        """
        HyperTerminal stream format: repeated "1BH0xxxxx" frames with optional noise.
        Example: 1BH0828001BH082800?P`@1BH082800?M@2...
        """
        if not text:
            return None

        self._hb_stream_buffer += text
        if len(self._hb_stream_buffer) > 500:
            self._hb_stream_buffer = self._hb_stream_buffer[-500:]

        matches = list(re.finditer(r'1BH0(\d{5})(?!\d)', self._hb_stream_buffer))
        if not matches:
            return None

        try:
            return float(matches[-1].group(1))
        except ValueError:
            return None

    def _method_p_at_pct_scan(self) -> Optional[float]:
        """
        HyperTerminal stream: weight token then vendor marker.

        The device family uses many firmware-dependent markers after
        ``<digits><letter>``.  Known non-zero examples:

          - 50eP@%p   -> 50 kg      (P@%)
          - 41940dQ@!v -> 41940 kg   (Q@!)
          - 70gPB%t   -> 70 kg      (PB%)
          - 60fPC y   -> 60 kg      (PC)
          - 60fP@!w   -> 60 kg      (P@!)

        Generalised pattern: ``(\\d+)([A-Za-z])[PQ][^0-9]``

        Zero: standalone ``0`` + backtick + ``P`` + uppercase letter
              e.g. ``0`PI y``  (not the trailing 0 inside 41940).
        """
        buf = self._pat_pct_buffer
        if not buf:
            return None

        # Generalised: digits + one letter + P/Q + any non-digit char.
        # Covers P@%, Q@!, PB%, PC, P@! and future firmware variants.
        matches = list(
            re.finditer(r"(\d+)([A-Za-z])[PQ][^0-9]", buf)
        )
        if matches:
            try:
                w = float(matches[-1].group(1))
                if w > 200000:
                    return None
                logger.info(
                    "Weight decoded via P/Q-marker token: %s kg (fragment=%r)",
                    w,
                    matches[-1].group(0)[:48],
                )
                return w
            except ValueError:
                pass

        # Zero stream: 0`P<uppercase> — must not match trailing 0 of e.g. 41940
        if re.search(r"(?<![0-9])0[\x60`]P[A-Z]", buf):
            logger.info("Weight decoded via P-marker zero-stream token: 0 kg")
            return 0.0

        return None

    def _method_plain_ascii(self, text: str) -> Optional[float]:
        """
        Plain ASCII with spaces/padding (generic fallback).
        """
        text_no_crlf = text.replace('\r', '').replace('\n', '')
        text_clean = re.sub(r'[kKgG]', '', text_no_crlf)
        match = re.search(r'[-+]?\s*(\d+(?:\.\d+)?)', text_clean)
        if not match:
            return None
        try:
            return float(match.group(1))
        except ValueError:
            return None
    
    def convert_accumulated(self, raw_data: bytes) -> Optional[float]:
        """
        Alternative conversion for character-by-character data.
        
        Accumulates data in buffer and returns weight only when complete.
        Call this for digitizers that send one character at a time.
        
        Args:
            raw_data: Raw bytes (may be single character)
            
        Returns:
            Weight in KG when complete reading available, None otherwise
        """
        try:
            # Add to buffer
            text = raw_data.decode('ascii', errors='ignore')
            self._buffer += text
            
            logger.debug(f"Buffer now: '{self._buffer}'")
            
            # Check for end-of-reading markers
            # Common markers: CR, LF, ETX (0x03)
            if '\r' in self._buffer or '\n' in self._buffer or '\x03' in self._buffer:
                # Extract weight from buffer
                clean = self._buffer.replace('\r', '').replace('\n', '').replace('\x03', '').strip()
                
                # Extract numeric value
                match = re.search(r'[-+]?\s*(\d+(?:\.\d+)?)', clean)
                if match:
                    weight = float(match.group(1))
                    logger.debug(f"Weight from accumulated data: {weight} kg")
                    self._buffer = ""  # Clear buffer
                    self._last_weight = weight
                    return weight
                
                # Clear buffer if no valid number found
                self._buffer = ""
            
            return None
            
        except Exception as e:
            logger.error(f"Accumulated conversion error: {e}")
            self._buffer = ""
            return None
    
    def clear_buffer(self) -> None:
        """Clear the accumulation buffer"""
        self._buffer = ""
        logger.debug("Digitizer buffer cleared")
    
    def get_buffer(self) -> str:
        """Get current buffer contents (for debugging)"""
        return self._buffer
    
    def get_last_raw_data(self) -> bytes:
        """Get the last raw data received (for debugging)"""
        return self._last_raw_data
    
    def get_last_weight(self) -> Optional[float]:
        """Get the last successfully converted weight"""
        return self._last_weight
    
    def debug_print(self, raw_data: bytes) -> None:
        """
        Print detailed debug information about raw data.
        
        Call this method to analyze unknown digitizer data formats.
        """
        print("\n" + "=" * 60)
        print("DIGITIZER DEBUG INFORMATION")
        print("=" * 60)
        print(f"Raw bytes length: {len(raw_data)}")
        print(f"Raw bytes (hex): {raw_data.hex()}")
        print(f"Raw bytes (repr): {repr(raw_data)}")
        
        try:
            print(f"ASCII decode: '{raw_data.decode('ascii', errors='replace')}'")
        except:
            print("ASCII decode: Failed")
        
        print(f"Current buffer: '{self._buffer}'")
        
        print("\nByte-by-byte breakdown:")
        for i, b in enumerate(raw_data):
            char_repr = chr(b) if 32 <= b <= 126 else '.'
            print(f"  [{i:3d}] 0x{b:02X} ({b:3d}) '{char_repr}'")
        
        print("=" * 60 + "\n")


# =============================================================================
# CONVENIENCE INSTANCES
# =============================================================================

# Global converter instances (can be used directly or create new instances)
rfid_converter = RFID_Convert()
digitizer_converter = Digitizer_Convert()


def convert_rfid(raw_data: bytes) -> Optional[str]:
    """
    Convenience function to convert RFID data.
    
    Args:
        raw_data: Raw bytes from RFID reader
        
    Returns:
        24-char hex string or None
    """
    return rfid_converter.convert(raw_data)


def convert_weight(raw_data: bytes) -> Optional[float]:
    """
    Convenience function to convert weight data.
    
    Args:
        raw_data: Raw bytes from digitizer
        
    Returns:
        Weight in KG or None
    """
    return digitizer_converter.convert(raw_data)


#26-6-2026