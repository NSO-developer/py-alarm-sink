SHELL=/bin/bash

# Include standard NID (NSO in Docker) package Makefile that defines all
# standard make targets
include nidpackage.mk

# The following are specific to this repositories packages
testenv-start-extra:
	@echo "Starting repository specific testenv"
# Start extra things, for example a netsim container by doing:
# docker run -td --name $(CNT_PREFIX)-my-netsim --network-alias mynetsim1 $(DOCKER_ARGS) $(IMAGE_PATH)my-ned-repo/netsim:$(DOCKER_TAG)
# Note how it becomes available under the name 'mynetsim1' from the NSO
# container, i.e. you can set the device address to 'mynetsim1' and it will
# magically work.

testenv-test:
	@echo "Make sure we're starting with 0 alarms"
	$(MAKE) testenv-runcmd CMD="request alarms purge-alarms alarm-status any"
	$(MAKE) testenv-runcmd CMD="show alarms alarm-list number-of-alarms" | awk '{ print $$4 }' | grep -w 0

	@echo "Create a single alarm and verify it's there"
	$(MAKE) testenv-runcmd CMD="request test-alarm-sink create-alarm device foo managed-object /devices/device[name='foo'] type test-alarm severity warning alarm-text test"
	$(MAKE) testenv-runcmd CMD="show alarms alarm-list number-of-alarms" | awk '{ print $$4 }' | grep -w 1
	mkdir -p tmp
	rm -f tmp/alarm-snapshot*
	$(MAKE) testenv-runcmd CMD="show alarms alarm-list" > tmp/alarm-snapshot1

	@echo "Create the same alarm and verify nothing has changed"
	$(MAKE) testenv-runcmd CMD="request test-alarm-sink create-alarm device foo managed-object /devices/device[name='foo'] type test-alarm severity warning alarm-text test"
	$(MAKE) testenv-runcmd CMD="show alarms alarm-list" > tmp/alarm-snapshot2
	diff -u tmp/alarm-snapshot1 tmp/alarm-snapshot2

	@echo "Update the alarm text and verify a a new status-change is added"
	$(MAKE) testenv-runcmd CMD="request test-alarm-sink update-alarm device foo managed-object /devices/device[name='foo'] type test-alarm severity warning alarm-text new-text"
	$(MAKE) testenv-runcmd CMD="show alarms alarm-list alarm last-alarm-text | notab" | grep new-text
	$(MAKE) testenv-runcmd CMD="show alarms alarm-list alarm | notab" | grep "[[:space:]]\+status-change" | wc -l | grep -w 2

	@echo "Clear the alarm and verify a new status-change is added and alarm is cleared"
	$(MAKE) testenv-runcmd CMD="request test-alarm-sink update-alarm device foo managed-object /devices/device[name='foo'] type test-alarm severity warning alarm-text all-clear cleared"
	$(MAKE) testenv-runcmd CMD="show alarms alarm-list alarm last-alarm-text | notab" | grep all-clear
	$(MAKE) testenv-runcmd CMD="show alarms alarm-list alarm is-cleared | notab" | grep true
	$(MAKE) testenv-runcmd CMD="show alarms alarm-list alarm | notab" | grep "[[:space:]]\+status-change" | wc -l | grep -w 3
