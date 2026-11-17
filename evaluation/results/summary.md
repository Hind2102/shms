# Evaluation summary (held-out SH17 split)

| Run | Images | Hazard | Precision [95% CI] | Recall [95% CI] | F1 | Positives |
|---|---:|---|---|---|---:|---:|
| ollama_qwen2.5vl_7b_subset | 300 | No hard hat | 0.952 [0.90–0.99] | 0.333 [0.27–0.39] | 0.494 | 237 |
| ollama_qwen2.5vl_7b_subset | 300 | No eye protection | 0.772 [0.68–0.86] | 0.364 [0.29–0.43] | 0.495 | 195 |
| ollama_qwen2.5vl_7b_subset | 300 | No gloves | 0.874 [0.80–0.94] | 0.319 [0.26–0.37] | 0.468 | 238 |
| ollama_qwen2.5vl_7b_subset | 300 | No hi-vis vest | 0.978 [0.95–1.00] | 0.335 [0.28–0.39] | 0.499 | 269 |
| yolo_sh17_yolo8s_subset | 300 | No hard hat | 0.974 [0.95–0.99] | 0.949 [0.92–0.97] | 0.962 | 237 |
| yolo_sh17_yolo8s_subset | 300 | No eye protection | 0.953 [0.92–0.98] | 0.938 [0.90–0.97] | 0.946 | 195 |
| yolo_sh17_yolo8s_subset | 300 | No gloves | 0.949 [0.92–0.97] | 0.937 [0.90–0.97] | 0.943 | 238 |
| yolo_sh17_yolo8s_subset | 300 | No hi-vis vest | 0.956 [0.93–0.98] | 0.959 [0.94–0.98] | 0.957 | 269 |
| yolo_sh17_yolo9e_subset | 300 | No hard hat | 0.971 [0.95–0.99] | 0.979 [0.96–1.00] | 0.975 | 237 |
| yolo_sh17_yolo9e_subset | 300 | No eye protection | 0.964 [0.94–0.99] | 0.959 [0.93–0.98] | 0.961 | 195 |
| yolo_sh17_yolo9e_subset | 300 | No gloves | 0.967 [0.94–0.99] | 0.975 [0.95–0.99] | 0.971 | 238 |
| yolo_sh17_yolo9e_subset | 300 | No hi-vis vest | 0.963 [0.94–0.99] | 0.970 [0.95–0.99] | 0.967 | 269 |

| Run | Macro F1 | Micro P | Micro R | Latency p50 (s) | Latency p95 (s) | Errors |
|---|---:|---:|---:|---:|---:|---:|
| ollama_qwen2.5vl_7b_subset | 0.489 | 0.893 | 0.337 | 4.86 | 5.75 | 0 |
| yolo_sh17_yolo8s_subset | 0.952 | 0.958 | 0.947 | 0.07 | 0.12 | 0 |
| yolo_sh17_yolo9e_subset | 0.968 | 0.966 | 0.971 | 0.09 | 0.15 | 0 |
