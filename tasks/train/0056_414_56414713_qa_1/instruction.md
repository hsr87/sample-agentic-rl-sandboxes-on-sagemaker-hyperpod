You are an intelligent data science assistant with access to a stateful jupyter notebook environment you can interact with it using tool calling. For example, you have access to the add_and_execute_jupyter_code_cell tool.

You have access to the following files:
- winequality-red.csv
All of the files are located only in the '/home/user/input' folder without any folders inside 'input'. Do not use '/kaggle/input/' folder as it does not exist.

The following packages are already installed:
pandas, numpy, matplotlib, seaborn, scipy, scikit-learn, statsmodels, tabulate, sqlite3, plotly.

You are also allowed to install additional packages if needed via `pip install ...`.

Answer the following question based on the provided files:
What is the highest upper whisker value for the 'alcohol' feature across all wine quality classes based on the outlier analysis?

Those are the guidelines for how to format your answer:
Answer must be short and concise. If a question does not have a relevant or applicable answer for the task, please respond with 'Not Applicable'.

To provide your final answer, you should call the final_answer tool using your tool calling capabilities. Do not do everything at once - break down your solution into smaller steps and code cell chunks, like data exploration, planning, data preprocessing required to answer the question and execution. Do not plot figures as they would not be visible. Look into previous conversation history and try not to get stuck on generating repetitive code.

---
**Work it out step by step.** Inspect the data first (head, shape, dtypes), write down what you observe, plan the computation, then execute it. If your agent has a notes/scratchpad tool, USE IT — jot down intermediate results, the columns you found, and the exact formula you're applying before the final calc. This is more reliable than reasoning silently across many tool calls.

**Submission protocol (READ CAREFULLY):**
1. Compute the answer in your sandbox.
2. Write **only the answer value** (no labels, no units, no trailing newline noise) to the absolute path `/workdir/answer.txt`. Examples:
   - Shell: `echo -n "<value>" > /workdir/answer.txt`
   - Python: `open("/workdir/answer.txt","w").write(str(<value>))`
3. **Do NOT use patch-style tools** (`apply_patch`, `edit`, diff patches) to write `answer.txt` — they resolve paths relative to a workspace root which may not include `/workdir/`. Always use a direct-write tool (shell redirect, file write) with the **absolute** path `/workdir/answer.txt`.
4. After the file is written, stop calling tools.

The grader does exact match, then numeric tolerance, against the gold answer. Keep the answer short and concise.