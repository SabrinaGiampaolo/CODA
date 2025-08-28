import sys
import json
import inspect
import os
sys.dont_write_bytecode = True
from .utils import TypeSort

import sys
import re
import functools
import traceback

from dataclasses import dataclass

from typing import List, Set, FrozenSet, Optional
from typing import Callable, Self, NoReturn

sys.dont_write_bytecode = True
from .. import Prompts
from .override import *
from .manager import OBS, Manager
from .model import Content, TextContent
from .utils import TypeSort, relative_py
from .log import GLOBAL_VLOG

RAW = TypeSort.Sort.Raw
VM = TypeSort.Sort.VM

QwenPlannerPrompt = """You are a GUI agent. You are given a task and your action history, with screenshots. You need to perform the next action to complete the task. 

## Output Format
```
Thought: ...
Action: ...
```

## Example:
Thought: To adjust the time scale, next action is to click the "Time" menu.
Action: click(start_box='(116,58,197,90)')

## Note
- Use {language} in `Thought` part.
- Clearly specify the target element and the action in thought.
- To enter new text, first delete the existing content or select all of it in the input box.

## User Instruction
{instruction}
"""

QwenPlannerWCodePrompt = """You are an intelligent agent that completes tasks by operating a GUI. You are given a task and your action history, with screenshots. Your primary role is to decide the next GUI action.

## Action Types

### 1. Standard GUI Actions
Used for all typical interface operations like clicking, scrolling, or typing simple, literal text.
- **Examples**:
  - `click(start_box='...')`
  - `scroll(direction='...')`
  - `type(text='some literal text', start_box='...')`

### 2. Coder Delegation Action
This is a special GUI action used to call an external Coder Agent. You use this when the task requires generating complex code, commands, or multi-line scripts.
- **Action Format**: `type(text='CODER_CALL', start_box='...')`
- **How it works**:
  - You use the literal string `CODER_CALL` as the text and add `CODER_CALL` explictly in your Thought part.
  - You MUST specify the `start_box` that corresponds to the target input field (e.g., a terminal, a search bar for complex queries, or a code editor).
  - Another system will intercept this action, call the Coder Agent to get the required code, and then type that code into the specified `start_box`.

## Output Format
```
Thought: ...
Action: ...
```

## Example:
Thought: To adjust the time scale, next action is to click the "Time" menu.
Action: click(start_box='(116,58,197,90)')

## Note
- Use {language} in `Thought` part.
- Clearly specify the target element and the action in thought.
- To enter new text, first delete the existing content or select all of it in the input box.

## User Instruction
{instruction}
"""


QwenPlannerPromptANS = """You are a GUI agent. You are given a task and your action history, with screenshots. You need to perform the next action to complete the task. 

## Output Format
```
Thought: ...
Action: ...
```

## Example:
Thought: To adjust the time scale, next action is to click the "Time" menu.
Action: click(start_box='(116,58,197,90)')

## Note
- Use {language} in `Thought` part.
- Clearly specify the target element and the action in thought.
- To enter new text, first delete the existing content or select all of it in the input box.
- When you are asked to submit an answer, if the current screenshot provides enough information to determine it, the action should be like ```ANS your_answer```. For example: ```ANS 5```.

## User Instruction
{instruction}
"""


UI_TARS_15_PROMPT = """You are a GUI agent. You are given a task and your action history, with screenshots. You need to perform the next action to complete the task. 

## Output Format
```
Thought: ...
Action: ...
```

## Action Space
click(start_box='<|box_start|>(x1,y1)<|box_end|>')
left_double(start_box='<|box_start|>(x1,y1)<|box_end|>')
right_single(start_box='<|box_start|>(x1,y1)<|box_end|>')
drag(start_box='<|box_start|>(x1,y1)<|box_end|>', end_box='<|box_start|>(x3,y3)<|box_end|>')
hotkey(key='')
type(content='') #If you want to submit your input, use "\\n" at the end of `content`.
scroll(start_box='<|box_start|>(x1,y1)<|box_end|>', direction='down or up or right or left')
wait() #Sleep for 5s and take a screenshot to check for any changes.
finished()
call_user() # Submit the task and call the user when the task is unsolvable, or when you need the user's help.

## Note
- Use {language} in `Thought` part.
- Write a small plan and finally summarize your next action (with its target element) in one sentence in `Thought` part.

## User Instruction
{instruction}
"""

