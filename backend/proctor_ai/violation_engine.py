from proctor_ai.face_module import count_faces
from proctor_ai.gaze_module import estimate_gaze
from proctor_ai.phone_module import detect_phone
from proctor_ai.person_module import detect_additional_person, detect_any_person_present
from proctor_ai.suspicion_score import calculate_suspicion


def analyze_frame(image_bgr, enable_phone=True, enable_gaze=True, enable_person=False):
    violations = []

    faces = count_faces(image_bgr)
    person_present = detect_any_person_present(image_bgr)

    if faces == 0:
        if person_present:
            violations.append("gaze_away")
        else:
            violations.append("no_face")
    if faces > 1:
        violations.append("multiple_faces")

    if enable_gaze:
        gaze = estimate_gaze(image_bgr)
        if gaze in {"left", "right"}:
            violations.append(f"gaze_{gaze}")


    if enable_person and detect_additional_person(image_bgr, face_count=faces):
        violations.append("external_person_detected")

    if enable_phone and detect_phone(image_bgr):
        violations.append("phone_detected")

    score = calculate_suspicion(violations)
    return violations, score