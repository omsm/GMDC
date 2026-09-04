"""
PDF Report Generator for IoT Configuration Setup
Generates a comprehensive PDF report with all device configurations and snapshots.
"""

import os
import sys
import json
import logging
from datetime import datetime
from io import BytesIO
import base64

try:
    from reportlab.lib.pagesizes import A4, letter
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

try:
    from config import ENABLE_CAMERA_CONFIGURATION
except ImportError:
    ENABLE_CAMERA_CONFIGURATION = True

logger = logging.getLogger(__name__)


class PDFReportGenerator:
    """Generate PDF reports for IoT configuration setup"""
    
    def __init__(self, config_manager):
        self.config_manager = config_manager
        if not REPORTLAB_AVAILABLE:
            logger.warning("reportlab not available - PDF generation disabled")
        if not CV2_AVAILABLE:
            logger.warning("opencv-python not available - camera snapshots disabled")

    @staticmethod
    def _is_bidirectional_layout(config):
        wb_type = config.get("wb_type") or config.get("weighbridge_layout", "unidirectional")
        return wb_type == "bidirectional"

    @staticmethod
    def _weighbridge_layout_label(config):
        if PDFReportGenerator._is_bidirectional_layout(config):
            return "Bidirectional"
        return "Unidirectional"

    @staticmethod
    def _pdf_section_number(section_with_camera: int) -> int:
        """Renumber PDF sections when the camera wizard is disabled."""
        if ENABLE_CAMERA_CONFIGURATION or section_with_camera <= 3:
            return section_with_camera
        return section_with_camera - 1
    
    def capture_camera_snapshot(self, rtsp_url, timeout=5):
        """
        Capture a snapshot from an RTSP camera stream.

        Args:
            rtsp_url: RTSP URL of the camera
            timeout: Reserved for future bounded capture (FFMPEG timeouts are not reliable on all builds)

        Returns:
            BytesIO object with image data, or None if failed
        """
        if not CV2_AVAILABLE or not rtsp_url:
            return None

        try:
            cap = cv2.VideoCapture(rtsp_url)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            ret, frame = cap.read()
            cap.release()

            if ret and frame is not None:
                _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                return BytesIO(buffer.tobytes())
            logger.warning("Failed to capture snapshot for PDF report")
            return None
        except Exception as e:
            logger.error(f"Error capturing camera snapshot: {e}")
            return None
    
    def _create_table(self, data, col_widths=None):
        """Helper to create a styled table"""
        if col_widths is None:
            col_widths = [2.5*inch, 4.5*inch]
        table = Table(data, colWidths=col_widths, repeatRows=0)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#ecf0f1')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),  # Align content to top for wrapped text
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),  # Increased padding for wrapped text
            ('TOPPADDING', (0, 0), (-1, -1), 10),  # Increased padding for wrapped text
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ]))
        return table

    def _format_sensor_setup_test(self, sensor_config):
        """Human-readable WB/sensor setup test outcome from optional validated tri-state."""
        if not isinstance(sensor_config, dict):
            return 'Not recorded'
        validated = sensor_config.get('validated', False)
        if validated is True:
            return 'Tested (validated)'
        if validated is None:
            return 'Skipped'
        return 'Not tested'

    def _format_sensor_setup_test_boolean(self, sensor_config):
        """Entry/exit sensors: validated is true or false only."""
        if not isinstance(sensor_config, dict):
            return 'Not recorded'
        return 'Tested (validated)' if sensor_config.get('validated') is True else 'Not tested'
    
    def _create_status_table_data(self, config, styles):
        """
        Create status table data showing all components and their validation status.
        
        Args:
            config: Configuration dictionary
            styles: ReportLab styles object
            
        Returns:
            List of [Component, Status] rows
        """
        status_data = []
        
        # Create status paragraph styles
        success_style = ParagraphStyle(
            'StatusSuccess', parent=styles['Normal'], textColor=colors.HexColor('#27ae60'),
            fontSize=10, fontName='Helvetica-Bold'
        )
        skipped_style = ParagraphStyle(
            'StatusSkipped', parent=styles['Normal'], textColor=colors.HexColor('#f39c12'),
            fontSize=10, fontName='Helvetica-Bold'
        )
        failed_style = ParagraphStyle(
            'StatusFailed', parent=styles['Normal'], textColor=colors.HexColor('#e74c3c'),
            fontSize=10, fontName='Helvetica-Bold'
        )
        
        # Server Configuration
        server_config = config.get('server', {})
        if server_config.get('validated'):
            status_data.append(['Server Configuration', Paragraph('✓ Success', success_style)])
        elif server_config.get('type') == 'skip' or server_config.get('validated') is None:
            status_data.append(['Server Configuration', Paragraph('⚠ Skipped', skipped_style)])
        else:
            status_data.append(['Server Configuration', Paragraph('✗ Not Validated', failed_style)])
        
        # RFID Configuration
        if self._is_bidirectional_layout(config):
            rfids = config.get('rfids') or {}
            for label, key in [('ENTRY A RFID', 'entry_a'), ('ENTRY B RFID', 'entry_b')]:
                rc = rfids.get(key) or {}
                if rc.get('validated') is True:
                    status_data.append([label, Paragraph('✓ Success', success_style)])
                elif rc.get('validated') is None:
                    status_data.append([label, Paragraph('⚠ Skipped', skipped_style)])
                else:
                    status_data.append([label, Paragraph('✗ Not Validated', failed_style)])
        else:
            rfid_config = config.get('rfid', {})
            if rfid_config.get('validated'):
                status_data.append(['RFID Configuration', Paragraph('✓ Success', success_style)])
            elif rfid_config.get('type') == 'skip' or rfid_config.get('validated') is None:
                status_data.append(['RFID Configuration', Paragraph('⚠ Skipped', skipped_style)])
            else:
                status_data.append(['RFID Configuration', Paragraph('✗ Not Validated', failed_style)])
        
        # Top Camera Configuration
        if ENABLE_CAMERA_CONFIGURATION:
            camera_config = config.get('camera', {})
            top_camera = camera_config.get('top', {})
            if top_camera.get('validated'):
                status_data.append(['Top Camera Configuration', Paragraph('✓ Success', success_style)])
            elif top_camera.get('type') == 'skip' or top_camera.get('validated') is None:
                status_data.append(['Top Camera Configuration', Paragraph('⚠ Skipped', skipped_style)])
            else:
                status_data.append(['Top Camera Configuration', Paragraph('✗ Not Validated', failed_style)])

            # Front Camera Configuration
            front_camera = camera_config.get('front', {})
            if front_camera.get('validated'):
                status_data.append(['Front Camera Configuration', Paragraph('✓ Success', success_style)])
            elif front_camera.get('type') == 'skip' or front_camera.get('validated') is None:
                status_data.append(['Front Camera Configuration', Paragraph('⚠ Skipped', skipped_style)])
            else:
                status_data.append(['Front Camera Configuration', Paragraph('✗ Not Validated', failed_style)])
        
        # Display Configuration
        display_config = config.get('display', {})
        if display_config.get('type') == 'skip':
            status_data.append(['Display Configuration', Paragraph('⚠ Skipped', skipped_style)])
        elif display_config.get('validated'):
            status_data.append(['Display Configuration', Paragraph('✓ Success', success_style)])
        else:
            status_data.append(['Display Configuration', Paragraph('✗ Not Validated', failed_style)])
        
        # I/O Controller Configuration
        io_config = config.get('io_controller', {})
        if io_config.get('validated'):
            status_data.append(['I/O Controller Configuration', Paragraph('✓ Success', success_style)])
        elif io_config.get('type') == 'skip' or io_config.get('validated') is None:
            status_data.append(['I/O Controller Configuration', Paragraph('⚠ Skipped', skipped_style)])
        else:
            status_data.append(['I/O Controller Configuration', Paragraph('✗ Not Validated', failed_style)])
        
        # Sensors (1, 2, 3)
        sensors_config = io_config.get('sensors', {})
        for i in range(1, 4):
            sensor_key = f'sensor{i}'
            sensor = sensors_config.get(sensor_key, {})
            if io_config.get('validated'):
                status_data.append([f'Sensor {i} Configuration', Paragraph('✓ Success', success_style)])
            elif io_config.get('type') == 'skip' or io_config.get('validated') is None:
                status_data.append([f'Sensor {i} Configuration', Paragraph('⚠ Skipped', skipped_style)])
            else:
                status_data.append([f'Sensor {i} Configuration', Paragraph('✗ Not Validated', failed_style)])
        
        # Traffic Lights
        traffic_lights_config = io_config.get('traffic_lights', {})
        if self._is_bidirectional_layout(config):
            for dir_label, dir_key in [('ENTRY A', 'entry_a'), ('ENTRY B', 'entry_b')]:
                dmeta = traffic_lights_config.get(dir_key) or {}
                for light_type in ['Entry', 'Exit']:
                    light_key = light_type.lower()
                    tl_info = dmeta.get(light_key, {}) if isinstance(dmeta, dict) else {}
                    tl_validated = tl_info.get('validated', False) if isinstance(tl_info, dict) else False
                    row_label = f'{dir_label} {light_type} Traffic Light'
                    if tl_validated is True:
                        status_data.append([row_label, Paragraph('✓ Success', success_style)])
                    elif tl_validated is None:
                        status_data.append([row_label, Paragraph('⚠ Skipped', skipped_style)])
                    else:
                        status_data.append([row_label, Paragraph('✗ Not Validated', failed_style)])
        else:
            for light_type in ['Entry', 'Exit']:
                light_key = light_type.lower()
                tl_info = traffic_lights_config.get(light_key, {})
                if not isinstance(tl_info, dict):
                    tl_info = {}
                tl_validated = tl_info.get('validated', False)
                if tl_validated is True:
                    status_data.append([f'{light_type} Traffic Light Configuration', Paragraph('✓ Success', success_style)])
                elif tl_validated is None:
                    status_data.append([f'{light_type} Traffic Light Configuration', Paragraph('⚠ Skipped', skipped_style)])
                else:
                    status_data.append([f'{light_type} Traffic Light Configuration', Paragraph('✗ Not Validated', failed_style)])
        
        # Boom Barriers
        boom_barriers_config = io_config.get('boom_barriers', {})
        for barrier_type in ['Entry', 'Exit']:
            barrier_key = barrier_type.lower()
            bb_info = boom_barriers_config.get(barrier_key, {})
            if not isinstance(bb_info, dict):
                bb_info = {}
            bb_validated = bb_info.get('validated', False)
            if bb_validated is True:
                status_data.append([f'{barrier_type} Boom Barrier Configuration', Paragraph('✓ Success', success_style)])
            elif bb_validated is None:
                status_data.append([f'{barrier_type} Boom Barrier Configuration', Paragraph('⚠ Skipped', skipped_style)])
            else:
                status_data.append([f'{barrier_type} Boom Barrier Configuration', Paragraph('✗ Not Validated', failed_style)])
        
        # Digitizer Configuration
        digitizer_config = config.get('digitizer', {})
        if digitizer_config.get('validated'):
            status_data.append(['Digitizer Configuration', Paragraph('✓ Success', success_style)])
        elif digitizer_config.get('type') == 'skip' or digitizer_config.get('validated') is None:
            status_data.append(['Digitizer Configuration', Paragraph('⚠ Skipped', skipped_style)])
        else:
            status_data.append(['Digitizer Configuration', Paragraph('✗ Not Validated', failed_style)])
        
        # Audio System Configuration
        voice_config = config.get('voice', {})
        audio_config = config.get('audio', {})
        if voice_config.get('validated') or audio_config.get('validated'):
            status_data.append(['Audio System Configuration', Paragraph('✓ Success', success_style)])
        elif voice_config.get('type') == 'skip' or audio_config.get('type') == 'skip' or (voice_config.get('validated') is None and audio_config.get('validated') is None):
            status_data.append(['Audio System Configuration', Paragraph('⚠ Skipped', skipped_style)])
        else:
            status_data.append(['Audio System Configuration', Paragraph('✗ Not Validated', failed_style)])
        
        return status_data
    
    def generate_report(self, config_data=None):
        """
        Generate a PDF report and return as BytesIO buffer with filename.
        
        Args:
            config_data: Optional config dict. If None, uses config_manager.
            
        Returns:
            Tuple of (BytesIO buffer, filename)
        """
        filename = f"report.pdf"
        
        buffer = self.generate_pdf(output_path=None)
        return buffer, filename
    
    def generate_pdf(self, output_path=None):
        """
        Generate a comprehensive PDF report with all configuration details.
        
        Args:
            output_path: Path to save PDF file. If None, returns BytesIO object.
            
        Returns:
            Path to saved file or BytesIO object
        """
        if not REPORTLAB_AVAILABLE:
            raise ImportError("reportlab is required for PDF generation")
        
        config = self.config_manager.get_all()
        setup_info = config.get('setup_info', {})

        # Load weighbridge info (ID & Name) from wb_info.json if available
        wb_id = "N/A"
        wb_name = "N/A"
        try:
            # Reuse the same base_path logic as config_manager for config files
            if getattr(sys, 'frozen', False):
                base_path = os.path.dirname(sys.executable)
            else:
                # Running as script - project root is one level above this services/ directory
                base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

            wb_info_path = os.path.join(base_path, "wb_info.json")
            if os.path.exists(wb_info_path):
                try:
                    # First, try normal UTF-8 (no BOM)
                    with open(wb_info_path, "r", encoding="utf-8") as f:
                        wb_info = json.load(f)
                except Exception:
                    # Fallback: handle files saved as UTF-8 with BOM on some PCs
                    with open(wb_info_path, "r", encoding="utf-8-sig") as f:
                        wb_info = json.load(f)

                # Support both flat and nested {"Data": {...}} structures
                data = wb_info.get("Data", wb_info)
                wb_id = data.get("wb_id", wb_id)
                wb_name = data.get("wb_name", wb_name)

        except Exception as e:
            logger.warning(f"Failed to load wb_info.json for report header: {e}")
        
        # Create PDF document
        if output_path:
            doc = SimpleDocTemplate(output_path, pagesize=A4)
        else:
            buffer = BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4)
        
        # Container for PDF elements
        story = []
        
        # Get styles
        styles = getSampleStyleSheet()
        
        # =====================================================================
        # Cover Page
        # =====================================================================
        cover_title_style = ParagraphStyle(
            'CoverTitle',
            parent=styles['Heading1'],
            fontSize=28,
            textColor=colors.HexColor('#1a1a1a'),
            spaceAfter=40,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold',
            leading=36
        )
        cover_subtitle_style = ParagraphStyle(
            'CoverSubtitle',
            parent=styles['Normal'],
            fontSize=14,
            textColor=colors.HexColor('#7f8c8d'),
            spaceAfter=20,
            alignment=TA_CENTER,
            leading=18
        )
        
        # Add vertical spacing for centering
        story.append(Spacer(1, 2.5*inch))
        
        # Main title
        story.append(Paragraph("Weighbridge Automation", cover_title_style))
        story.append(Spacer(1, 0.3*inch))
        story.append(Paragraph("Configuration Report", cover_title_style))
        
        story.append(Spacer(1, 1*inch))
        
        # Subtitle/Date
        report_date = datetime.now().strftime('%B %d, %Y')
        story.append(Paragraph(f"Generated on {report_date}", cover_subtitle_style))
        
        # Add page break after cover
        story.append(PageBreak())
        
        # Regular styles for content pages
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1a1a1a'),
            spaceAfter=30,
            alignment=TA_CENTER
        )
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=16,
            textColor=colors.HexColor('#2c3e50'),
            spaceAfter=12,
            spaceBefore=20
        )
        subheading_style = ParagraphStyle(
            'CustomSubHeading',
            parent=styles['Heading3'],
            fontSize=12,
            textColor=colors.HexColor('#34495e'),
            spaceAfter=8,
            spaceBefore=12
        )
        
        # =====================================================================
        # Device Status Table (Page 2)
        # =====================================================================
        status_heading_style = ParagraphStyle(
            'StatusHeading',
            parent=styles['Heading1'],
            fontSize=18,
            textColor=colors.HexColor('#2c3e50'),
            spaceAfter=20,
            spaceBefore=10,
            alignment=TA_CENTER
        )
        story.append(Paragraph("Device Configuration Status", status_heading_style))
        story.append(Spacer(1, 0.3*inch))
        
        # Create status table data
        status_table_data = self._create_status_table_data(config, styles)
        # Add header row
        status_table_data.insert(0, [
            Paragraph('<b>Component</b>', styles['Normal']),
            Paragraph('<b>Device Status</b>', styles['Normal'])
        ])
        
        # Create and style the status table
        status_table = Table(status_table_data, colWidths=[4*inch, 3*inch])
        status_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e6e6e6')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
        ]))
        story.append(status_table)
        story.append(Spacer(1, 0.5*inch))
        
        # Page break after status table
        story.append(PageBreak())
        
        # Title
        story.append(Paragraph("Device Configuration Setup Report", title_style))
        story.append(Spacer(1, 0.0001*inch))
        
        # =====================================================================
        # 1. Setup Information
        # =====================================================================
        story.append(Paragraph("1. Setup Information", heading_style))
        
        setup_data = [
            ['Weighbridge ID:', wb_id],
            ['Weighbridge Name:', wb_name],
            ['Weighbridge type:', self._weighbridge_layout_label(config)],
            ['Vendor Company:', setup_info.get('vendor_company', 'N/A')],
            ['Verified By:', setup_info.get('verified_by', 'N/A')],
            ['Verification Date:', setup_info.get('verification_date', 'N/A')],
        ]
        
        if setup_info.get('remarks'):
            setup_data.append(['Remarks:', setup_info.get('remarks')])
        
        story.append(self._create_table(setup_data))
        story.append(Spacer(1, 0.1*inch))
        
        # =====================================================================
        # 2. Server Configuration
        # =====================================================================
        story.append(Paragraph("2. Server Configuration", heading_style))
        server_config = config.get('server', {})
        server_data = [
            ['IP Address:', server_config.get('ip', 'N/A')],
            ['Port:', server_config.get('port', 'N/A')],
            ['Status:', '✓ Validated' if server_config.get('validated') else '✗ Not Validated'],
        ]
        story.append(self._create_table(server_data))
        story.append(Spacer(1, 0.1*inch))
        
        # =====================================================================
        # 3. RFID Reader Configuration
        # =====================================================================
        story.append(Paragraph("3. RFID Reader Configuration", heading_style))

        def _rfid_mode_label(rfid_mode):
            if rfid_mode == 'CLIENT':
                return 'Server'
            if rfid_mode == 'SERVER':
                return 'Client'
            return rfid_mode

        def _append_rfid_table(rfid_config, title=None):
            if title:
                story.append(Paragraph(title, subheading_style))
            rfid_mode = rfid_config.get('mode', 'N/A')
            rfid_data = [
                ['IP Address:', rfid_config.get('ip', 'N/A')],
                ['Port:', rfid_config.get('port', 'N/A')],
                ['Mode:', _rfid_mode_label(rfid_mode)],
                ['Make:', rfid_config.get('make', 'N/A')],
                ['Model:', rfid_config.get('model', 'N/A')],
                ['Status:', '✓ Validated' if rfid_config.get('validated') else '✗ Not Validated'],
            ]
            story.append(self._create_table(rfid_data))
            story.append(Spacer(1, 0.15 * inch))

        if self._is_bidirectional_layout(config):
            rfids = config.get('rfids') or {}
            _append_rfid_table(rfids.get('entry_a') or {}, 'ENTRY A')
            _append_rfid_table(rfids.get('entry_b') or {}, 'ENTRY B')
        else:
            _append_rfid_table(config.get('rfid') or {})

        # Page break after Setup + Server + RFID sections
        story.append(PageBreak())
        
        # =====================================================================
        # 4. Camera Configuration (optional)
        # =====================================================================
        if ENABLE_CAMERA_CONFIGURATION:
            story.append(Paragraph("4. Camera Configuration", heading_style))
            camera_config = config.get('camera', {})
            # When the camera wizard is disabled, do not open RTSP during PDF build - stale URLs can hang OpenCV indefinitely.
            pdf_camera_snapshots = CV2_AVAILABLE
            
            # Top Camera
            story.append(Paragraph("Top Camera", subheading_style))
            top_camera = camera_config.get('top', {})
            
            # Try to capture top camera snapshot (if available)
            top_snapshot_img = None
            top_rtsp = top_camera.get('rtsp_url', '')
            if top_rtsp and pdf_camera_snapshots:
                snapshot = self.capture_camera_snapshot(top_rtsp)
                if snapshot:
                    try:
                        top_snapshot_img = Image(snapshot, width=1*inch, height=0.5*inch)
                    except Exception as e:
                        logger.warning(f"Could not create top camera snapshot image for table: {e}")
            
            # Create a style for wrapping long URLs
            url_wrap_style = ParagraphStyle(
                'URLWrap',
                parent=styles['Normal'],
                fontSize=9,
                leading=12,
                wordWrap='CJK'  # Enables word wrapping
            )
            
            # Convert RTSP URL to Paragraph for word wrapping
            top_rtsp_url = top_camera.get('rtsp_url', 'N/A')
            if top_rtsp_url != 'N/A':
                top_rtsp_para = Paragraph(top_rtsp_url.replace('&', '&amp;'), url_wrap_style)
            else:
                top_rtsp_para = 'N/A'
            
            top_camera_data = [
                ['RTSP URL:', top_rtsp_para],
                ['Make:', top_camera.get('make', 'N/A')],
                ['Model:', top_camera.get('model', 'N/A')],
                ['Status:', '✓ Validated' if top_camera.get('validated') else '✗ Not Validated'],
            ]
            # Add snapshot inside table if available
            if top_snapshot_img is not None:
                top_camera_data.append(['Image:', top_snapshot_img])
            
            story.append(self._create_table(top_camera_data))
            story.append(Spacer(1, 0.2*inch))
            
            # Front Camera
            story.append(Paragraph("Front Camera", subheading_style))
            front_camera = camera_config.get('front', {})
            
            # Try to capture front camera snapshot (if available)
            front_snapshot_img = None
            front_rtsp = front_camera.get('rtsp_url', '')
            if front_rtsp and pdf_camera_snapshots:
                snapshot = self.capture_camera_snapshot(front_rtsp)
                if snapshot:
                    try:
                        front_snapshot_img = Image(snapshot, width=1*inch, height=0.5*inch)
                    except Exception as e:
                        logger.warning(f"Could not create front camera snapshot image for table: {e}")
            
            # Convert RTSP URL to Paragraph for word wrapping
            front_rtsp_url = front_camera.get('rtsp_url', 'N/A')
            if front_rtsp_url != 'N/A':
                front_rtsp_para = Paragraph(front_rtsp_url.replace('&', '&amp;'), url_wrap_style)
            else:
                front_rtsp_para = 'N/A'
            
            front_camera_data = [
                ['RTSP URL:', front_rtsp_para],
                ['Make:', front_camera.get('make', 'N/A')],
                ['Model:', front_camera.get('model', 'N/A')],
                ['Status:', '✓ Validated' if front_camera.get('validated') else '✗ Not Validated'],
            ]
            # Add snapshot inside table if available
            if front_snapshot_img is not None:
                front_camera_data.append(['Image:', front_snapshot_img])
            
            story.append(self._create_table(front_camera_data))
            story.append(Spacer(1, 0.3*inch))

            # Page break after Camera Configuration
            story.append(PageBreak())
        
        # =====================================================================
        # 5. Display Configuration
        # =====================================================================
        display_config = config.get('display', {})
        if display_config.get('type') != 'skip':
            story.append(Paragraph(f"{self._pdf_section_number(5)}. Display Configuration", heading_style))
            display_data = [
                ['Type:', display_config.get('type', 'N/A')],
                ['IP Address:', display_config.get('ip', 'N/A')],
                ['Port:', display_config.get('port', 'N/A')],
                ['Make:', display_config.get('make', 'N/A')],
                ['Model:', display_config.get('model', 'N/A')],
                ['Status:', '✓ Validated' if display_config.get('validated') else '✗ Not Validated'],
            ]
            story.append(self._create_table(display_data))
            story.append(Spacer(1, 0.3*inch))

            # Page break after Display Configuration
            story.append(PageBreak())
        
        # =====================================================================
        # 6. I/O Controller Configuration
        # =====================================================================
        story.append(Paragraph(f"{self._pdf_section_number(6)}. I/O Controller Configuration", heading_style))
        io_config = config.get('io_controller', {})
        
        # Connection Settings
        story.append(Paragraph("Connection Settings", subheading_style))
        io_conn_data = [
            ['Type:', io_config.get('type', 'N/A')],
            ['Output Mode:', io_config.get('output_mode', 'N/A')],
        ]
        
        if io_config.get('type') == 'ethernet':
            conn = io_config.get('connection', {}).get('ethernet', {})
            io_conn_data.extend([
                ['IP Address:', conn.get('ip', 'N/A')],
                ['Port:', conn.get('port', 'N/A')],
                ['Timeout:', conn.get('timeout', 'N/A')],
            ])
        elif io_config.get('type') == 'serial':
            conn = io_config.get('connection', {}).get('serial', {})
            io_conn_data.extend([
                ['Port:', conn.get('port', 'N/A')],
                ['Baud Rate:', conn.get('baud_rate', 'N/A')],
                ['Data Bits:', conn.get('bytesize', 'N/A')],
                ['Parity:', conn.get('parity', 'N/A')],
                ['Stop Bits:', conn.get('stopbits', 'N/A')],
                ['Timeout:', conn.get('timeout', 'N/A')],
            ])
        
        io_conn_data.extend([
            ['Slave ID:', io_config.get('slave_id', 'N/A')],
            ['Make:', io_config.get('make', 'N/A')],
            ['Model:', io_config.get('model', 'N/A')],
            ['Status:', '✓ Validated' if io_config.get('validated') else '✗ Not Validated'],
        ])
        
        story.append(self._create_table(io_conn_data))
        story.append(Spacer(1, 0.2*inch))
        
        # Register Mappings
        story.append(Paragraph("Register Mappings", subheading_style))
        
        # Digital Inputs
        digital_inputs = io_config.get('digital_inputs', {})
        if digital_inputs:
            story.append(Paragraph("Digital Inputs", ParagraphStyle(
                'SubSubHeading',
                parent=styles['Normal'],
                fontSize=11,
                textColor=colors.HexColor('#34495e'),
                spaceAfter=6,
                spaceBefore=8
            )))
            input_mapping = digital_inputs.get('mapping', {})
            input_data = [
                ['Start Address:', digital_inputs.get('start_address', 'N/A')],
                ['Count:', digital_inputs.get('count', 'N/A')],
                ['Function Code:', digital_inputs.get('function_code', 'N/A')],
            ]
            if input_mapping:
                for key, value in input_mapping.items():
                    desc = value.get('description', key) if isinstance(value, dict) else str(value)
                    addr = value.get('address', 'N/A') if isinstance(value, dict) else 'N/A'
                    input_data.append([f"{desc}:", f"Address {addr}"])
            story.append(self._create_table(input_data))
            story.append(Spacer(1, 0.15*inch))
        
        # Digital Outputs
        digital_outputs = io_config.get('digital_outputs', {})
        if digital_outputs:
            story.append(Paragraph("Digital Outputs", ParagraphStyle(
                'SubSubHeading',
                parent=styles['Normal'],
                fontSize=11,
                textColor=colors.HexColor('#34495e'),
                spaceAfter=6,
                spaceBefore=8
            )))
            output_mapping = digital_outputs.get('mapping', {})
            output_data = [
                ['Start Address:', digital_outputs.get('start_address', 'N/A')],
                ['Count:', digital_outputs.get('count', 'N/A')],
                ['Function Code:', digital_outputs.get('function_code', 'N/A')],
            ]
            if output_mapping:
                for key, value in output_mapping.items():
                    desc = value.get('description', key) if isinstance(value, dict) else str(value)
                    addr = value.get('address', 'N/A') if isinstance(value, dict) else 'N/A'
                    output_data.append([f"{desc}:", f"Address {addr}"])
            story.append(self._create_table(output_data))
        
        story.append(Spacer(1, 0.3*inch))

        # Page break after I/O Controller Configuration
        story.append(PageBreak())
        
        # =====================================================================
        # 7. Ultrasonic Sensor Configuration
        # =====================================================================
        story.append(Paragraph(f"{self._pdf_section_number(7)}. Ultrasonic Sensor Configuration", heading_style))
        sensors_config = io_config.get('sensors', {})

        def _sensor_cfg(new_key, legacy_key):
            return sensors_config.get(new_key) or sensors_config.get(legacy_key) or {}
        
        # Entry sensor
        story.append(Paragraph("Entry sensor", subheading_style))
        sensor1 = _sensor_cfg('entry_sensor', 'sensor1')
        sensor1_data = [
            ['Make:', sensor1.get('make', 'N/A')],
            ['Model:', sensor1.get('model', 'N/A')],
            ['Pin No:', sensor1.get('pin', 'N/A')],
            ['Signal When Not Triggered:', sensor1.get('default_signal', 'N/A').upper() if sensor1.get('default_signal') else 'N/A'],
            ['Setup test:', self._format_sensor_setup_test_boolean(sensor1)],
        ]
        story.append(self._create_table(sensor1_data))
        story.append(Spacer(1, 0.2*inch))
        
        # WB sensor
        story.append(Paragraph("WB Sensor", subheading_style))
        sensor2 = _sensor_cfg('wb_sensor', 'sensor2')
        sensor2_data = [
            ['Make:', sensor2.get('make', 'N/A')],
            ['Model:', sensor2.get('model', 'N/A')],
            ['Pin No:', sensor2.get('pin', 'N/A')],
            ['Signal When Not Triggered:', sensor2.get('default_signal', 'N/A').upper() if sensor2.get('default_signal') else 'N/A'],
            ['Setup test:', self._format_sensor_setup_test(sensor2)],
            ['I/O section:', '✓ Validated' if io_config.get('validated') else '✗ Not Validated'],
        ]
        story.append(self._create_table(sensor2_data))
        story.append(Spacer(1, 0.2*inch))
        
        # Exit sensor
        story.append(Paragraph("Exit Sensor", subheading_style))
        sensor3 = _sensor_cfg('exit_sensor', 'sensor3')
        sensor3_data = [
            ['Make:', sensor3.get('make', 'N/A')],
            ['Model:', sensor3.get('model', 'N/A')],
            ['Pin No:', sensor3.get('pin', 'N/A')],
            ['Signal When Not Triggered:', sensor3.get('default_signal', 'N/A').upper() if sensor3.get('default_signal') else 'N/A'],
            ['Setup test:', self._format_sensor_setup_test_boolean(sensor3)],
        ]
        story.append(self._create_table(sensor3_data))
        story.append(Spacer(1, 0.3*inch))

        # Page break after Ultrasonic Sensor Configuration
        story.append(PageBreak())
        
        # =====================================================================
        # 8. Traffic Lights Configuration
        # =====================================================================
        story.append(Paragraph(f"{self._pdf_section_number(8)}. Traffic Lights Configuration", heading_style))
        traffic_lights_config = io_config.get('traffic_lights', {})
        tl_mode = traffic_lights_config.get('mode', 'direct')

        def _append_tl_table(light_title, pin_cfg, meta_info):
            story.append(Paragraph(light_title, subheading_style))
            tl_make = meta_info.get('make', '') if isinstance(meta_info, dict) else ''
            tl_model = meta_info.get('model', '') if isinstance(meta_info, dict) else ''
            tl_data = [
                ['Make:', tl_make or 'N/A'],
                ['Model:', tl_model or 'N/A'],
            ]
            if tl_mode == 'direct':
                tl_data.extend([
                    ['Red Pin:', pin_cfg.get('red_pin', 'N/A')],
                    ['Green Pin:', pin_cfg.get('green_pin', 'N/A')],
                ])
            else:
                pin = pin_cfg.get('pin', 'N/A')
                tl_data.extend([
                    ['Red Pin:', pin],
                    ['Green Pin:', pin],
                ])
            tl_data.append(['Setup test:', self._format_sensor_setup_test(meta_info)])
            story.append(self._create_table(tl_data))
            story.append(Spacer(1, 0.2 * inch))

        if self._is_bidirectional_layout(config):
            for dir_label, dir_key in [('ENTRY A', 'entry_a'), ('ENTRY B', 'entry_b')]:
                story.append(Paragraph(dir_label, subheading_style))
                dmeta = traffic_lights_config.get(dir_key) or {}
                direct = (traffic_lights_config.get('direct') or {}).get(dir_key) or {}
                relay = (traffic_lights_config.get('relay') or {}).get(dir_key) or {}
                for light_type in ['Entry', 'Exit']:
                    light_key = light_type.lower()
                    if tl_mode == 'direct':
                        pin_cfg = direct.get(light_key, {})
                    else:
                        pin_cfg = relay.get(light_key, {})
                    meta = dmeta.get(light_key, {}) if isinstance(dmeta, dict) else {}
                    _append_tl_table(f'{light_type} Traffic Light', pin_cfg, meta)
        else:
            entry_tl = {}
            exit_tl = {}
            if tl_mode == 'direct':
                entry_tl = traffic_lights_config.get('direct', {}).get('entry', {})
                exit_tl = traffic_lights_config.get('direct', {}).get('exit', {})
            else:
                entry_tl = traffic_lights_config.get('relay', {}).get('entry', {})
                exit_tl = traffic_lights_config.get('relay', {}).get('exit', {})
            _append_tl_table('Entry Traffic Light', entry_tl, traffic_lights_config.get('entry', {}))
            _append_tl_table('Exit Traffic Light', exit_tl, traffic_lights_config.get('exit', {}))
        story.append(Spacer(1, 0.1 * inch))

        # Page break after Traffic Lights Configuration
        story.append(PageBreak())
        
        # =====================================================================
        # 9. Boom Barrier Configuration
        # =====================================================================
        story.append(Paragraph(f"{self._pdf_section_number(9)}. Boom Barrier Configuration", heading_style))
        boom_barriers_config = io_config.get('boom_barriers', {})
        bb_mode = boom_barriers_config.get('mode', 'direct')
        
        # Entry Boom Barrier
        story.append(Paragraph("Entry Boom Barrier", subheading_style))
        entry_bb = {}
        if bb_mode == 'direct':
            entry_bb = boom_barriers_config.get('direct', {}).get('entry', {})
        else:
            entry_bb = boom_barriers_config.get('relay', {}).get('entry', {})
        
        # Get make/model from boom_barriers.entry if available
        entry_bb_info = boom_barriers_config.get('entry', {})
        if isinstance(entry_bb_info, dict):
            entry_bb_make = entry_bb_info.get('make', '')
            entry_bb_model = entry_bb_info.get('model', '')
        else:
            entry_bb_make = ''
            entry_bb_model = ''
        
        entry_bb_data = [
            ['Make:', entry_bb_make or 'N/A'],
            ['Model:', entry_bb_model or 'N/A'],
        ]
        
        if bb_mode == 'direct':
            open_pin = entry_bb.get('open_pin', 'N/A')
            close_pin = entry_bb.get('close_pin', 'N/A') or 'N/A'
            entry_bb_data.extend([
                ['Open Pin:', open_pin],
                ['Close Pin:', close_pin],
            ])
        else:
            # Relay mode - same pin for both
            pin = entry_bb.get('pin', 'N/A')
            entry_bb_data.extend([
                ['Open Pin:', pin],
                ['Close Pin:', pin],
            ])
        
        entry_bb_data.append(['Setup test:', self._format_sensor_setup_test(entry_bb_info)])
        story.append(self._create_table(entry_bb_data))
        story.append(Spacer(1, 0.2*inch))
        
        # Exit Boom Barrier
        story.append(Paragraph("Exit Boom Barrier", subheading_style))
        exit_bb = {}
        if bb_mode == 'direct':
            exit_bb = boom_barriers_config.get('direct', {}).get('exit', {})
        else:
            exit_bb = boom_barriers_config.get('relay', {}).get('exit', {})
        
        # Get make/model from boom_barriers.exit if available
        exit_bb_info = boom_barriers_config.get('exit', {})
        if isinstance(exit_bb_info, dict):
            exit_bb_make = exit_bb_info.get('make', '')
            exit_bb_model = exit_bb_info.get('model', '')
        else:
            exit_bb_make = ''
            exit_bb_model = ''
        
        exit_bb_data = [
            ['Make:', exit_bb_make or 'N/A'],
            ['Model:', exit_bb_model or 'N/A'],
        ]
        
        if bb_mode == 'direct':
            open_pin = exit_bb.get('open_pin', 'N/A')
            close_pin = exit_bb.get('close_pin', 'N/A') or 'N/A'
            exit_bb_data.extend([
                ['Open Pin:', open_pin],
                ['Close Pin:', close_pin],
            ])
        else:
            # Relay mode - same pin for both
            pin = exit_bb.get('pin', 'N/A')
            exit_bb_data.extend([
                ['Open Pin:', pin],
                ['Close Pin:', pin],
            ])
        
        exit_bb_data.append(['Setup test:', self._format_sensor_setup_test(exit_bb_info)])
        story.append(self._create_table(exit_bb_data))
        story.append(Spacer(1, 0.3*inch))

        # Page break after Boom Barrier Configuration
        story.append(PageBreak())
        
        # =====================================================================
        # 10. Digitizer Configuration
        # =====================================================================
        story.append(Paragraph(f"{self._pdf_section_number(10)}. Digitizer Configuration", heading_style))
        digitizer_config = config.get('digitizer', {})
        conversion_method = digitizer_config.get('conversion_method', 'Auto-detect (not configured)')
        conversion_methods_map = {
            'bracket': 'Method 1 - Bracketed format [000000]',
            'kg': 'Method 2 - Number + "kg" format',
            'ga': 'Method 3 - G ... A garbled format',
            'wt': 'Method 4 - "Wt:" prefix format',
            'st_gs': 'Method 5 - ST,GS format',
            'prefix': 'Method 6 - Number prefix format',
            'hyper_1bh': 'Method 7 - HyperTerminal 1BH0 frame format',
            'plain_ascii': 'Method 8 - Plain ASCII digits',
            'p_at_pct': 'Method 9 - PI / P@% HyperTerminal stream',
        }
        method_label = conversion_methods_map.get(conversion_method, conversion_method)
        
        digitizer_data = [
            ['Port:', digitizer_config.get('port', 'N/A')],
            ['Baud Rate:', digitizer_config.get('baud_rate', 'N/A')],
            ['Data Bits:', digitizer_config.get('bytesize', 'N/A')],
            ['Parity:', digitizer_config.get('parity', 'N/A')],
            ['Stop Bits:', digitizer_config.get('stopbits', 'N/A')],
            ['Timeout:', digitizer_config.get('timeout', 'N/A')],
            ['Stable Count:', digitizer_config.get('stable_count', 'N/A')],
            ['Conversion Method:', method_label],
            ['Make:', digitizer_config.get('make', 'N/A')],
            ['Model:', digitizer_config.get('model', 'N/A')],
            ['Status:', '✓ Validated' if digitizer_config.get('validated') else '✗ Not Validated'],
        ]
        story.append(self._create_table(digitizer_data))
        story.append(Spacer(1, 0.3*inch))

        # Page break after Digitizer Configuration
        story.append(PageBreak())
        
        # =====================================================================
        # 11. Audio System Configuration
        # =====================================================================
        story.append(Paragraph(f"{self._pdf_section_number(11)}. Audio System Configuration", heading_style))
        voice_config = config.get('voice', {})
        audio_config = config.get('audio', {})
        
        audio_data = [
            ['Enabled:', 'Yes' if voice_config.get('enabled', True) else 'No'],
            ['Status:', '✓ Validated' if (voice_config.get('validated') or audio_config.get('validated')) else '✗ Not Validated'],
        ]
        story.append(self._create_table(audio_data))
        story.append(Spacer(1, 0.5*inch))

        # Success message + final report info on the same page as Audio configuration
        success_style = ParagraphStyle(
            'SuccessMessage',
            parent=styles['Heading1'],
            fontSize=14,
            textColor=colors.HexColor('#27ae60'),
            spaceAfter=20,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold',
            leading=24
        )
        
        # Add vertical spacing before success message
        story.append(Spacer(1, 1.5*inch))

        # Success message with tick icon
        story.append(Paragraph("✓ The devices have been configured successfully.", success_style))
        
        story.append(Spacer(1, 0.5*inch))
        
        # Footer
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.grey,
            alignment=TA_CENTER
        )
        story.append(Paragraph(f"Report generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", footer_style))
        
        # Build PDF
        doc.build(story)
        
        if output_path:
            return output_path
        else:
            # Ensure buffer is at the beginning
            buffer.seek(0)
            # Verify buffer has content
            buffer_size = len(buffer.getvalue())
            if buffer_size == 0:
                logger.warning("PDF buffer is empty after build!")
            else:
                logger.debug(f"PDF buffer size: {buffer_size} bytes")
            buffer.seek(0)  # Reset again after getvalue()
            return buffer
