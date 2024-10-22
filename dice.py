import random
import re

import numpy as np


def dice_expand(expression: str, sub: str) -> str:
    return re.sub(
        r"(\d*)d(\d+)",
        lambda m: "("
        + str(int(m.group(1) or 1) * ("+" + (sub % m.group(2) if "%" in sub else sub)))
        + ")",
        expression,
    )


def dice_min(expression: str) -> float:
    return eval(dice_expand(expression, "1"))


def dice_max(expression: str) -> float:
    return eval(dice_expand(expression, "%s"))


def dice_avg(expression: str) -> float:
    return eval(dice_expand(expression, "(1+%s)/2"))


def dice_roll(expression: str, seed: random.Random | np.random.RandomState) -> float:
    if isinstance(seed, np.random.RandomState):
        dice = lambda x: seed.randint(1, x + 1)
    else:
        dice = lambda x: seed.randint(1, x)
    return eval(dice_expand(expression, "dice(%s)"), None, {"dice": dice})
