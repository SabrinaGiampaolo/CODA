import sys
import random
from openai import OpenAI
import io
import base64
import os
import copy
from typing import List, Tuple, Dict
from typing import Optional, Any, Self
from dataclasses import dataclass

sys.dont_write_bytecode = True
from .manager import OBS
from .log import VirtualLog
from .agent import Agent, AIOAgent
from .agent import PlannerAgent, GrounderAgent
from .prompt import TypeSort, CodeLike
from ui_tars_util import parse_action_to_structure_output, parsing_response_to_pyautogui_code
import re

@dataclass
class Community:
    def __post_init__(self):
        self.vlog = VirtualLog()

    @property
    def agents(self) -> List[Tuple[str, Agent]]:
        return [
            (key, getattr(self, key))
            for key in self.__dataclass_fields__.keys()
            if isinstance(getattr(self, key), Agent)
        ]

    def __iter__(self) -> Self:
        self.iter_pointer = 0
        return self

    def __next__(self):
        if self.iter_pointer < len(self.agents):
            self.iter_pointer += 1
            return self.agents[self.iter_pointer - 1]
        else:
            raise StopIteration

    def __call__(
        self,
        steps: Tuple[int, int],
        inst: str,
        obs: Dict[str, Any],
        code_info: tuple[set[str], Optional[List[List[int]]]],
        type_sort: TypeSort,
        timeout: int
    ) -> List[CodeLike]:
        raise NotImplementedError


@dataclass
class AllInOne(Community):
    mono: AIOAgent

    def __call__(
        self,
        steps: Tuple[int, int],
        inst: str,
        obs: Dict[str, Any],
        code_info: tuple[set[str], Optional[List[List[int]]]],
        type_sort: TypeSort,
        timeout: int
    ) -> List[CodeLike]:
        step_index, total_steps = steps
        init_kwargs = {
            "inst": inst,
            "type_sort": type_sort
        } if step_index == 0 else None

        user_content = self.mono._step(obs, init_kwargs)
        if os.getenv("TARS_DPO_NAME") == "ui-tars" or os.getenv('QWEN_VL', 0) == "1":
            tmp = user_content[0]
            del user_content[0]

        response_message = self.mono(user_content, timeout=timeout)
        assert len(response_message.content) == 1
        if "CODER_CALL" in response_message.content[0].text:
            print("CALL")
        if os.getenv('QWEN_PLANNER', '0') == '1':
            try:
                ans = response_message.content[0].text
                action = ans.split('\nAction')[1]
                if 'ANS' in action:
                    if ans.count('ANS') == 1:
                        response_message.content[0].text = ans.replace('ANS', 'ANS ANS')
                    else:
                        response_message.content[0].text = ans
                    return self.mono.code_handler(response_message.content[0], *code_info)
            except Exception as e:
                print(f'Parse Qwen Ans Action Failed: {e}')


            self.vlog.info(
                f"Planner Response {step_index + 1}/{total_steps}: \n" \
                + response_message.content[0].text
            )
            from sci.base.prompt import UI_TARS_15_PROMPT
            task = self.mono.system_message.content[0].text.split('User Instruction\n')[1]
            tars_prompt = UI_TARS_15_PROMPT.format(instruction=task, language='English')
            payload = self.mono.dump_payload(None)
            payload[0]['role'] = 'user'
            payload[0]['content'][0]['text'] = tars_prompt
            thought = payload[-1]['content'][0]['text'].split('\nAction')[0].strip('\n').strip()
            payload[-1]['content'][0]['text'] = thought + '\nAction: '

            max_try_times = 3
            try_times = 0
            while try_times < max_try_times:
                try:
                    url = os.environ["EXECUTOR_URL"].split("//")[-1].split("/v1")[0]
                    vlm = OpenAI(
                        base_url=f"http://{url}/v1",
                        api_key="empty",
                    )
                    response = vlm.chat.completions.create(
                        model="tars1.5-grounding",
                        messages=payload,
                        temperature=1.,
                    )
                    action = response.choices[0].message.content.strip()
                    response = f'{thought}\nAction: {action}'
                    self.mono.context[-1].content[0].text = response
                    response_message.content[0].text = response

                    response_content = response_message.content[0]
                    self.vlog.info(
                        f"Actor Response {step_index + 1}/{total_steps}: \n" \
                        + response_message.content[0].text
                    )

                    parsed_responses = parse_action_to_structure_output(response_content.text, factor=1000, origin_resized_height=800, origin_resized_width=1280)
                    pyautogui_code_full = ""
                    if len(parsed_responses) == 1:
                        for parsed_response in parsed_responses:
                            pyautogui_code = parsing_response_to_pyautogui_code(
                                responses=parsed_response,
                                image_height=800, image_width=1280,
                                input_swap=False
                            )
                            self.vlog.info(
                                f"Response {step_index + 1}/{total_steps}: pyautogui code\n" \
                                    + pyautogui_code
                            )
                            if "action_type" not in parsed_response:
                                pyautogui_code_full += pyautogui_code.split('\n\n')[-1].strip(';') + "; time.sleep(0.5);\n"
                            else:
                                pyautogui_code_full = pyautogui_code.split('\n\n')[-1].strip(';')
                    else:
                        for parsed_response in parsed_responses:
                            pyautogui_code = parsing_response_to_pyautogui_code(
                                responses=parsed_response,
                                image_height=800, image_width=1280,
                                input_swap=False
                            )
                            self.vlog.info(
                                f"Response {step_index + 1}/{total_steps}: pyautogui code\n" \
                                    + pyautogui_code
                            )
                            if "action_type" in parsed_response:
                                pyautogui_code_full += pyautogui_code.split('\n\n')[-1].strip(';') + "; time.sleep(0.5);\n"
                            else:
                                pyautogui_code_full = pyautogui_code.split('\n\n')[-1].strip(';')
                    response_content_clone = copy.deepcopy(response_content)
                    response_content_clone.text = "```\n" + pyautogui_code_full + "```"
                    self.vlog.info(
                        f"Response {step_index + 1}/{total_steps}: \n" \
                        + response_content_clone.text
                )
                    break
                except:
                    self.vlog.info(
                        f"Actor Response Fail {try_times}: {step_index + 1}/{total_steps}: \n" \
                        + action
                    )
                    try_times += 1
            return self.mono.code_handler(response_content_clone, *code_info)

        response_content = response_message.content[0]
        self.vlog.info(
            f"Response {step_index + 1}/{total_steps}: \n" \
                + response_content.text
        )

        if os.getenv("TARS_DPO_NAME") == "ui-tars":
            parsed_responses = parse_action_to_structure_output(response_content.text, factor=1000, origin_resized_height=800, origin_resized_width=1280)
            pyautogui_code_full = ""
            for parsed_response in parsed_responses:
                pyautogui_code = parsing_response_to_pyautogui_code(
                    responses=parsed_response,
                    image_height=800, image_width=1280,
                    input_swap=False
                )
                self.vlog.info(
                    f"Response {step_index + 1}/{total_steps}: pyautogui code\n" \
                        + pyautogui_code
                )
                if len(parsed_responses) == 1:
                    if "action_type" not in parsed_response:
                        pyautogui_code_full += pyautogui_code.split('\n\n')[-1] + "; time.sleep(0.5);\n"
                    else:
                        pyautogui_code_full = pyautogui_code.split('\n\n')[-1]
                else:
                    if "action_type" in parsed_response:
                        pyautogui_code_full += pyautogui_code.split('\n\n')[-1].strip(';') + "; time.sleep(0.5);\n"
                    else:
                        pyautogui_code_full = pyautogui_code.split('\n\n')[-1].strip(';')
            response_content_clone = copy.deepcopy(response_content)
            response_content_clone.text = "```\n" + pyautogui_code_full + "```"
            return self.mono.code_handler(response_content_clone, *code_info)

        if os.getenv('QWEN_VL', 1) == "1":
            action_str = response_content.text.split("Action:")[-1]
            action_str = action_str.strip(';')
            response_content_clone = copy.deepcopy(response_content)
            response_content_clone.text = "```\n" +  action_str + "```"
            return self.mono.code_handler(response_content_clone, *code_info)
        if os.getenv("REASONING", "0") == "1":
            response_content_clone = copy.deepcopy(response_content)
            raw_text = response_content.text
            match = re.search(r"<code>(.*?)</code>", raw_text, re.DOTALL)
            parsed_code = match.group(1).strip() if match else ""
            response_content_clone.text = "```\n" +  parsed_code + "```"
            if os.getenv("SINGLE_STEP", "0") == "1":
                print(parsed_code)
                if len(parsed_code.split('; ')) != 1:
                    new_res = []
                    for sub_code in parsed_code.split('; '):
                        response_content_clone = copy.deepcopy(response_content)
                        response_content_clone.text = "```\n" + sub_code + "```"
                        single = self.mono.code_handler(response_content_clone, *code_info)
                        new_res.append(single)
                    return new_res
            return self.mono.code_handler(response_content_clone, *code_info)

        # not reasoning and tars, original output.
        return self.mono.code_handler(response_content, *code_info)


