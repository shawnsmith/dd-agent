
.PHONY: clean deb rpm all

clean:
	rm -rf *.deb
	rm -rf *.rpm
	make -C datadog-agent-lib clean
	make -C datadog-agent-base clean
	make -C datadog-agent clean

deb:
	make -C datadog-agent-lib deb
	cp datadog-agent-lib/*.deb .
	make -C datadog-agent-base deb
	cp datadog-agent-base/*.deb .
	make -C datadog-agent deb
	cp datadog-agent/*.deb .

rpm:
	make -C datadog-agent-lib rpm
	cp datadog-agent-lib/*.rpm .
	make -C datadog-agent-base rpm
	cp datadog-agent-base/*.rpm .
#	make -C datadog-agent rpm
#	cp datadog-agent/*.rpm .

all: clean deb rpm
