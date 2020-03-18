"""A Python implementation of NCS AlarmSink

The module can be used to work with alarms as defined in tailf-ncs-alarms.yang
module.

This implementation is comparable to the Java AlarmSink running in local mode
(that is, each AlarmSink instance will keep its own CDB session).

Example:
    Use the Alarm helper class in combination with AlarmId to provide data for
    all alarm fields. Then use AlarmSink to submit the alarm to NCS.

    Example:

        with AlarmSink() as alarm_sink:
            alarm_id = AlarmId(device='c0',
                               managed_object="/ncs:devices/ncs:device[ncs:name='c0']",
                               type='connection-failure', specific_problem=None)
            alarm = Alarm(alarm_id, severity=PerceivedSeverity.MINOR,
                          alarm_text='this is not a test!')
            alarm_sink.submit_alarm(alarm)

    When submitting a new alarm to NCS, NCS matches the new alarm against
    the existing Alarms in the alarm list. If the new Alarm matches an entry
    in the alarm list, that entry is simply updated with the new information
    provided. The full history of alarms submitted for the same event is kept
    and can be inspected through the NCS interfaces.

    To clear an alarm, use the `Alarm.cleared` property:

        alarm = Alarm(alarm_id, severity=PerceivedSeverity.MINOR,
              alarm_text='this is not a test!')
        alarm.cleared = True
"""

import datetime
from collections import namedtuple
from enum import Enum

import ncs


class PerceivedSeverity(Enum):
    CLEARED = 1  # internal use, do not set manually
    INDETERMINATE = 2
    MINOR = 3
    WARNING = 4
    MAJOR = 5
    CRITICAL = 6


class AlarmId(namedtuple('AlarmId', ['device', 'managed_object', 'type', 'specific_problem'])):
    """Unique identifier for an alarm list entry

    Each alarm is uniquely identified with four keys:

        - device: The managed device for which this alarm is associated with,
        plain string which identifies the device (usually the key string in
        /ncs:devices/device{dev1}). I.e. dev1
        For alarms associated with NCS, this leaf has the value 'ncs'.

        - managed_object: The managed object for which this alarm is associated
        with. Also referred to as the "Alarming Object". This may not be the
        same as the rootCause object, which is set in the rootCauseObjects
        parameter. If an NCS Service generates an alarm based on an error state
        in a device used by this service, the managed_object is the service Id
        and the object on the device the root_cause_objects.

        - type: The AlarmType this alarm is associated with. This is a YANG
        identity. Alarm types are defined by the YANG developer and should be
        designed to be as specific as possible.

        - specific_problem: If the AlarmType isn't enough to describe the Alarm,
        this field can be used in combination. Keep in mind that when
        dynamically adding a specific problem, there is no way for the operator
        to know in beforehand which alarms that can be raised on the network."""
    __slots__ = ()


class Alarm(object):
    def __init__(self, alarm_id: AlarmId,
                 severity: PerceivedSeverity, alarm_text, timestamp=None,
                 impacted_objects=None,
                 related_alarms=None, root_cause_objects=None) -> None:
        """Create a new Alarm

        :param alarm_id: AlarmId instance
        :param severity: PerceivedSeverity (= alarm state)
        :param alarm_text: additional alarm text
        :param timestamp: optional timestamp for the alarm change
        :param impacted_objects: list of ManagedObjects that may no longer
            function due to this alarm. Typically these point to NCS Services
            dependent on the objects on the device that reported the problem.
        :param related_alarms: list of other alarms (AlarmId) that have been
            generated as a consequence of this alarm, or are otherwise related
        :param root_cause_objects: ManagedObjects that are likely to be the root
            cause of this alarm.
        """
        self.device = alarm_id.device
        self.managed_object = alarm_id.managed_object
        self.type = alarm_id.type
        self.specific_problem = alarm_id.specific_problem
        self._severity = severity
        self._alarm_text = alarm_text
        self.timestamp = timestamp or datetime.datetime.now().isoformat()

        self.impacted_objects = impacted_objects
        self.related_alarms = related_alarms
        self.root_cause_objects = root_cause_objects

    @property
    def cleared(self):
        return self._severity == PerceivedSeverity.CLEARED

    @cleared.setter
    def cleared(self, value):
        if value:
            self._severity = PerceivedSeverity.CLEARED

    @property
    def severity(self):
        return self._severity

    @severity.setter
    def severity(self, value):
        if value == PerceivedSeverity.CLEARED:
            raise ValueError('Use Alarm.cleared property to clear the alarm')
        self._severity = value

    @property
    def alarm_text(self):
        return self._alarm_text

    @alarm_text.setter
    def alarm_text(self, value):
        max_length = 1024
        if len(value) > max_length:
            truncated = ' .. [truncated]'
            self._alarm_text = value[:max_length-len(truncated)] + truncated
        else:
            self._alarm_text = value

    @property
    def ncs_severity(self):
        # use the numeric value of the PerceivedSeverity enum for NCS
        return self.severity.value


