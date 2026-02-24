def calculate_suspicion(violations):
    score_map = {
        "multiple_faces": 3,
        "no_face": 2,
        "phone_detected": 3,
        "gaze_left": 1,
        "gaze_right": 1,
    }
    return sum(score_map.get(v, 1) for v in violations)
