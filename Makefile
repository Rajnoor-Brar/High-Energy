# Makefile — this work dir's build: Heimdall's rules (framework/work.mk). `heimdall build` is `make all`.
ifndef HEP
$(error HEP is not set: load Heimdall's environment first (source <Heimdall>/gjallarhorn.sh))
endif
include $(HEP)/framework/work.mk