class AlarmSink(object):
    """The AlarmSink is used to submit Alarm objects to NCS."""
    def __init__(self, maapi=None):
        self.maapi = maapi

    def __enter__(self):
        if self.maapi:
            raise Exception("If using context manager, don't provide a MAAPI session")

        self.maapi = ncs.maapi.Maapi()
        self.maapi.start_user_session('python-alarm-sink-write', 'system')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.maapi.close()

    def submit_alarm(self, alarm: Alarm):
        """Immediately create an alarm list entry.

        :param alarm: Alarm DTO

        If the alarm doesn't exist in the alarm list and the input Alarm has
        cleared=True, nothing is done, i.e. a new alarm with cleared=True is
        NOT created.

        If the alarm severity and text are the same, the alarm status change
        will not be submitted!"""

        with self.maapi.start_write_trans(db=ncs.OPERATIONAL) as t_write:
            root = ncs.maagic.get_root(t_write)
            alarm_list = root.al__alarms.alarm_list.alarm

            # if the inputted alarm is cleared and there is no alarm we don't
            # need to do anything
            if alarm.cleared is True and not alarm_list.exists(
                    (alarm.device, alarm.type, alarm.managed_object,
                     alarm.specific_problem or '')):
                return

            # create an entry, specific_problem may be empty string
            al = alarm_list.create(alarm.device, alarm.type,
                                   alarm.managed_object,
                                   alarm.specific_problem or '')

            # exit if nothing has changed
            # it seems last_alarm_text returns the text for when the alarm last
            # changed status. if the alarm has gone into clear, this
            # last_alarm_text doesn't reflect this but will return the text
            # previous to that, thus to prevent us from constantly updating the
            # alarm with our alarm-text for clearing, we explicitly check if
            # alarm.cleared is True or the text and perceived severity is the
            # same. This means there can not be any alarm-text updates once we
            # gone into clear (unless we go back to some other severity first,
            # which is entirely possible).
            if al.is_cleared == alarm.cleared \
               and (alarm.cleared is True or
                    (al.last_perceived_severity.value == alarm.ncs_severity and
                     al.last_alarm_text == alarm.alarm_text)):
                return

            al.is_cleared = alarm.cleared
            al.last_alarm_text = alarm.alarm_text
            if alarm.ncs_severity != PerceivedSeverity.CLEARED:
                al.last_perceived_severity = alarm.ncs_severity
            al.last_status_change = alarm.timestamp

            # TODO(mzagozen): in NSO 4.5, create entries in this leaf-list
            al.impacted_objects = alarm.impacted_objects
            al.root_cause_objects = alarm.root_cause_objects
            if alarm.related_alarms:
                for ra in alarm.related_alarms:
                    al.related_alarms.create(ra.device, ra.type, ra.managed_object, ra.specific_problem)

            sc = al.status_change.create(alarm.timestamp)

            sc.perceived_severity = alarm.ncs_severity
            sc.alarm_text = alarm.alarm_text

            t_write.apply()

    def purge_alarm(self, alarm_id: AlarmId):
        """Immediately purge an existing alarm from the alarm list

        :param alarm_id: alarm_id object"""
        with self.maapi.start_write_trans(db=ncs.OPERATIONAL) as t_write:
            root = ncs.maagic.get_root(t_write)
            alarm_list = root.al__alarms.alarm_list.alarm

            try:
                del alarm_list[alarm_id.device, alarm_id.type, alarm_id.managed_object,
                               alarm_id.specific_problem or '']
                t_write.apply()
            except KeyError:
                pass


if __name__ == '__main__':
    with AlarmSink() as alarm_sink:
        mo = "/devices/device[name='{}']".format('c0')
        test_alarm_id = AlarmId(device='c0',
                                managed_object=mo,
                                type='connection-failure', specific_problem=None)
        test_alarm = Alarm(test_alarm_id, severity=PerceivedSeverity.MINOR,
                           alarm_text='this is not a test!')
        alarm_sink.submit_alarm(test_alarm)
