# XyloBot convenience targets — thin aliases over the `xylobot` CLI.
# Prefer the CLI directly for options; these cover the common flow.
.PHONY: help setup doctor ports can-up calibrate teleop record replay train eval lint

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup:  ## Create venv + install toolkit + LeRobot
	./setup.sh

doctor:  ## Check the environment is ready
	xb doctor

ports:  ## Discover USB ports for the arms
	xb find-ports

can-up:  ## Bring up the SocketCAN interface (RS follower)
	xb can-up

calibrate:  ## Calibrate follower + leader
	xb calibrate all

teleop:  ## Drive follower with the leader
	xb teleop

record:  ## Record demonstrations
	xb record

replay:  ## Replay episode 0 (override: make replay EP=3)
	xb replay --episode $(or $(EP),0)

train:  ## Train the policy
	xb train

eval:  ## Run a trained policy (make eval P=outputs/train/act_xylobot/checkpoints/last/pretrained_model)
	xb eval --policy-path $(P)

lint:  ## Lint the toolkit
	ruff check stampbot