QWEN_PROMPT = """
You are a GUI agent. You are given a task and your action history, with screenshots. You need to perform the next action to complete the task. 

## Output Format

Thought: ...
Action: ...

## Action Space

pyautogui.click() # Perform a left click at the current mouse cursor position.
pyautogui.doubleClick() # Perform left click twice at the current mouse cursor position.
pyautogui.click(x, y) # Performs a left click at the specified (x, y) coordinates.
pyautogui.doubleClick(x, y) # Perform left click twice twice at the specified (x, y) coordinates.
pyautogui.rightClick(x, y) # Performs a right click at the specified (x, y) coordinates.
pyautogui.write(text) # Types the given text. Ensure the target input field is focused first.
pyautogui.moveTo(x, y) # Moves the mouse cursor to the specified (x, y) coordinates.
pyautogui.dragTo(x, y) # Drags the mouse from its current position to the specified (x, y) coordinates.
pyautogui.scroll(x) # Scrolls the window. x > 0 scrolls up, x < 0 scrolls down.
pyautogui.press(key) # Presses a single keyboard key (e.g., 'enter', 'esc', 'down').
pyautogui.hotkey(key) # Presses multiple keys simultaneously (e.g., 'ctrl', 'c').
WAIT # WAIT several seconds, default 5s.
DONE # Indicates the task is successfully completed.
FAIL # Indicates the task cannot be completed.

## Note
- Use English in `Thought` part.
- Write a small plan and finally summarize your next action (with its target element) in one sentence in `Thought` part.

## User Instruction
{instruction}
"""


# DO NOT DELETE DOCSTRINGS OF EACH PRIMITIVE!
class Primitive:
    class PrimitiveGetter:
        def __get__(self, obj, obj_type=None):
            return [
                item for item in Primitive.__dict__
                if isinstance(
                    inspect.getattr_static(Primitive, item),
                    staticmethod
                ) and getattr(Primitive, item).__doc__ is not None
            ]

    WAIT_TIME = 5
    PRIMITIVES = PrimitiveGetter()

    def option_handler(method: Callable) -> Callable:
        @functools.wraps(method)
        def option_wrapper(*args, **kwargs):
            return method(*args, **kwargs)
        return option_wrapper

    class PlannedTermination(Exception):
        def __init__(self, type: staticmethod, *args) -> None:
            self.type = type
            self.args = args

    @staticmethod
    def DONE() -> NoReturn:
        """When you think the task is done, return «DONE»"""
        raise Primitive.PlannedTermination(Primitive.DONE)

    @staticmethod
    def FAIL() -> NoReturn:
        """When you think the task can not be done, return «FAIL». Don't easily say «FAIL»; try your best to do the task"""
        raise Primitive.PlannedTermination(Primitive.FAIL)

    @staticmethod
    def WAIT(time_span: Optional[str] = None) -> None:
        """When you think you have to wait for some time, return «WAIT» or «WAIT n», in which n defaults to 5(s)"""
        time_span = Primitive.WAIT_TIME if time_span is None else int(time_span)
        Manager.pause(time_span)

    @staticmethod
    @option_handler
    def ANS(*args) -> None:
        """When you are asked to submit an answer, return «ANS s» without quotation marks surrounding s, and use «FAIL» if there is no answer to the question"""
        raise Primitive.PlannedTermination(Primitive.ANS, *args)

    @staticmethod
    def TIMEOUT() -> None:
        ...


