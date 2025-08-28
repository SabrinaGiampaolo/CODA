export SOFTWARE='Celestia'
export SUBFOLDER="planner_ans"
export DEBUG_LOG=0
export SERVER_URL="http://YOUR.PLANER.ADDR:PORT/v1/chat/completions" # qwen32b for baseline and coda-1.0-32b for our planner
export EXECUTOR_URL="http://YOUR.EXECUTOR.ADDR:PORT" # uitars-1.5 addr
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

