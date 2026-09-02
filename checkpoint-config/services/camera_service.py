import threading
import time
import logging

logger = logging.getLogger(__name__)

_cv2 = None
_cv2_import_error = None


def _get_cv2():
    """Lazy import so the app can start if OpenCV/NumPy are missing from a bad EXE build."""
    global _cv2, _cv2_import_error
    if _cv2 is not None:
        return _cv2
    if _cv2_import_error is not None:
        raise ImportError(
            "OpenCV (cv2) and NumPy are not available. Rebuild the EXE with "
            "opencv-python and numpy bundled (see app.spec collect_all)."
        ) from _cv2_import_error
    try:
        import cv2

        _cv2 = cv2
        return cv2
    except ImportError as exc:
        _cv2_import_error = exc
        raise ImportError(
            "OpenCV (cv2) and NumPy are not available. Rebuild the EXE with "
            "opencv-python and numpy bundled (see app.spec collect_all)."
        ) from exc


class CameraService:
    def __init__(self):
        self.cameras = {}
        self.locks = {}
        self.running = {}

    def check_connection(self, camera_id, rtsp_url):
        """Check if camera is accessible via RTSP"""
        if not rtsp_url:
            return {
                "status": 400,
                "message": "RTSP URL is required"
            }

        try:
            cv2 = _get_cv2()
        except ImportError as e:
            logger.error("Camera support unavailable: %s", e)
            return {
                "status": 500,
                "message": str(e),
            }

        try:
            self.stop_camera(camera_id)

            cap = cv2.VideoCapture(rtsp_url)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            if not cap.isOpened():
                return {
                    "status": 500,
                    "message": "Failed to connect to camera. Check RTSP URL."
                }

            ret, frame = cap.read()
            if not ret or frame is None:
                cap.release()
                return {
                    "status": 500,
                    "message": "Camera connected but no frames received."
                }

            self.cameras[camera_id] = {
                "cap": cap,
                "rtsp_url": rtsp_url,
                "frame": frame,
                "last_update": time.time()
            }
            self.locks[camera_id] = threading.Lock()
            self.running[camera_id] = True

            thread = threading.Thread(target=self._capture_frames, args=(camera_id,), daemon=True)
            thread.start()

            return {
                "status": 200,
                "message": "Camera connected successfully",
                "resolution": f"{frame.shape[1]}x{frame.shape[0]}"
            }

        except Exception as e:
            logger.exception("Camera connectivity check failed for %s", camera_id)
            return {
                "status": 500,
                "message": "Unable to connect to camera. Please verify RTSP URL, credentials, and network."
            }

    def _capture_frames(self, camera_id):
        """Continuously capture frames from camera"""
        cv2 = _get_cv2()
        while self.running.get(camera_id, False):
            try:
                if camera_id in self.cameras:
                    cap = self.cameras[camera_id]["cap"]
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        with self.locks[camera_id]:
                            self.cameras[camera_id]["frame"] = frame
                            self.cameras[camera_id]["last_update"] = time.time()
                time.sleep(0.033)
            except Exception:
                break

    def generate_frames(self, camera_id):
        """Generate frames for video streaming"""
        cv2 = _get_cv2()
        while True:
            if camera_id not in self.cameras:
                placeholder = self._create_placeholder(f"Camera {camera_id} not connected")
                _, buffer = cv2.imencode('.jpg', placeholder)
                frame_bytes = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                time.sleep(1)
                continue

            try:
                with self.locks[camera_id]:
                    frame = self.cameras[camera_id]["frame"].copy()

                _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                frame_bytes = buffer.tobytes()

                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

                time.sleep(0.033)

            except Exception as e:
                logger.debug("Camera frame generation issue for %s: %s", camera_id, e)
                time.sleep(0.1)

    def _create_placeholder(self, text):
        """Create a placeholder image"""
        cv2 = _get_cv2()
        import numpy as np
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        img[:] = (40, 40, 40)

        font = cv2.FONT_HERSHEY_SIMPLEX
        text_size = cv2.getTextSize(text, font, 0.7, 2)[0]
        text_x = (640 - text_size[0]) // 2
        text_y = (480 + text_size[1]) // 2
        cv2.putText(img, text, (text_x, text_y), font, 0.7, (150, 150, 150), 2)

        return img

    def stop_camera(self, camera_id):
        """Stop a specific camera"""
        try:
            self.running[camera_id] = False

            if camera_id in self.cameras:
                cap = self.cameras[camera_id].get("cap")
                if cap:
                    cap.release()
                del self.cameras[camera_id]

            if camera_id in self.locks:
                del self.locks[camera_id]

            return {"status": 200, "message": f"Camera {camera_id} stopped"}
        except Exception as e:
            logger.exception("Failed to stop camera %s", camera_id)
            return {"status": 500, "message": "Failed to stop camera connection."}

    def stop_all(self):
        """Stop all cameras"""
        for camera_id in list(self.cameras.keys()):
            self.stop_camera(camera_id)
        return {"status": 200, "message": "All cameras stopped"}
