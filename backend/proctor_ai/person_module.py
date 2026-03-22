from proctor_ai.phone_module import _get_model


def count_person_detections(image_bgr):
    model = _get_model()
    results = model.predict(image_bgr, verbose=False, imgsz=640, conf=0.12)

    count = 0
    for result in results:
        for box in result.boxes:
            cls_id = int(box.cls[0])
            label = result.names.get(cls_id, "")
            if label != "person":
                continue

            x1, y1, x2, y2 = [float(v) for v in box.xyxy[0].tolist()]
            area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
            frame_area = float(image_bgr.shape[0] * image_bgr.shape[1])
            if frame_area <= 0:
                continue

            # Ignore tiny false positives while keeping sensitivity for background people.
            if (area / frame_area) < 0.0015:
                continue

            count += 1
    return count


def detect_any_person_present(image_bgr):
    return count_person_detections(image_bgr) > 0


def detect_additional_person(image_bgr, face_count=0):
    person_count = count_person_detections(image_bgr)

    # A second person can be visible as body parts even when only one face is visible.
    if person_count > 1:
        return True

    # If no face is visible but person detector finds a body, treat as suspicious external presence.
    if face_count == 0 and person_count >= 1:
        return True

    return False