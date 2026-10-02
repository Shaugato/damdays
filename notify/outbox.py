"""The outbox: one JSON file per week holding every farm's text, ready to send.

    outbox/<date>.json      e.g. outbox/2026-10-02.json

Writing the texts to a file first (instead of sending straight away) means every text can be
read and checked before anything goes out, and there is a record of what was sent. The
optional sender (notify/sms.py) reads this file; it never makes texts of its own.

File format:
    {
      "date": "2026-10-02",               the day the texts are for
      "made_at": "2026-10-02T12:30:00Z",  when this file was written (UTC)
      "source": "...",                     which forecasts the texts come from
      "messages": [
        { "farm_id": "farm-a", "farm_name": "Farm A (near Orange)",
          "to": null,                       phone number in +61... form; null for demo farms
          "sms": "Fri 2 Oct ...",           the SMS (GSM-7, 160 places or fewer)
          "sms_characters": 141, "sms_septets": 143,
          "long": "...",                    the app or email version
          "dams": [ ... ] }                 the farm's dams (notify.farms.FarmDam.as_json)
      ]
    }
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from notify import gsm7

OUTBOX_DIR = Path(__file__).resolve().parents[1] / "outbox"


def message_record(farm, dams, sms, long, to=None):
    """One farm's entry in the outbox. Refuses a text that would not go out as one GSM-7 SMS."""
    if not gsm7.fits_one_sms(sms):
        raise ValueError(f"{farm.farm_id}: the SMS is not one GSM-7 message of {gsm7.SMS_MAX} places or fewer")
    return dict(farm_id=farm.farm_id, farm_name=farm.name, to=to, sms=sms, sms_characters=len(sms),
                sms_septets=gsm7.septets(sms), long=long, dams=[d.as_json() for d in dams])


def outbox_path(day, folder=OUTBOX_DIR):
    """outbox/<day>.json"""
    return Path(folder) / f"{day}.json"


def write_outbox(day, messages, source, folder=OUTBOX_DIR):
    """Write the week's messages to outbox/<day>.json and return its path."""
    path = outbox_path(day, folder)
    path.parent.mkdir(parents=True, exist_ok=True)
    document = dict(date=str(day), made_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    source=source, messages=messages)
    path.write_text(json.dumps(document, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def read_outbox(path):
    """The outbox document at `path`."""
    return json.loads(Path(path).read_text(encoding="utf-8"))
