# CODA

This repository is the official implementation of CODA.

**[CODA: Coordinating the Cerebrum and Cerebellum for a Dual-Brain Computer Use Agent with Decoupled Reinforcement Learning](https://arxiv.org/abs/2508.20096)**
</br>
[Zeyi Sun*](https://sunzey.github.io/),
[Yuhang Cao*](https://scholar.google.com/citations?user=sJkqsqkAAAAJ/),
[Jianze Liang*](https://scholar.google.com/citations?user=P4yNnSkAAAAJ/),
[Qiushi Sun*](https://qiushisun.github.io/),
[Ziyu Liu*](https://liuziyu77.github.io/),
[Zhixiong Zhang](https://github.com/rookiexiong7/),
[Yuhang Zang](https://yuhangzang.github.io/),
[Xiaoyi Dong](https://lightdxy.github.io/),
[Kai Chen](https://chenkai.site/),
[Dahua Lin](http://dahua.site/),
[Jiaqi Wang](https://myownskyw7.github.io/)

<p align="center">
📖<a href="https://arxiv.org/abs/2508.20096">Paper</a> |
🤗<a href="https://huggingface.co/OpenIXCLab/CODA-PLANNER-TARS-32B">CODA-PLANNER-TARS-32B</a> 
</p>

## 👨‍💻 Todo
- [ ] Training code of CODA based on OpenRLHF.
- [ ] Release of JudgeModel finetuned on Qwen2.5-VL-72B.
- [x] Inference code of CODA on ScienceBoard.
- [x] Release of CODA-PLANER-TARS-32B.

## 🛠️ Usage
### Installation
```shell
conda create -n coda python=3.11 
conda activate coda
pip install vllm==0.8.5.post1
```

## Inference
Prepare [ScienceBoard](https://github.com/OS-Copilot/ScienceBoard) environment 
replace `sci` folder in ScienceBoard with our `ScienceBoard_CODA/sci` and put `qwenvl_test.py` under ScienceBoard base folder.

```shell
# use conda (vllm==0.8.5.post1) to deploy model to reproduce our results.
# deploy CODA-PLANER-TARS-32B
vllm serve OpenIXCLab/CODA-PLANNER-TARS-32B \
    --served-model-name "qwen32b" \
    --host 0.0.0.0 \
    --port "${PORT_1}" \
    --tensor-parallel-size 4 &

# deploy executor UI-TARS-1.5-7B
CUDA_VISIBLE_DEVICES=4,5 vllm serve ByteDance-Seed/UI-TARS-1.5-7B \
    --served-model-name "tars1.5-grounding" \
    --host 0.0.0.0 \
    --port "${PORT_2}" \
    --tensor-parallel-size 2 &

# in sciboard env, perform agent evaluation.
export SOFTWARE='Celestia'
export SUBFOLDER="planner_ans"
export DEBUG_LOG=0
export SERVER_URL="http://YOUR.PLANER.ADDR:PORT_1/v1/chat/completions" # qwen32b for baseline and coda-1.0-32b for our planner
export EXECUTOR_URL="http://YOUR.EXECUTOR.ADDR:PORT_2" # uitars-1.5 addr
export MODEL_NAME="qwen32b"
export NO_CONTEXT_IMAGE=0
export SPLITE=8
export QWEN_PLANNER=1
export PLANNER_ANS=1

for i in {0..7}; do # parallel for 8 VMs
    export VM_PATH="vmware_vm_data/Ubuntu${i}/Ubuntu${i}.vmx" 
    # Set port based on i value
    export INDEX=$i
    if [ $i -eq 0 ]; then
        # Process i=0: show output in terminal
        timeout 90m python qwenvl_test.py &
    else
        # Process i>0: redirect output to log file
        timeout 90m python qwenvl_test.py > "logs/vm${i}_output.log" 2>&1 &
    fi

    sleep 10s
done
wait
sleep 10s
echo "All tasks completed."

```

<!-- ## Acknowledgements
We sincerely thank [UI-TARS](https://github.com/bytedance/UI-TARS), [OSWorld](https://github.com/xlang-ai/OSWorld), [R1-V](https://github.com/Deep-Agent/R1-V), [DeepSeek](https://github.com/deepseek-ai/DeepSeek-R1), [Open-R1](https://github.com/huggingface/open-r1), [QwenVL](https://github.com/QwenLM/Qwen2.5-VL), for providing open source resources and to build the project. -->

## ✒️ Citation
```
@misc{sun2025codacoordinatingcerebrumcerebellum,
      title={CODA: Coordinating the Cerebrum and Cerebellum for a Dual-Brain Computer Use Agent with Decoupled Reinforcement Learning}, 
      author={Zeyi Sun and Yuhang Cao and Jianze Liang and Qiushi Sun and Ziyu Liu and Zhixiong Zhang and Yuhang Zang and Xiaoyi Dong and Kai Chen and Dahua Lin and Jiaqi Wang},
      year={2025},
      eprint={2508.20096},
      archivePrefix={arXiv},
      primaryClass={cs.CV},
      url={https://arxiv.org/abs/2508.20096}, 
}


@misc{sun2025seagentselfevolvingcomputeruse,
      title={SEAgent: Self-Evolving Computer Use Agent with Autonomous Learning from Experience}, 
      author={Zeyi Sun and Ziyu Liu and Yuhang Zang and Yuhang Cao and Xiaoyi Dong and Tong Wu and Dahua Lin and Jiaqi Wang},
      year={2025},
      eprint={2508.04700},
      archivePrefix={arXiv},
      primaryClass={cs.AI},
      url={https://arxiv.org/abs/2508.04700}, 
}
```

## 📄 License
![Code License](https://img.shields.io/badge/Code%20License-Apache_2.0-green.svg) ![Data License](https://img.shields.io/badge/Data%20License-CC%20By%20NC%204.0-red.svg) **Usage and License Notices**: The data and code are intended and licensed for research use only.
License: Attribution-NonCommercial 4.0 International It should abide by the policy of OpenAI: https://openai.com/policies/terms-of-use

## Acknowledgement
We sincerely thank projects <a href="https://github.com/bytedance/UI-TARS">UI-TARS</a>, <a href="https://qiushisun.github.io/ScienceBoard-Home/">ScienceBoard</a>, <a href="https://github.com/Deep-Agent/R1-V">R1-V</a>, for providing their open-source resources.