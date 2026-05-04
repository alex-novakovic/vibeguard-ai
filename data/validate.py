from data.schemas import VisionDoc

def validate_vision_doc(vision_doc: dict) -> VisionDoc:
    return VisionDoc(**vision_doc)