@dataclass
class SeeAct(Community):
    planner: PlannerAgent
    grounder: GrounderAgent

    def __call__(
        self,
        steps: Tuple[int, int],
        inst: str,
        obs: Dict[str, Any],
        code_info: tuple[set[str], Optional[List[List[int]]]],
        type_sort: TypeSort,
        timeout: int
    ) -> List[CodeLike]:
        step_index, total_steps = steps
        first_step = step_index == 0

        init_kwargs = {
            "inst": inst,
            "type_sort": type_sort
        } if first_step else None

        planner_content = self.planner._step(obs, init_kwargs)
        planner_reponse_message = self.planner(planner_content, timeout=timeout)

        assert len(planner_reponse_message.content) == 1
        planner_response_content = planner_reponse_message.content[0]

        self.vlog.info(
            f"Response of planner {step_index + 1}/{total_steps}: \n" \
                + planner_response_content.text
        )

        codes = self.planner.code_handler(planner_response_content, *code_info)

        if first_step:
            self.grounder._init(obs.keys(), **init_kwargs)

        # to intercept special codes
        if codes[0].desc is False:
            return codes

        obs[OBS.schedule] = codes[0].code
        grounder_content = self.grounder._step(obs)
        grounder_response_message = self.grounder(grounder_content, timeout=timeout)

        assert len(grounder_response_message.content) == 1
        grounder_response_content = grounder_response_message.content[0]

        self.vlog.info(
            f"Response of grounder {step_index + 1}/{total_steps}: \n" \
                + grounder_response_content.text
        )
        return self.grounder.code_handler(grounder_response_content, *code_info)
