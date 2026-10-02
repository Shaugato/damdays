"""OPTIONAL: send the week's texts through Twilio's REST API. A DRY RUN unless you say --send.

Nothing in DamDays needs this file: the texts are made and checked without it. It exists to
show that the outbox is one step from a real phone. It uses only the `requests` library.

Dry run (the default; no network, no account needed): prints exactly what would be sent.

    .venv/Scripts/python.exe -m notify.sms outbox/2026-10-02.json

Real send: only with ALL of the following. Use your own Twilio account and your own phone.

    --send                    the explicit switch; without it nothing is ever sent
    TWILIO_SID                your Twilio Account SID        (environment variables, never in a file
    TWILIO_TOKEN              your Twilio Auth Token          in this repository)
    TWILIO_FROM               the sending number (+61...) or an approved sender name

    .venv/Scripts/python.exe -m notify.sms outbox/2026-10-02.json --farm farm-a --to +61491570156 --send

The demo farms have no phone numbers ("to": null in the outbox), so a real send needs --to:
it sends ONE farm's text (--farm) to the number you give. Messages with no number are skipped.
"""
import argparse
import os
import re
import sys
from pathlib import Path

if __package__ in (None, ""):                      # let "python notify/sms.py" work as well as "-m"
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from notify import gsm7  # noqa: E402
from notify.outbox import read_outbox  # noqa: E402

TWILIO_URL = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
ENV_VARS = ("TWILIO_SID", "TWILIO_TOKEN", "TWILIO_FROM")
PHONE = re.compile(r"^\+[1-9][0-9]{7,14}$")        # E.164: "+" and up to 15 digits


def twilio_request(sid, sender, to, body):
    """The HTTP request Twilio's "create a Message" call needs (the token is added only when sending)."""
    return dict(url=TWILIO_URL.format(sid=sid), data={"From": sender, "To": to, "Body": body})


def chosen_messages(outbox, farm=None, to=None):
    """The outbox messages to send, with their destination; --to overrides the number of one --farm."""
    messages = outbox["messages"]
    if farm is not None:
        messages = [m for m in messages if m["farm_id"] == farm]
        if not messages:
            raise SystemExit(f"No message for farm {farm!r} in this outbox.")
    if to is not None and farm is None:
        raise SystemExit("--to sends to one phone, so it needs --farm (which farm's text to send).")
    return [dict(m, to=to if to is not None else m.get("to")) for m in messages]


def send_outbox(outbox, send=False, farm=None, to=None, env=None, post=None):
    """Dry-run (default) or send the outbox's texts. Returns one result per message.

    send   False: only describe each request. True: send for real, which also needs
           TWILIO_SID, TWILIO_TOKEN and TWILIO_FROM in `env` (default: os.environ).
    post   the function that makes the HTTP POST (default: requests.post); tests pass a fake.
    """
    env = os.environ if env is None else env
    messages = chosen_messages(outbox, farm, to)
    if send:
        missing = [name for name in ENV_VARS if not env.get(name)]
        if missing:
            raise SystemExit(f"Not sending: set {', '.join(missing)} (your own Twilio account) to send for real.")
        if post is None:
            import requests                          # only needed for a real send
            post = requests.post
    results = []
    for message in messages:
        body, number = message["sms"], message["to"]
        if not gsm7.fits_one_sms(body):
            results.append(dict(farm_id=message["farm_id"], to=number, status="refused: not one GSM-7 SMS"))
            continue
        if number is None or not PHONE.match(number):
            results.append(dict(farm_id=message["farm_id"], to=number, status="skipped: no valid phone number"))
            continue
        if not send:
            request = twilio_request(env.get("TWILIO_SID") or "<TWILIO_SID>",
                                     env.get("TWILIO_FROM") or "<TWILIO_FROM>", number, body)
            results.append(dict(farm_id=message["farm_id"], to=number, status="dry run", request=request))
            continue
        request = twilio_request(env["TWILIO_SID"], env["TWILIO_FROM"], number, body)
        response = post(request["url"], data=request["data"], auth=(env["TWILIO_SID"], env["TWILIO_TOKEN"]),
                        timeout=30)
        ok = 200 <= response.status_code < 300
        results.append(dict(farm_id=message["farm_id"], to=number,
                            status="sent" if ok else f"failed: HTTP {response.status_code}"))
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description="Send the week's DamDays texts with Twilio (dry run by default).")
    parser.add_argument("outbox", help="the outbox file, e.g. outbox/2026-10-02.json")
    parser.add_argument("--farm", help="only this farm's text (its farm_id)")
    parser.add_argument("--to", help="send that farm's text to this phone number (+61...) instead")
    parser.add_argument("--send", action="store_true", help="really send (needs TWILIO_SID, TWILIO_TOKEN, TWILIO_FROM)")
    args = parser.parse_args(argv)

    outbox = read_outbox(args.outbox)
    print(("SENDING" if args.send else "DRY RUN: nothing is sent") + f" ({args.outbox}, {outbox['date']})")
    for message, result in zip(chosen_messages(outbox, args.farm, args.to),
                               send_outbox(outbox, args.send, args.farm, args.to)):
        print(f"\n{message['farm_id']} ({message['farm_name']}) to {result['to']}: {result['status']}")
        print(f"  {message['sms_septets']} of {gsm7.SMS_MAX} places")
        print("  " + message["sms"].replace("\n", "\n  "))


if __name__ == "__main__":
    main()