@dataclass
class CodeLike:
    code: str
    desc: bool = False
    prefix: str = ""

    @staticmethod
    def parse_tags(tags):
        tag_prefix = ""
        for index, tag in enumerate(tags):
            cord_x, cord_y, width, height = tag
            tag_prefix += "tag_" \
                + str(index + 1) \
                + "=" \
                + f"({cord_x + width // 2}, {cord_y + height // 2})"
            tag_prefix += "\n"
        return tag_prefix.strip()

    def is_primitive(self, primitives: List[str]) -> bool:
        return any([self.code.strip().startswith(prim) for prim in primitives])

    @staticmethod
    def _tag_handler(method: Callable[[Content], List[Self]]) -> Callable:
        def _tag_wrapper(
            content: Content,
            primitives: Set[str],
            tags: List[List[int]]
        ) -> List[Self]:
            for code in (codes := method(content)):
                if tags is not None and not code.is_primitive(primitives):
                    code.push_prefix(CodeLike.parse_tags(tags))
            return codes
        return _tag_wrapper

    @staticmethod
    def match(pattern: str, content: TextContent, index: int = 1) -> List[Self]:
        occurence = [
            match.group(index).strip()
            for match in re.finditer(pattern, content.text)
        ]
        return [CodeLike(code=code) for code in occurence]

    @_tag_handler
    @staticmethod
    def extract_antiquot(content: TextContent) -> List[Self]:
        return CodeLike.match(r'```(?:\w*\s+)?([\w\W]*?)```', content)

    @staticmethod
    def wrap_antiquot(doc_str: str) -> str:
        return doc_str.replace("«", "```").replace("»", "```")

    @staticmethod
    def extract_planner(
        content: TextContent,
        primitives: Set[str],
        *args,
        **kwargs
    ) -> List[Self]:
        codes = [
            code for code in CodeLike.match(
                r'```(?:\w*\s+)?([\w\W]*?)```',
                content
            ) if code.is_primitive(primitives)
        ]
        return codes if len(codes) > 0 \
            else [CodeLike(code=content.text, desc=True)]

    @staticmethod
    def wrap_planner(doc_str: str) -> str:
        return doc_str.replace("«", "```").replace("»", "```")

    @staticmethod
    def extract_atlas(content: TextContent, *args, **kwargs) -> List[Self]:
        pat_click = r'CLICK <point>\[\[(\d+), ?(\d+)\]\]</point>'
        pat_type = r'TYPE \[(.+?)\]'
        pat_scroll = r'SCROLL \[(UP|DOWN|LEFT|RIGHT)\]'
        pat_atlas = fr'({pat_click}|{pat_type}|{pat_scroll})'

        def parse(code: str) -> str:
            match_obj = None
            if (match_obj := re.match(pat_click, code)) is not None:
                x = int(match_obj[1]) / 1000
                y = int(match_obj[2]) / 1000
                return f"pyautogui.click({x}, {y})"
            elif (match_obj := re.match(pat_type, code)) is not None:
                text = json.dumps(match_obj[1])
                return f"pyautogui.typewrite({text}, interval=0.1)"
            elif (match_obj := re.match(pat_scroll, code)) is not None:
                direction = match_obj[1]
                return {
                    "UP": "pyautogui.scroll(10)",
                    "DOWN": "pyautogui.scroll(-10)",
                    "LEFT": "pyautogui.hscroll(-10)",
                    "RIGHT": "pyautogui.hscroll(10)"
                }[direction]

        return [
            CodeLike(code=parse(code.code), prefix=relative_py)
            for code in CodeLike.match(pat_atlas, content)
        ]

    @staticmethod
    def wrap_atlas(doc_str: str) -> str:
        # this function will not be called
        return doc_str

    @staticmethod
    def extract_uground(content: TextContent, *args, **kwargs) -> List[Self]:
        def parse(code: str) -> str:
            match_obj = re.match(r'\((\d+), ?(\d+)\)', code)
            x = int(match_obj[1]) / 1000
            y = int(match_obj[2]) / 1000
            return f"pyautogui.click({x}, {y})"

        return [
            CodeLike(code=parse(code.code), prefix=relative_py)
            for code in CodeLike.match(r'(\(\d+, ?\d+\))', content)
        ]

    @staticmethod
    def wrap_uground(doc_str: str) -> str:
        # this function will not be called
        return doc_str

    def push_prefix(self, prefix: str, back: bool = True) -> None:
        new_prefix = [self.prefix, prefix.strip()] if back \
            else [prefix.strip(), self.prefix]
        self.prefix = "\n\n".join(PromptFactory.filter(new_prefix))

    def __call__(
        self,
        manager: Manager,
        primitives: List[str]
    ) -> Optional[bool]:
        assert self.desc is False

        if self.is_primitive(primitives):
            splits = self.code.split(" ")
            try:
                getattr(Primitive, splits[0])(*splits[1:])
            except Primitive.PlannedTermination as early_stop:
                # pass planned exception
                raise early_stop
            except:
                # catch unexpected exception
                GLOBAL_VLOG.error(
                    f"Error calling primitive. \n" \
                        + traceback.format_exc()
                )
        else:
            return manager("\n\n".join(PromptFactory.filter([
                "" if self.prefix is None else self.prefix.strip(),
                self.code
            ])))


