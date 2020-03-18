import ncs
from ncs.application import Service

from alarm_sink import alarm_sink



class CreateAlarm(ncs.dp.Action):
    @ncs.dp.Action.action
    def cb_action(self, uinfo, name, kp, action_input, action_output):
        alarm_id = alarm_sink.AlarmId(action_input.device, action_input.managed_object, action_input.type, action_input.specific_problem)
        sev = alarm_sink.PerceivedSeverity[str(action_input.severity).upper()]
        alarm = alarm_sink.Alarm(alarm_id, severity=sev, alarm_text=action_input.alarm_text)
        try:
            alarm.cleared = action_input.cleared.exists()
        except AttributeError:
            pass
        with alarm_sink.AlarmSink() as ask:
            ask.submit_alarm(alarm)


class Main(ncs.application.Application):
    def setup(self):
        self.register_action('create-alarm', CreateAlarm)
        self.register_action('update-alarm', CreateAlarm)
