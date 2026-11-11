# Makefile — this work dir's build: Heimdall's rules (framework/work.mk). `heimdall build` is `make all`.
ifndef HEIMDALL
$(error HEIMDALL is not set: load Heimdall's environment first (source <Heimdall>/gjallarhorn.sh))
endif
include $(HEIMDALL)/framework/work.mk
