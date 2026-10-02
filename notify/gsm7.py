"""Which characters an SMS can carry, and how many of its 160 places each one takes.

A single SMS holds 160 characters only if every character is in the GSM-7 alphabet
(3GPP TS 23.038). One character outside it (an emoji, a curly quote, a long dash) switches
the whole message to UCS-2, and then a single SMS holds only 70. A few GSM-7 characters
(^ { } \\ [ ~ ] | and the euro sign) live in an "extension table" and take two places each.

DamDays texts use "~" ("~45% full"), so they are measured in places (septets), not just
characters: "Dam 1 ~45% full" is 15 characters but 16 places.
"""

# The GSM-7 basic alphabet: each character takes one place. (The escape code 0x1B is left out:
# it is not a character, it introduces the extension table.)
BASIC = ("@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
         "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà")

# The extension table: each character takes two places (an escape code, then the character).
EXTENDED = "^{}\\[~]|€\f"

SMS_MAX = 160          # places in one GSM-7 SMS

# The characters DamDays texts are built from: plain letters, digits and a little punctuation.
# All are GSM-7; only "~" takes two places. No emoji, no curly quotes, no long dashes.
SAFE = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 \n.,:;()+-/%'~")


def is_gsm7(text):
    """True if every character of `text` is in the GSM-7 alphabet (basic or extension table)."""
    return all(c in BASIC or c in EXTENDED for c in text)


def septets(text):
    """How many of the SMS's 160 places `text` takes (extension characters take two)."""
    return sum(2 if c in EXTENDED else 1 for c in text)


def fits_one_sms(text):
    """True if `text` goes out as ONE GSM-7 SMS: GSM-7 only, and 160 places or fewer."""
    return is_gsm7(text) and septets(text) <= SMS_MAX
