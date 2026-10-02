"""DamDays weekly text: the farmer product.

A mentor who grew up on farms told us farmers don't open apps or emails, but a text that
comes once a week is "super handy" (mentor feedback, Fri 2 Oct 2026). So the weekly SMS is the
product, and the app is for setting up a farm and looking deeper.

This package turns the live forecasts the app already shows (app/data/real/forecasts.json)
into one text per farm. Read in this order:

    farms.py     a farm = a homestead point + a radius (default 3 km); its dams, numbered by distance
    message.py   weekly_text(): the SMS (one message, 160 characters or fewer)
                 long_text():   a longer version for the app or an email
    gsm7.py      which characters an SMS can carry, and what each one costs
    outbox.py    writes the week's texts to outbox/<date>.json
    sms.py       OPTIONAL Twilio sender: a dry run unless --send and the account's env vars are given
    examples.py  the inputs of the worked examples in MESSAGE_SPEC.md

The rules, with worked examples: notify/MESSAGE_SPEC.md. Nothing here imports or changes the
frozen model (damdays/); it only reads the forecasts the model has already published.
"""
