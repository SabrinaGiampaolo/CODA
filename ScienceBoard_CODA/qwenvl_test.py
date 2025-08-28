import sys
import os

sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
from sci import Automata, Tester, OBS
from sci import AllInOne, AIOAgent

# open-source models
qwen25_vl = lambda cls: Automata(
    model_style="openai",
    base_url=os.environ["SERVER_URL"],
    model_name=os.environ["MODEL_NAME"],
    overflow_style="openai_lmdeploy",
    hide_text=True,
    temperature=1.,
)(cls)

if __name__ == "__main__":
    AIO_NAME = "qwen25_vl"
    AIO_GROUP = AllInOne(qwen25_vl(AIOAgent))
    # register a tester and execute it
    software = os.environ.get('SOFTWARE', '')
    Tester(
        # tasks_path=f'tasks/VM/{software}',
        tasks_path=f'tasks/VM/{software}',
        # tasks_path=f'task_buffer/Software_qa/{software}',
        # tasks_path=f'tasks/VM_ANS/',
        logs_path=f"./logs/{os.environ['SUBFOLDER']}",
        community=AIO_GROUP,
        vm_path=os.environ["VM_PATH"],
        headless=True
    )()