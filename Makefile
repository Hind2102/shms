# Convenience targets. Every target is a plain command you can also run by hand (see README).
PY ?= python3
SH17 ?= $(HOME)/datasets/sh17

.PHONY: install install-ai models run test eval-prepare eval-yolo eval-vlm eval-compare audit audit-score clean

install:            ## core app + tests (no AI model, uses the mock detector)
	$(PY) -m pip install -e ".[dev]"

install-ai:         ## add YOLO (PyTorch) and plotting for evaluation
	$(PY) -m pip install -e ".[dev,yolo]" matplotlib

models:             ## download SH17 YOLO weights (checksummed)
	$(PY) scripts/download_models.py --all

run:                ## start the web app on http://127.0.0.1:8000
	$(PY) -m uvicorn shms.asgi:app --reload

test:
	$(PY) -m pytest

eval-prepare:
	$(PY) -m evaluation.prepare_sh17 --root $(SH17)

eval-yolo:
	$(PY) -m evaluation.evaluate --root $(SH17) --detector yolo --weights models/sh17_yolo8s.pt --map
	$(PY) -m evaluation.evaluate --root $(SH17) --detector yolo --weights models/sh17_yolo9e.pt --map
	$(PY) -m evaluation.evaluate --root $(SH17) --detector yolo --weights models/sh17_yolo8s.pt --subset
	$(PY) -m evaluation.evaluate --root $(SH17) --detector yolo --weights models/sh17_yolo9e.pt --subset

eval-vlm:           ## prompt v2: dev split first, then one run on the test subset; v1 kept for comparison
	$(PY) -m evaluation.evaluate --root $(SH17) --detector ollama --model qwen2.5vl:7b --prompt v2 --split dev
	$(PY) -m evaluation.evaluate --root $(SH17) --detector ollama --model qwen2.5vl:7b --prompt v2 --subset
	$(PY) -m evaluation.evaluate --root $(SH17) --detector ollama --model qwen2.5vl:7b --prompt v1 --subset

eval-compare:
	$(PY) -m evaluation.compare
	$(PY) -m evaluation.compare --only-subset

audit:
	$(PY) -m evaluation.label_audit build --root $(SH17) --n 100

audit-score:
	$(PY) -m evaluation.label_audit score

clean:
	rm -rf shms.db uploads .pytest_cache
