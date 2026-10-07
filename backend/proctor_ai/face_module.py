import cv2
import mediapipe as mp


mp_face_detection = mp.solutions.face_detection
# Short-range detector for primary face + long-range detector to catch distant/background faces.
_face_detector_near = mp_face_detection.FaceDetection(model_selection=0, min_detection_confidence=0.45)
_face_detector_far = mp_face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.35)


def _detect_count(detector, rgb_image):
    results = detector.process(rgb_image)
    if not results or not results.detections:
        return 0
    return len(results.detections)


def count_faces(image_bgr):
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)

    near_count = _detect_count(_face_detector_near, rgb)
    far_count = _detect_count(_face_detector_far, rgb)

    # Use the stronger signal while avoiding double-counting same face across detectors.
    return max(near_count, far_count)