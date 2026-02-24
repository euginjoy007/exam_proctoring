import cv2
import mediapipe as mp


mp_face_detection = mp.solutions.face_detection
_face_detector = mp_face_detection.FaceDetection(model_selection=0, min_detection_confidence=0.5)


def count_faces(image_bgr):
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    results = _face_detector.process(rgb)
    if not results.detections:
        return 0
    return len(results.detections)
