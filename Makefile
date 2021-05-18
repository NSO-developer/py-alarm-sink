# You can set the default NSO_IMAGE_PATH & PKG_PATH to point to your docker
# registry so that developers don't have to manually set these variables.
# Similarly for NSO_VERSION you can set a default version. Note how the ?=
# operator only sets these variables if not already set, thus you can easily
# override them by explicitly setting them in your environment and they will be
# overridden by variables in CI.
# TODO: uncomment and fill in values for your environment
# Default variables:
#export NSO_IMAGE_PATH ?= registry.example.com:5000/my-group/nso-docker/
#export PKG_PATH ?= registry.example.com:5000/my-group/
#export NSO_VERSION ?= 5.4

# Include standard NID (NSO in Docker) package Makefile that defines all
# standard make targets
include nidpackage.mk

# The rest of this file is specific to this repository.

testenv-start-extra:
	@echo "Starting repository specific testenv"
# Start extra things, for example a netsim container by doing:
# docker run -td --name $(CNT_PREFIX)-my-netsim --network-alias mynetsim1 $(DOCKER_ARGS) $(IMAGE_PATH)my-ned-repo/netsim:$(DOCKER_TAG)
# Note how it becomes available under the name 'mynetsim1' from the NSO
# container, i.e. you can set the device address to 'mynetsim1' and it will
# magically work.

testenv-test:
	@echo "Make sure we're starting with 0 alarms"
	$(MAKE) testenv-runcmdJ CMD="request alarms purge-alarms alarm-status any"
	$(MAKE) testenv-runcmdJ CMD="show alarms alarm-list number-of-alarms" | awk '{ print $$4 }' | grep -w 0

	@echo "Create a single alarm and verify it's there"
	$(MAKE) testenv-runcmdJ CMD="request test-alarm-sink create-alarm device foo managed-object /devices/device[name='foo'] type test-alarm severity warning alarm-text test"
	$(MAKE) testenv-runcmdJ CMD="show alarms alarm-list number-of-alarms" | awk '{ print $$4 }' | grep -w 1
	mkdir -p tmp
	rm -f tmp/alarm-snapshot*
	$(MAKE) testenv-runcmdJ CMD="show alarms alarm-list" > tmp/alarm-snapshot1

	@echo "Create the same alarm and verify nothing has changed"
	$(MAKE) testenv-runcmdJ CMD="request test-alarm-sink create-alarm device foo managed-object /devices/device[name='foo'] type test-alarm severity warning alarm-text test"
	$(MAKE) testenv-runcmdJ CMD="show alarms alarm-list" > tmp/alarm-snapshot2
	diff -u tmp/alarm-snapshot1 tmp/alarm-snapshot2

	@echo "Update the alarm text and verify a a new status-change is added"
	$(MAKE) testenv-runcmdJ CMD="request test-alarm-sink update-alarm device foo managed-object /devices/device[name='foo'] type test-alarm severity warning alarm-text new-text"
	$(MAKE) testenv-runcmdJ CMD="show alarms alarm-list alarm last-alarm-text | notab" | grep new-text
	$(MAKE) testenv-runcmdJ CMD="show alarms alarm-list alarm | notab" | grep "[[:space:]]\+status-change" | wc -l | grep -w 2

	@echo "Clear the alarm and verify a new status-change is added and alarm is cleared"
	$(MAKE) testenv-runcmdJ CMD="request test-alarm-sink update-alarm device foo managed-object /devices/device[name='foo'] type test-alarm severity warning alarm-text all-clear cleared"
	$(MAKE) testenv-runcmdJ CMD="show alarms alarm-list alarm last-alarm-text | notab" | grep all-clear
	$(MAKE) testenv-runcmdJ CMD="show alarms alarm-list alarm is-cleared | notab" | grep true
	$(MAKE) testenv-runcmdJ CMD="show alarms alarm-list alarm | notab" | grep "[[:space:]]\+status-change" | wc -l | grep -w 3
	@echo "verify the cleared alarm still has the perceived severity of warning"
	$(MAKE) testenv-runcmdJ CMD="show alarms alarm-list alarm last-perceived-severity | notab" | grep warning

	@echo "Create the alarm again"
	$(MAKE) testenv-runcmdJ CMD="request test-alarm-sink create-alarm device foo managed-object /devices/device[name='foo'] type test-alarm severity warning alarm-text test"
	$(MAKE) testenv-runcmdJ CMD="show alarms alarm-list number-of-alarms" | awk '{ print $$4 }' | grep -w 1

	@echo "Clear the alarm unconditionally and verify a new status-change is added and alarm is cleared"
	$(MAKE) testenv-runcmdJ CMD="request test-alarm-sink clear-alarm device foo managed-object /devices/device[name='foo'] type test-alarm alarm-text all-clear"
	$(MAKE) testenv-runcmdJ CMD="show alarms alarm-list alarm last-alarm-text | notab" | grep all-clear
	$(MAKE) testenv-runcmdJ CMD="show alarms alarm-list alarm is-cleared | notab" | grep true
	$(MAKE) testenv-runcmdJ CMD="show alarms alarm-list alarm | notab" | grep "[[:space:]]\+status-change" | wc -l | grep -w 5
	@echo "verify the cleared alarm still has the perceived severity of warning"
	$(MAKE) testenv-runcmdJ CMD="show alarms alarm-list alarm last-perceived-severity | notab" | grep warning
