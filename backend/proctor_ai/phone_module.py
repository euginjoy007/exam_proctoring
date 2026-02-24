from ultralytics import YOLO


_model = None


def _get_model():
    global _model
    if _model is None:
        _model = YOLO("yolov8n.pt")
    return _model


def detect_phone(image_bgr):
    model = _get_model()
    results = model.predict(image_bgr, verbose=False, imgsz=320, conf=0.2)
    for result in results:
        for box in result.boxes:
            cls_id = int(box.cls[0])
            label = result.names.get(cls_id, "")
            if label == "cell phone":
                return True
    return False
