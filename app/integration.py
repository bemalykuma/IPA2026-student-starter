"""Part 4 student implementation."""
import yaml

from app.core import validate_request

from app.dispatcher import dispatch_request

from app.request_handler import validate_webex_envelope

def process_request(mentioned_people, attachment_path, bot_person_id):
    error = validate_webex_envelope(mentioned_people, attachment_path, bot_person_id)
    if error:
        return error

    try:
        with open(attachment_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

    except (yaml.YAMLError, UnicodeDecodeError):
        return {
            "status": "error",
            "result": "invalid_yaml",
        }

    request_validation = validate_request(data)
    if request_validation["result"] != "accepted":
        return request_validation

    return dispatch_request(data)
