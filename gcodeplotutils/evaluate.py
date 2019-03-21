import re

SAFE_EVAL_RE = re.compile(r'^[-+/*()eE0-9.]+$')

def safeEval(string):
    if not SAFE_EVAL_RE.match(string):
        raise ValueError()
    return eval(string)
            
def evaluate(value, variables, formulas, MAX_DEPTH=100):
    tryAgain = True
    depth = 0
    while tryAgain and depth<MAX_DEPTH:
        tryAgain = False
        for x in formulas:
            value,n = re.subn(r'\b' + x + r'\b', '('+formulas[x]+')', value)
            if n > 0: tryAgain = True
        for x in variables:
            value,n = re.subn(r'\b' + x + r'\b', repr(variables[x]), value)
            if n > 0: tryAgain = True
        depth += 1
    if depth >= MAX_DEPTH:
        raise ValueError()
    return safeEval(value)

