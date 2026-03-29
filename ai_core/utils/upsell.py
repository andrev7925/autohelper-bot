import random


UPSELL_MESSAGES = [
    "hidden technical risks you might miss",
    "real maintenance costs over the next 2–3 years",
    "likelihood of expensive failures",
    "true resale difficulty in your market",
    "common problems specific to this model",
    "real negotiation strategy based on market behaviour",
    "risk of costly repairs in the near future",
]


def get_random_upsell():
    return random.choice(UPSELL_MESSAGES)