class PromptFactory:
    def __init__(self, code_style: str) -> None:
        assert hasattr(CodeLike, func_name:=f"wrap_{code_style}")
        self.code_style = code_style
        self.code_handler: Callable[[str], str] = getattr(CodeLike, func_name)

    @staticmethod
    def option(item: Optional[str]) -> List[str]:
        # usage: [..., *PromptFactory.option("..."), ...]
        return PromptFactory.filter([item])

    @staticmethod
    def filter(inputs: List[str]) -> List[str]:
        return [
            item for item in inputs
            if isinstance(item, str) and len(item) > 0
        ]


class AIOPromptFactory(PromptFactory):
    # first section: _intro
    GENERAL_INTRO = "You are an agent which follow my instruction and perform desktop computer tasks as instructed."
    APP_GENERAL = "an application available on Ubuntu"
    APP_INCENTIVE = {
        RAW: lambda type, intro: f"You have good knowledge of {type}, {intro}; and assume that your code will run directly in the CLI/REPL of {type}.",
        VM: lambda type, intro: f"You have good knowledge of {type}, {intro}; and assume your code will run on a computer controlling the mouse and keyboard."
    }
    OBS_INCENTIVE = lambda obs_descr: f"For each step, you will get an observation of the desktop by {obs_descr}, and you will predict actions of next steps based on that."

    # second section: _command = _general_command + _general_usage + _special_command
    # second #1: _general_command
    RETURN_OVERVIEW_RAW = staticmethod(lambda type, media: f"You are required to use {media} to perform the action grounded to the observation. DO NOT use the bash commands or and other codes that {type} itself does not support.")
    RETURN_OVERVIEW_VM = {
        "antiquot": "You are required to use `pyautogui` to perform the action grounded to the observation, but DO NOT use the `pyautogui.locateCenterOnScreen` function to locate the element you want to operate with since we have no image of the element you want to operate with. DO NOT USE `pyautogui.screenshot()` to make screenshot."
    }
    RETURN_REGULATION = {
        "antiquot": "You ONLY need to return the code inside a code block, like this:\n```\n# your code here\n```"
    }
    RETURN_SUPPLEMENT_RAW = "Return exact one line of commands to perform the action in each code block."
    RETURN_SUPPLEMENT_VM = {
        "antiquot": "Return one line or multiple lines of python code to perform the action each time, and be time efficient. When predicting multiple lines of code, make some small sleep like `time.sleep(0.5);` interval so that the machine could take breaks. Each time you need to predict a complete code, and no variables or function can be shared from history."
    }

    # second #1.5: supplementary instruction for set of marks
    SOM_SUPPLEMENT = [
        "You can replace x, y in the code with the tag of elements you want to operate with, such as:",
        "«\npyautogui.moveTo(tag_3)\npyautogui.click(tag_2)\npyautogui.dragTo(tag_1, button='left')\n»",
        "When you think you can directly output precise x and y coordinates or there is no tag on which you want to interact, you can also use them directly; but you should be careful to ensure the correct of coordinates."
    ]

    # second #3: _general_command
    SPECIAL_OVERVIEW = "Specially, it is also allowed to return the following special code:"

    # third section: _warning
    VM_GENERAL = f"My computer's password is '{Prompts.VM_PASSWORD}', feel free to use it when you need sudo rights."

    # fourth section: _ending
    ENDING_ULTIMATUM = "First give the current observation and previous things we did a short reflection, then RETURN ME THE CODE OR SPECIAL CODE I ASKED FOR. NEVER EVER RETURN ME ANYTHING ELSE."
    SYSTEM_INSTRUCTION = lambda inst: f"You are asked to complete the following task: {inst}"

    def getattr(self, type_sort: TypeSort, name: str, default: Any) -> Any:
        assert type(default) == type(results := getattr(
            Prompts,
            str(type_sort).upper() + "_" + name,
            getattr(
                Prompts,
                type_sort.type.upper() + "_" + name,
                default
            )
        ))
        return results

    def _unfold(self, obs: FrozenSet[str]) -> str:
        get_descr = lambda obs_name: getattr(Manager, obs_name).__doc__
        obs = list(obs)

        if len(obs) == 1:
            return get_descr(obs[0])
        else:
            return "; ".join([
                f"{index + 1}) {get_descr(item)}"
                for index, item in enumerate(obs[:-1])
            ]) + f"; and {len(obs)}) " + get_descr(obs[-1])

    def _intro(self, obs: FrozenSet[str], type_sort: TypeSort) -> str:
        brief_intro = self.getattr(type_sort, "IS", self.APP_GENERAL)
        return "\n".join([
            self.GENERAL_INTRO,
            self.APP_INCENTIVE[type_sort.sort](type_sort.type, brief_intro),
            self.OBS_INCENTIVE.__func__(self._unfold(obs))
        ])

    def _general_command(self, obs: FrozenSet[str], type_sort: TypeSort) -> str:
        media = self.getattr(type_sort, "NEED", type_sort.type + " commands")
        set_of_marks = self.SOM_SUPPLEMENT if OBS.set_of_marks in obs else []

        return_overview = self.RETURN_OVERVIEW_RAW(type_sort.type, media) \
            if type_sort.sort == RAW \
            else self.RETURN_OVERVIEW_VM[self.code_style]
        return_regulation = self.RETURN_REGULATION[self.code_style]
        return_supplement = self.RETURN_SUPPLEMENT_RAW \
            if type_sort.sort == RAW \
            else self.RETURN_SUPPLEMENT_VM[self.code_style]

        return "\n\n".join(PromptFactory.filter([
            "\n".join(PromptFactory.filter([
                return_overview,
                return_regulation,
                return_supplement,
            ])),
            "\n".join([self.code_handler(item) for item in set_of_marks]),
        ]))

    def _general_usage(self, type_sort: TypeSort) -> str:
        return "\n".join(self.getattr(type_sort, "USAGE", []))

    def _special_command(self) -> str:
        docs = [
            self.code_handler(getattr(Primitive, item).__doc__)
            for item in Primitive.PRIMITIVES
        ]

        return "\n".join([self.SPECIAL_OVERVIEW, *[
            item + ("." if index + 1 == len(docs) else ";")
            for index, item in enumerate(docs)
        ]])

    def _command(self, obs: FrozenSet[str], type_sort: TypeSort) -> str:
        return "\n\n".join(PromptFactory.filter([
            self._general_command(obs, type_sort),
            self._general_usage(type_sort),
            self._special_command()
        ]))

    def _warning(self, type_sort: TypeSort) -> str:
        vm_tip = self.VM_GENERAL if type_sort == TypeSort.VM else None
        extra_tips = self.getattr(type_sort, "TIPS", [])

        return "\n".join([
            *PromptFactory.option(vm_tip),
            *extra_tips
        ])

    def _ending(self) -> Callable[[str], str]:
        NEW_ENDING_ULTIMATUM = self.ENDING_ULTIMATUM
        if os.getenv("NO_SLEEP", "0") == "1":
            NEW_ENDING_ULTIMATUM += " DO NOT output code pyautogui.sleep() or time.sleep() in your code."
        if os.getenv("SINGLE_CODE", "0") == "1":
            NEW_ENDING_ULTIMATUM += " output only a single pyautogui code at a time."
        if os.getenv("EXAMPLE_7B", "0") == "1":
            NEW_ENDING_ULTIMATUM += '''
You are only allowed to output pyautogui codes and the special command defined above, here are 4 exampler output:
```\npyautogui.click(x, y); time.sleep(0.5);\n```
```\npyautogui.click(x, y); time.sleep(0.5); pyautogui.write('hbonds radius 0.1'); time.sleep(0.5); pyautogui.press('enter');\n```
```\npyautogui.click(x, y); time.sleep(0.5);\npyautogui.typewrite('angle /A GLN4 OE1, OXT GLN3 OE1'); time.sleep(0.5);\npyautogui.press('enter'); time.sleep(0.5);\n```
```\nDONE\n```
'''
        if os.getenv("REASONING", "0") == "1":
             return lambda inst: "\n".join([
                NEW_ENDING_ULTIMATUM.replace(' NEVER EVER RETURN ME ANYTHING ELSE.', '\n\nOutput your action and resoning process in the following fomart strictly:\n<think>reasoning process of why choose this action and code</think><code>PYGUI CODE</code>\n'),
                self.SYSTEM_INSTRUCTION.__func__(inst)
            ])
        else:
            return lambda inst: "\n".join([
                NEW_ENDING_ULTIMATUM,
                self.SYSTEM_INSTRUCTION.__func__(inst)
            ])

    def __call__(
        self,
        obs: FrozenSet[str],
        type_sort: TypeSort
    ) -> Callable[[str], str]:
        if os.getenv("QWEN_PLANNER", '0') == "1":
            if os.getenv("PLANNER_ANS", '0') == '1':
                out = lambda inst: "\n\n".join(PromptFactory.filter([
                    QwenPlannerPromptANS.format(language='English', instruction=inst)
                ]))
            elif os.getenv("QwenPlannerWCodePrompt", '0') == '1':
                out = lambda inst: "\n\n".join(PromptFactory.filter([
                    QwenPlannerWCodePrompt.format(language='English', instruction=inst)
                ]))
            else:
                out = lambda inst: "\n\n".join(PromptFactory.filter([
                    QwenPlannerPrompt.format(language='English', instruction=inst)
                ]))
            return out

        elif os.getenv("TARS_DPO_NAME") == "ui-tars":
            out = lambda inst: "\n\n".join(PromptFactory.filter([
                UI_TARS_15_PROMPT.format(instruction=inst, language="English")
            ]))
            return out
        elif os.getenv("QWEN_VL", "0") == "1":
            out = lambda inst: "\n\n".join(PromptFactory.filter([
                QWEN_PROMPT.format(instruction=inst)
            ]))
            return out
        else:
            out = lambda inst: "\n\n".join(PromptFactory.filter([
                self._intro(obs, type_sort),
                self._command(obs, type_sort),
                self._warning(type_sort),
                self._ending()(inst)
            ]))
            return out

