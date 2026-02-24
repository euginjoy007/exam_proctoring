import cv2
import mediapipe as mp


mp_face_mesh = mp.solutions.face_mesh
_mesh = mp_face_mesh.FaceMesh(static_image_mode=True, refine_landmarks=True, max_num_faces=1)


def estimate_gaze(image_bgr):
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    results = _mesh.process(rgb)
    if not results.multi_face_landmarks:
        return "no_face"

    landmarks = results.multi_face_landmarks[0].landmark
    left_iris = landmarks[474]
    right_iris = landmarks[469]

    avg_x = (left_iris.x + right_iris.x) / 2

    if avg_x < 0.4:
        return "left"
    if avg_x > 0.6:
        return "right"
    return "center"
