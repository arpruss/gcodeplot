#Custom argparse classes for additional function. Allows stripping '#' comments
#from files passed in, and also allows 'arg=value' format instead of 'arg value'
#
#Also allows negatable arguments; --arg=124 --arg=true --arg=false --no-arg


import argparse
from pathlib import Path
from .enums import *

class cArgumentParser(argparse.ArgumentParser):
    def convert_arg_line_to_args(self, arg_line):
        
        if arg_line.startswith("#"):
            return []
        elif "=" in arg_line:
            # Treat lines with "=" as if they were passed as command-line arguments
            key, value = arg_line.split("=", 1)
            return ['--' + key.strip(), value.strip()]
        elif arg_line.startswith('no-'):
            return ['--' + arg_line.strip()]
        else:
            return arg_line.split()


class CustomBooleanAction(argparse.Action):
    def __init__(self,option_strings,
                 dest,
                 default=None,
                 required=False,
                 help=None,
                 metavar=None):

        _option_strings = []
        for option_string in option_strings:
            _option_strings.append(option_string)

            if option_string.startswith('--'):
                option_string = '--no-' + option_string[2:]
                _option_strings.append(option_string)

        if help is not None and default is not None:
            help += f" (default: {default})"

        super().__init__(
            option_strings=_option_strings,
            dest=dest,
            nargs='?',
            const=None,
            default=default,
            required=required,
            help=help,
            metavar=metavar)

    def __call__(self, parser, namespace, values, option_string=None):
        if option_string and option_string.startswith('--no-'):
            # Handle the case where the option is negated, e.g., --no-shading-crosshatch
            setattr(namespace, self.dest, False)
        elif values is None or values.lower() == 'true':
            # Handle the cases where the option is provided without a value or explicitly set to 'true'
            setattr(namespace, self.dest, True)
        elif values.lower() == 'false':
            # Handle the case where the option is explicitly set to 'false'
            setattr(namespace, self.dest, False)
        else:
            # assign the target value to the provided input. e.g, --send=21523
            setattr(namespace, self.dest, values)

class PrintDefaultsAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        printed = set()
        formatted_strings = [
            self.format_argument(action, namespace)
            for action in parser._actions 
            if not isinstance(action, argparse._HelpAction) 
            and action.help != argparse.SUPPRESS 
            and (formatted := f'{action.dest}: {action.default}') not in printed and not printed.add(formatted)
        ]
        print('\n'.join(formatted_strings))
        # parser.exit()

    def format_argument(self, action, namespace):

        if action.dest in ('scale', 'align_x', 'align_y'):
            value = parse_alignment(getattr(namespace, action.dest, action.default), reverse=True)    
        elif action.dest == 'extract_color' and (value := getattr(namespace, action.dest, action.default) ) == None:
            value = 'all'
        else:
            value = getattr(namespace, action.dest, action.default)
        return f'{action.dest + ":":<25}{value}'
    

def parse_alignment(arg, enumMode=False, reverse=False):
    verbose_mapping = {'none': 'n', 'left': 'l', 'right': 'r', 'center': 'c', 'bottom': 'b', 'top': 't', 'down': 'd', 'fit': 'f'}
    enum_mapping = {'n': ALIGN_SCALE_NONE, 'l': ALIGN_LEFT, 'r': ALIGN_RIGHT, 'c': ALIGN_CENTER, 'b': ALIGN_BOTTOM, 't': ALIGN_TOP, 'd': SCALE_DOWN_ONLY, 'f': SCALE_FIT}
    if enumMode: return enum_mapping.get(arg, ALIGN_SCALE_NONE)  
    if reverse: return next((key for key, value in verbose_mapping.items() if value == arg), None)
    return verbose_mapping.get(arg.lower(), 'n') if len(arg) > 1 else arg

def none_or_str(value):
        return None if value=='none' else value
    
    

class PenAction(argparse.Action):
    def __init__(self, PenClass, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.Pen = PenClass
    def __call__(self, parser, namespace, values, option_string=None):
        pens = {}
        pen_file = Path(values)
        if pen_file.is_file():
            pens = {p.pen: p for line in open(pen_file) if (line_stripped := line.strip()) and (p := self.Pen(line_stripped))}
        else:
            parser.error(f'Invalid filename provided in {self.dest} \n')
        setattr(namespace, self.dest, pens)