class PlannerPromptFactory(AIOPromptFactory):
    # first section: _intro
    GENERAL_INTRO = "You are an agent which follow my instruction and schedule desktop computer tasks as instructed."
    APP_INCENTIVE = {VM: lambda type, intro: f"You have good knowledge of {type}, {intro}."}

    # second section: _command
    RETURN_OVERVIEW = "You are required to make ONE step of the plan in natural language, and then it will be parsed into `pyautogui` codes by another grounding agent."
    SPECIAL_OVERVIEW = "Sometimes you should return special codes directly as followings, at which your plan will not be passed to the grounder model."

    # fourth section: _ending
    ENDING_ULTIMATUM = "First give the current observation and previous things we did a short reflection, then RETURN ME YOUR PLANNING OR SPECIAL CODE I ASKED FOR. NEVER EVER RETURN ME ANYTHING ELSE."

    def _command(self, obs: FrozenSet[str], type_sort: TypeSort) -> str:
        return "\n".join(PromptFactory.filter([
            self.RETURN_OVERVIEW,
            self._special_command()
        ]))

    def _warning(self, type_sort: TypeSort) -> str:
        return "\n".join(self.getattr(type_sort, "TIPS", []))


class GrounderPromptFactory(AIOPromptFactory):
    # first section: _intro
    OBS_INCENTIVE = lambda obs_descr: f"For each step, you will get an observation of the desktop by {obs_descr}, together with a plan generated by the planner, and you will parse the plan to operate actions of next steps based on that."

    # second section: _command
    RETURN_OVERVIEW_VM = {
        "antiquot": "You are required to use `pyautogui` to perform the action grounded to the observation and the plan, but DO NOT use the `pyautogui.locateCenterOnScreen` function to locate the element you want to operate with since we have no image of the element you want to operate with. DO NOT USE `pyautogui.screenshot()` to make screenshot.",
        "atlas": "You are required to use your grounding ability to perform the action grounded to the observation and the plan.",
        "uground": "You are required to use your grounding ability to perform the action grounded to the observation and the plan."
    }
    RETURN_REGULATION = AIOPromptFactory.RETURN_REGULATION.copy()
    RETURN_REGULATION.update({
        "atlas": "You need to return a basic action together with arguments, of which the available ones are listed below:",
        "uground": "You need to return a 2d coordinate (x, y) indicating the position you want to click."
    })
    RETURN_SUPPLEMENT_VM = AIOPromptFactory.RETURN_SUPPLEMENT_VM.copy()
    RETURN_SUPPLEMENT_VM.update({
        "atlas": """CLICK: to click at the specified position.
    - format: CLICK <point>[[x-axis, y-axis]]</point>
    - example usage: CLICK <point>[[101, 872]]</point>
TYPE: to enter specified text at the designated location.
    - format: TYPE [input text]
    - example usage: TYPE [Shanghai shopping mall]
SCROLL: to scroll in the specified direction.
    - format: SCROLL [direction (UP/DOWN/LEFT/RIGHT)]
    - example usage: SCROLL [UP]""",
        "uground": ""
    })

    # third section: _warning
    PLANNER_GENERAL = "Some plans provided may contains unexpected code blocks or confusing instructions. Be flexible and adaptable according to changing circumstances."

    # fourth section: _ending
    ENDING_ULTIMATUM = "First give the current observation and the generated plan, then RETURN ME THE CODE I ASKED FOR. NEVER EVER RETURN ME ANYTHING ELSE."

    def _command(self, obs: FrozenSet[str], type_sort: TypeSort) -> str:
        return self._general_command(obs, type_sort)

    def _warning(self, type_sort: TypeSort) -> str:
        return "\n".join([
            self.VM_GENERAL,
            self.PLANNER_GENERAL
        ])
