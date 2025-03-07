﻿# This Python file uses the following encoding: utf-8
# -*- coding: utf-8 -*-
from cereal import log, car

from common.realtime import DT_CTRL
from selfdrive.config import Conversions as CV
from selfdrive.locationd.calibration_helpers import Filter

AlertSize = log.ControlsState.AlertSize
AlertStatus = log.ControlsState.AlertStatus
VisualAlert = car.CarControl.HUDControl.VisualAlert
AudibleAlert = car.CarControl.HUDControl.AudibleAlert
EventName = car.CarEvent.EventName

# Alert priorities
class Priority:
  LOWEST = 0
  LOWER = 1
  LOW = 2
  MID = 3
  HIGH = 4
  HIGHEST = 5

# Event types
class ET:
  ENABLE = 'enable'
  PRE_ENABLE = 'preEnable'
  NO_ENTRY = 'noEntry'
  WARNING = 'warning'
  USER_DISABLE = 'userDisable'
  SOFT_DISABLE = 'softDisable'
  IMMEDIATE_DISABLE = 'immediateDisable'
  PERMANENT = 'permanent'

# get event name from enum
EVENT_NAME = {v: k for k, v in EventName.schema.enumerants.items()}

class Events:
  def __init__(self):
    self.events = []
    self.static_events = []
    self.events_prev = dict.fromkeys(EVENTS.keys(), 0)

  @property
  def names(self):
    return self.events

  def __len__(self):
    return len(self.events)

  def add(self, event_name, static=False):
    if static:
      self.static_events.append(event_name)
    self.events.append(event_name)

  def clear(self):
    self.events_prev = {k: (v+1 if k in self.events else 0) for k, v in self.events_prev.items()}
    self.events = self.static_events.copy()

  def any(self, event_type):
    for e in self.events:
      if event_type in EVENTS.get(e, {}).keys():
        return True
    return False

  def create_alerts(self, event_types, callback_args=None):
    if callback_args is None:
      callback_args = []

    ret = []
    for e in self.events:
      types = EVENTS[e].keys()
      for et in event_types:
        if et in types:
          alert = EVENTS[e][et]
          if not isinstance(alert, Alert):
            alert = alert(*callback_args)

          if DT_CTRL * (self.events_prev[e] + 1) >= alert.creation_delay:
            alert.alert_type = f"{EVENT_NAME[e]}/{et}"
            ret.append(alert)
    return ret

  def add_from_msg(self, events):
    for e in events:
      self.events.append(e.name.raw)

  def to_msg(self):
    ret = []
    for event_name in self.events:
      event = car.CarEvent.new_message()
      event.name = event_name
      for event_type in EVENTS.get(event_name, {}).keys():
        setattr(event, event_type , True)
      ret.append(event)
    return ret

class Alert:
  def __init__(self,
               alert_text_1,
               alert_text_2,
               alert_status,
               alert_size,
               alert_priority,
               visual_alert,
               audible_alert,
               duration_sound,
               duration_hud_alert,
               duration_text,
               alert_rate=0.,
               creation_delay=0.):

    self.alert_type = ""
    self.alert_text_1 = alert_text_1
    self.alert_text_2 = alert_text_2
    self.alert_status = alert_status
    self.alert_size = alert_size
    self.alert_priority = alert_priority
    self.visual_alert = visual_alert
    self.audible_alert = audible_alert

    self.duration_sound = duration_sound
    self.duration_hud_alert = duration_hud_alert
    self.duration_text = duration_text

    self.start_time = 0.
    self.alert_rate = alert_rate
    self.creation_delay = creation_delay

    # typecheck that enums are valid on startup
    tst = car.CarControl.new_message()
    tst.hudControl.visualAlert = self.visual_alert

  def __str__(self):
    return self.alert_text_1 + "/" + self.alert_text_2 + " " + str(self.alert_priority) + "  " + str(
      self.visual_alert) + " " + str(self.audible_alert)

  def __gt__(self, alert2):
    return self.alert_priority > alert2.alert_priority

class NoEntryAlert(Alert):
  def __init__(self, alert_text_2, audible_alert=AudibleAlert.chimeError,
               visual_alert=VisualAlert.none, duration_hud_alert=2.):
    super().__init__("오픈파일럿 사용불가", alert_text_2, AlertStatus.normal,
                     AlertSize.mid, Priority.LOW, visual_alert,
                     audible_alert, .4, duration_hud_alert, 3.)


class SoftDisableAlert(Alert):
  def __init__(self, alert_text_2):
    super().__init__("핸들을 잡아주세요", alert_text_2,
                     AlertStatus.critical, AlertSize.full,
                     Priority.MID, VisualAlert.steerRequired,
                     AudibleAlert.chimeWarningRepeat, .1, 2., 2.),


class ImmediateDisableAlert(Alert):
  def __init__(self, alert_text_2, alert_text_1="핸들을 잡아주세요"):
    super().__init__(alert_text_1, alert_text_2,
                     AlertStatus.critical, AlertSize.full,
                     Priority.HIGHEST, VisualAlert.steerRequired,
                     AudibleAlert.chimeWarningRepeat, 2.2, 3., 4.),

class EngagementAlert(Alert):
  def __init__(self, audible_alert=True):
    super().__init__("", "",
                     AlertStatus.normal, AlertSize.none,
                     Priority.MID, VisualAlert.none,
                    #  audible_alert, .2, 0., 0.),
                     audible_alert, 2.2, 0., 0.),


# ********** alert callback functions **********

def below_steer_speed_alert(CP, sm, metric):
  speed = CP.minSteerSpeed * (CV.MS_TO_KPH if metric else CV.MS_TO_MPH)
  unit = "km/h" if metric else "mi/h"
  return Alert(
    "핸들을 잡아주세요",
    "%d %s 이하에서는 조향제어가 불가합니다" % (speed, unit),
    AlertStatus.userPrompt, AlertSize.mid,
    Priority.MID, VisualAlert.none, AudibleAlert.none, 0., 0.4, .3)

def calibration_incomplete_alert(CP, sm, metric):
  speed = int(Filter.MIN_SPEED * (CV.MS_TO_KPH if metric else CV.MS_TO_MPH))
  unit = "km/h" if metric else "mi/h"
  return Alert(
    "캘리브레이션 진행중: %d%%" % sm['liveCalibration'].calPerc,
    "%d %s 이상의 속도로 주행하세요" % (speed, unit),
    AlertStatus.normal, AlertSize.mid,
    Priority.LOWEST, VisualAlert.none, AudibleAlert.none, 0., 0., .2)

def no_gps_alert(CP, sm, metric):
  gps_integrated = sm['health'].hwType in [log.HealthData.HwType.uno, log.HealthData.HwType.dos]
  return Alert(
    "GPS 신호 약함",
    "환경에 문제가 없을경우 서비스팀에 연락하세요" if gps_integrated else "GPS안테나 위치를 점검하세요",
    AlertStatus.normal, AlertSize.mid,
    Priority.LOWER, VisualAlert.none, AudibleAlert.none, 0., 0., .2, creation_delay=300.)

def wrong_car_mode_alert(CP, sm, metric):
  text = "크루즈 모드 꺼짐"
  if CP.carName == "honda":
    text = "Main Switch Off"
  return NoEntryAlert(text, duration_hud_alert=0.)

EVENTS = {
  # ********** events with no alerts **********

  # ********** events only containing alerts displayed in all states **********

  EventName.debugAlert: {
    ET.PERMANENT: Alert(
      "DEBUG ALERT",
      "",
      AlertStatus.userPrompt, AlertSize.mid,
      Priority.LOW, VisualAlert.none, AudibleAlert.none, .1, .1, .1),
  },

  EventName.startup: {
    ET.PERMANENT: Alert(
      "오픈파일럿 사용준비가 되었습니다",
      "안전운전을 위해 항상 핸들을 잡고 도로교통 상황을 주시하세요",
      AlertStatus.normal, AlertSize.mid,
      Priority.LOWER, VisualAlert.none, AudibleAlert.chimeReady, 5., 0., 5.),
  },

  EventName.startupWhitePanda: {
    ET.PERMANENT: Alert(
      "경고: 화이트 판다는 더이상 사용되지 않습니다",
      "콤마2나 블랙판다로 업그레이드 하세요",
      AlertStatus.userPrompt, AlertSize.mid,
      Priority.LOWER, VisualAlert.none, AudibleAlert.none, 0., 0., 15.),
  },

  EventName.startupMaster: {
    ET.PERMANENT: Alert(
      "경고: 이 Branch는 테스트되지 않았습니다",
      "안전운전을 위해 항상 핸들을 잡고 도로교통 상황을 주시하세요",
      AlertStatus.userPrompt, AlertSize.mid,
      Priority.LOWER, VisualAlert.none, AudibleAlert.none, 0., 0., 15.),
  },

  EventName.startupNoControl: {
    ET.PERMANENT: Alert(
      "대시캠 모드",
      "안전운전을 위해 항상 핸들을 잡고 도로교통 상황을 주시하세요",
      AlertStatus.normal, AlertSize.mid,
      Priority.LOWER, VisualAlert.none, AudibleAlert.none, 0., 0., 15.),
  },

  EventName.startupNoCar: {
    ET.PERMANENT: Alert(
      "대시캠 모드: 지원되지 않는 차량",
      "안전운전을 위해 항상 핸들을 잡고 도로교통 상황을 주시하세요",
      AlertStatus.normal, AlertSize.mid,
      Priority.LOWER, VisualAlert.none, AudibleAlert.none, 0., 0., 15.),
  },

  EventName.invalidGiraffeToyota: {
    ET.PERMANENT: Alert(
      "지원되지 않는 지라프 설정",
      "comma.ai/tg 방문하세요",
      AlertStatus.normal, AlertSize.mid,
      Priority.LOWER, VisualAlert.none, AudibleAlert.none, 0., 0., .2),
  },

  EventName.whitePandaUnsupported: {
    ET.PERMANENT: Alert(
      "화이트판다는 더 이상 지원되지 않습니다",
      "콤마2나 블랙판다로 업그레이드 하세요",
      AlertStatus.normal, AlertSize.mid,
      Priority.LOWER, VisualAlert.none, AudibleAlert.none, 0., 0., .2),
    ET.NO_ENTRY: NoEntryAlert("White panda is no longer supported"),
  },

  EventName.invalidLkasSetting: {
    ET.PERMANENT: Alert(
      "차량의 LKAS 기능이 켜져 있습니다",
      "오픈파일럿 사용을 위해 LKAS를 끄세요",
      AlertStatus.normal, AlertSize.mid,
      Priority.LOWER, VisualAlert.none, AudibleAlert.none, 0., 0., .2),
  },

  EventName.communityFeatureDisallowed: {
    # LOW priority to overcome Cruise Error
    ET.PERMANENT: Alert(
      "",
      "커뮤니티 기능 감지됨",
      "개발자 설정에서 커뮤니티 기능을 활성화하세요",
      AlertStatus.normal, AlertSize.mid,
      Priority.LOW, VisualAlert.none, AudibleAlert.none, 0., 0., .2),
  },

  EventName.carUnrecognized: {
    ET.PERMANENT: Alert(
      "대시캠 모드",
      "미인식 차량",
      AlertStatus.normal, AlertSize.mid,
      Priority.LOWER, VisualAlert.none, AudibleAlert.none, 0., 0., .2),
  },

  EventName.stockAeb: {
    ET.PERMANENT: Alert(
      "브레이크!",
      "순정 AEB: 충돌 위험",
      AlertStatus.critical, AlertSize.full,
      Priority.HIGHEST, VisualAlert.fcw, AudibleAlert.none, 1., 2., 2.),
  },

  EventName.stockFcw: {
    ET.PERMANENT: Alert(
      "브레이크!",
      "순정 FCW: 충돌 위험",
      AlertStatus.critical, AlertSize.full,
      Priority.HIGHEST, VisualAlert.fcw, AudibleAlert.none, 1., 2., 2.),
  },

  EventName.fcw: {
    ET.PERMANENT: Alert(
      "브레이크!",
      "충돌 위험",
      AlertStatus.critical, AlertSize.full,
      Priority.HIGHEST, VisualAlert.fcw, AudibleAlert.chimeWarningRepeat, 1., 2., 2.),
  },

  EventName.ldw: {
    ET.PERMANENT: Alert(
      "핸들을 잡아주세요",
      "차선이탈이 감지되었습니다",
      AlertStatus.userPrompt, AlertSize.mid,
      Priority.LOW, VisualAlert.steerRequired, AudibleAlert.chimeLaneDeparture, 5., 2., 3.),
  },

  # ********** events only containing alerts that display while engaged **********

  EventName.gasPressed: {
    ET.PRE_ENABLE: Alert(
      "가속중에는 오픈파일럿 브레이크 작동불가",
      "",
      AlertStatus.normal, AlertSize.small,
      Priority.LOWEST, VisualAlert.none, AudibleAlert.none, .0, .0, .1),
  },

  EventName.vehicleModelInvalid: {
    ET.WARNING: Alert(
      "차량 매개 변수 식별 실패",
      "",
      AlertStatus.normal, AlertSize.small,
      Priority.LOWEST, VisualAlert.none, AudibleAlert.none, .0, .0, .1),
  },

  EventName.steerTempUnavailableMute: {
    ET.WARNING: Alert(
      "핸들을 잡아주세요",
      "조향제어가 일시적으로 비활성화 되었습니다",
      AlertStatus.userPrompt, AlertSize.mid,
      Priority.LOW, VisualAlert.none, AudibleAlert.none, .2, .2, .2),
  },

  EventName.preDriverDistracted: {
    ET.WARNING: Alert(
      "도로상황에 주의를 기울이세요",
      "",
      AlertStatus.normal, AlertSize.small,
      Priority.LOW, VisualAlert.none, AudibleAlert.none, .0, .1, .1, alert_rate=0.75),
  },

  EventName.promptDriverDistracted: {
    ET.WARNING: Alert(
      "도로상황에 주의하세요",
      "전방주시 필요",
      AlertStatus.userPrompt, AlertSize.mid,
      Priority.MID, VisualAlert.steerRequired, AudibleAlert.chimeRoadWarning, 4., .1, .1),
  },

  EventName.driverDistracted: {
    ET.WARNING: Alert(
      "경고: 조향제어가 즉시 해제됩니다",
      "운전자 전방주시 불안",
      AlertStatus.critical, AlertSize.full,
      Priority.HIGH, VisualAlert.steerRequired, AudibleAlert.chimeWarningRepeat, .1, .1, .1),
  },

  EventName.preDriverUnresponsive: {
    ET.WARNING: Alert(
      "핸들을 터치하세요: 모니터링 없음",
      "",
      AlertStatus.normal, AlertSize.small,
      Priority.LOW, VisualAlert.none, AudibleAlert.none, .0, .1, .1, alert_rate=0.75),
  },

  EventName.promptDriverUnresponsive: {
    ET.WARNING: Alert(
      "핸들을 터치하세요",
      "운전자 모니터링 없음",
      AlertStatus.userPrompt, AlertSize.mid,
      Priority.MID, VisualAlert.none, AudibleAlert.none, .1, .1, .1),
  },

  EventName.driverUnresponsive: {
    ET.WARNING: Alert(
      "경고: 조향제어가 즉시 해제됩니다",
      "운전자 모니터링 없음",
      AlertStatus.critical, AlertSize.full,
      Priority.HIGH, VisualAlert.none, AudibleAlert.none, .1, .1, .1),
  },

  EventName.driverMonitorLowAcc: {
    ET.WARNING: Alert(
      "운전자 얼굴 확인 중",
      "운전자 얼굴 인식이 어렵습니다",
      AlertStatus.normal, AlertSize.mid,
      Priority.LOW, VisualAlert.none, AudibleAlert.none, .4, 0., 1.),
  },

  EventName.manualRestart: {
    ET.WARNING: Alert(
      "핸들을 잡아주세요",
      "수동으로 재출발 하세요",
      AlertStatus.userPrompt, AlertSize.mid,
      Priority.LOW, VisualAlert.none, AudibleAlert.none, 0., 0., .2),
  },

  EventName.resumeRequired: {
    ET.WARNING: Alert(
      "잠시멈춤",
      "재출발을 위해 RES버튼을 누르세요",
      AlertStatus.userPrompt, AlertSize.mid,
      Priority.LOW, VisualAlert.none, AudibleAlert.none, 0., 0., .2),
  },

  EventName.belowSteerSpeed: {
    ET.WARNING: below_steer_speed_alert,
  },

  EventName.preLaneChangeLeft: {
    ET.WARNING: Alert(
      "차선 변경을 위해 핸들을 좌측으로 살짝 돌리세요",
      "다른 차량에 주의하세요",
      AlertStatus.normal, AlertSize.mid,
      Priority.LOW, VisualAlert.none, AudibleAlert.none, .0, .1, .1, alert_rate=0.75),
  },

  EventName.preLaneChangeRight: {
    ET.WARNING: Alert(
      "차선 변경을 위해 핸들을 우측으로 살짝 돌리세요",
      "다른 차량에 주의하세요",
      AlertStatus.normal, AlertSize.mid,
      Priority.LOW, VisualAlert.none, AudibleAlert.none, .0, .1, .1, alert_rate=0.75),
  },

  EventName.laneChangeBlocked: {
    ET.WARNING: Alert(
      "측면 차량 접근 중",
      "다른 차량에 주의하세요",
      AlertStatus.normal, AlertSize.mid,
      Priority.LOW, VisualAlert.steerRequired, AudibleAlert.none, .0, .1, .1),
  },  

  EventName.laneChange: {
    ET.WARNING: Alert(
      "차선 변경 중",
      "다른 차량에 주의하세요",
      AlertStatus.normal, AlertSize.mid,
      Priority.LOW, VisualAlert.none, AudibleAlert.none, .0, .1, .1),
  },
  
  EventName.laneChangeManual: {
    ET.WARNING: Alert(
      "저속 방향지시등 작동 중",
      "자동조향이 일시 비활성화 됩니다 직접 조향하세요",
      AlertStatus.userPrompt, AlertSize.mid,
      Priority.LOW, VisualAlert.none, AudibleAlert.none, .0, .1, .1, alert_rate=0.75),
  },

  EventName.emgButtonManual: {
    ET.WARNING: Alert(
      "비상등 점멸 중",
      "",
      AlertStatus.userPrompt, AlertSize.mid,
      Priority.LOW, VisualAlert.none, AudibleAlert.none, .0, .1, .1, alert_rate=0.75),
  },

  EventName.driverSteering: {
    ET.WARNING: Alert(
      "운전자 직접 조향중",
      "자동조향이 일시 비활성화 됩니다",
      AlertStatus.userPrompt, AlertSize.mid,
      Priority.LOW, VisualAlert.none, AudibleAlert.none, .0, .1, .1, alert_rate=0.75),
  },  

  EventName.steerSaturated: {
    ET.WARNING: Alert(
      "핸들을 잡아주세요",
      "차로유지 범위를 이탈하고 있습니다",
      AlertStatus.userPrompt, AlertSize.mid,
      Priority.LOW, VisualAlert.none, AudibleAlert.none, 1., 2., 3.),
  },

  EventName.modeChangeOpenpilot: {
    ET.WARNING: Alert(
      "오픈파일럿 모드",
      "",
      AlertStatus.normal, AlertSize.small,
      Priority.LOW, VisualAlert.none, AudibleAlert.chimeModeOpenpilot, 1., 0, 1.),
  },
  
  EventName.modeChangeDistcurv: {
    ET.WARNING: Alert(
      "차간+커브 제어 모드",
      "",
      AlertStatus.normal, AlertSize.small,
      Priority.LOW, VisualAlert.none, AudibleAlert.chimeModeDistcurv, 1., 0, 1.),
  },
  EventName.modeChangeDistance: {
    ET.WARNING: Alert(
      "차간ONLY 제어 모드",
      "",
      AlertStatus.normal, AlertSize.small,
      Priority.LOW, VisualAlert.none, AudibleAlert.chimeModeDistance, 1., 0, 1.),
  },
  EventName.modeChangeAutores: {
    ET.WARNING: Alert(
      "자동RES 모드",
      "사용에 주의 필요",
      AlertStatus.normal, AlertSize.small,
      Priority.LOW, VisualAlert.none, AudibleAlert.chimeModeAutores, 1., 0, 1.),
  },
  EventName.modeChangeStock: {
    ET.WARNING: Alert(
      "순정 모드",
      "",
      AlertStatus.normal, AlertSize.small,
      Priority.LOW, VisualAlert.none, AudibleAlert.chimeModeStock, 1., 0, 1.),
  },


  # ********** events that affect controls state transitions **********

  EventName.pcmEnable: {
    ET.ENABLE: EngagementAlert(AudibleAlert.chimeEngage),
  },

  EventName.buttonEnable: {
    ET.ENABLE: EngagementAlert(AudibleAlert.chimeEngage),
  },

  EventName.pcmDisable: {
    ET.USER_DISABLE: EngagementAlert(AudibleAlert.chimeDisengage),
  },

  EventName.buttonCancel: {
    ET.USER_DISABLE: EngagementAlert(AudibleAlert.chimeDisengage),
  },

  EventName.brakeHold: {
    ET.USER_DISABLE: EngagementAlert(AudibleAlert.none),
    ET.NO_ENTRY: NoEntryAlert("브레이크 홀드 중"),
  },

  EventName.parkBrake: {
    ET.USER_DISABLE: EngagementAlert(AudibleAlert.none),
    ET.NO_ENTRY: NoEntryAlert("파킹브레이크 체결 됨"),
  },

  EventName.pedalPressed: {
    ET.USER_DISABLE: EngagementAlert(AudibleAlert.none),
    ET.NO_ENTRY: NoEntryAlert("시작 중 페달 밟음",
                              visual_alert=VisualAlert.brakePressed),
  },

  EventName.wrongCarMode: {
    ET.USER_DISABLE: EngagementAlert(AudibleAlert.chimeDisengage),
    ET.NO_ENTRY: wrong_car_mode_alert,
  },

  EventName.wrongCruiseMode: {
    ET.USER_DISABLE: EngagementAlert(AudibleAlert.none),
    ET.NO_ENTRY: NoEntryAlert("어댑티브 크루즈를 활성화하세요"),
  },

  EventName.steerTempUnavailable: {
    ET.WARNING: Alert(
      "핸들을 잡아주세요",
      "조향제어가 일시적으로 비활성화 되었습니다",
      AlertStatus.userPrompt, AlertSize.mid,
      Priority.LOW, VisualAlert.none, AudibleAlert.none, .4, 2., 3.),
    ET.NO_ENTRY: NoEntryAlert("조향제어가 일시적으로 비활성화 되었습니다",
                              duration_hud_alert=0.),
  },

  EventName.posenetInvalid: {
    ET.WARNING: Alert(
      "핸들을 잡아주세요",
      "전방 영상 인식 불안",
      AlertStatus.userPrompt, AlertSize.mid,
      Priority.LOW, VisualAlert.steerRequired, AudibleAlert.chimeWarning1, .4, 2., 3.),
    ET.NO_ENTRY: NoEntryAlert("전방 영상 인식 불안"),
  },

  EventName.focusRecoverActive: {
    ET.WARNING: Alert(
      "핸들을 잡아주세요",
      "카메라 포커스 조정중: 카메라 포커스 부정확",
      AlertStatus.userPrompt, AlertSize.mid,
      Priority.LOW, VisualAlert.steerRequired, AudibleAlert.chimeWarning1, .4, 2., 3.),
  },

  EventName.outOfSpace: {
    ET.NO_ENTRY: NoEntryAlert("저장공간 부족",
                              duration_hud_alert=0.),
  },

  EventName.belowEngageSpeed: {
    ET.NO_ENTRY: NoEntryAlert("차량의 속도 낮음"),
  },

  EventName.neosUpdateRequired: {
    ET.PERMANENT: Alert(
      "NEOS 업데이트 필요",
      "업데이트를 위해 기다리세요",
      AlertStatus.normal, AlertSize.mid,
      Priority.HIGHEST, VisualAlert.none, AudibleAlert.none, 0., 0., .2),
    ET.NO_ENTRY: NoEntryAlert("NEOS 업데이트 필요"),
  },

  EventName.sensorDataInvalid: {
    ET.PERMANENT: Alert(
      "EON센서로부터 데이터를 받지 못했습니다",
      "장치를 재시작 하세요",
      AlertStatus.normal, AlertSize.mid,
      Priority.LOWER, VisualAlert.none, AudibleAlert.none, 0., 0., .2, creation_delay=1.),
    ET.NO_ENTRY: NoEntryAlert("EON센서로부터 데이터를 받지 못했습니다"),
  },

  EventName.noGps: {
    ET.PERMANENT: no_gps_alert,
  },

  EventName.soundsUnavailable: {
    ET.PERMANENT: Alert(
      "스피커를 찾을 수 없습니다",
      "장치를 재시작하세요",
      AlertStatus.normal, AlertSize.mid,
      Priority.LOWER, VisualAlert.none, AudibleAlert.none, 0., 0., .2),
    ET.NO_ENTRY: NoEntryAlert("스피커를 찾을 수 없습니다"),
  },

  EventName.tooDistracted: {
    ET.NO_ENTRY: NoEntryAlert("운전자 전방주시 매우 불안"),
  },

  EventName.overheat: {
    ET.SOFT_DISABLE: SoftDisableAlert("시스템이 과열되었습니다"),
    ET.NO_ENTRY: NoEntryAlert("시스템이 과열되었습니다"),
  },

  EventName.wrongGear: {
    ET.USER_DISABLE: EngagementAlert(AudibleAlert.chimeDisengage),  #ET.SOFT_DISABLE: SoftDisableAlert("기어가 드라이브모드가 아닙니다"),
    ET.NO_ENTRY: NoEntryAlert("기어가 드라이브모드가 아닙니다"),
  },

  EventName.calibrationInvalid: {
    ET.SOFT_DISABLE: SoftDisableAlert("캘리브레이션 유효하지 않음: 장치 위치 조정 및 재 캘리브레이션"),
    ET.NO_ENTRY: NoEntryAlert("캘리브레이션 유효하지 않음: 장치 위치 조정 및 재 캘리브레이션"),
  },

  EventName.calibrationIncomplete: {
    ET.SOFT_DISABLE: SoftDisableAlert("캘리브레이션 진행 중"),
    ET.PERMANENT: calibration_incomplete_alert,
    ET.NO_ENTRY: NoEntryAlert("캘리브레이션 진행 중"),
  },

  EventName.doorOpen: {
    ET.SOFT_DISABLE: SoftDisableAlert("도어가 열려있습니다"),
    ET.NO_ENTRY: NoEntryAlert("도어가 열려있습니다"),
  },

  EventName.seatbeltNotLatched: {
    ET.SOFT_DISABLE: SoftDisableAlert("안전벨트를 체결하세요"),
    ET.NO_ENTRY: NoEntryAlert("안전벨트를 체결하세요"),
  },

  EventName.espDisabled: {
    ET.SOFT_DISABLE: SoftDisableAlert("ESP 꺼짐"),
    ET.NO_ENTRY: NoEntryAlert("ESP 꺼짐"),
  },

  EventName.lowBattery: {
    ET.SOFT_DISABLE: SoftDisableAlert("배터리 부족"),
    ET.NO_ENTRY: NoEntryAlert("배터리 부족"),
  },

  EventName.commIssue: {
    ET.SOFT_DISABLE: SoftDisableAlert("프로세스 간 통신 오류가 있습니다"),
    ET.NO_ENTRY: NoEntryAlert("프로세스 간 통신 오류가 있습니다",
                              audible_alert=AudibleAlert.none),
  },

  EventName.radarCommIssue: {
    ET.SOFT_DISABLE: SoftDisableAlert("레이더 통신 오류가 있습니다"),
    ET.NO_ENTRY: NoEntryAlert("레이더 통신 오류가 있습니다",
                              audible_alert=AudibleAlert.none),
  },

  EventName.radarCanError: {
    ET.SOFT_DISABLE: SoftDisableAlert("레이더 오류: 차량을 재시작하세요"),
    ET.NO_ENTRY: NoEntryAlert("레이더 오류: 차량을 재시작하세요"),
  },

  EventName.radarFault: {
    ET.SOFT_DISABLE: SoftDisableAlert("레이더 오류: 차량을 재시작하세요"),
    ET.NO_ENTRY : NoEntryAlert("레이더 오류: 차량을 재시작하세요"),
  },

  EventName.modeldLagging: {
    ET.SOFT_DISABLE: SoftDisableAlert("주행 모델 지연"),
    ET.NO_ENTRY : NoEntryAlert("주행 모델 지연"),
  },

  EventName.lowMemory: {
    ET.SOFT_DISABLE: SoftDisableAlert("메모리 부족: 장치를 재시작하세요"),
    ET.PERMANENT: Alert(
      "메모리 부족 심각",
      "장치를 재시작하세요",
      AlertStatus.normal, AlertSize.mid,
      Priority.LOWER, VisualAlert.none, AudibleAlert.none, 0., 0., .2),
    ET.NO_ENTRY : NoEntryAlert("메모리 부족: 장치를 재시작하세요",
                               audible_alert=AudibleAlert.none),
  },

  EventName.controlsFailed: {
    ET.IMMEDIATE_DISABLE: ImmediateDisableAlert("차량제어 불가"),
    ET.NO_ENTRY: NoEntryAlert("차량제어 불가"),
  },

  EventName.controlsMismatch: {
    ET.IMMEDIATE_DISABLE: ImmediateDisableAlert("Controls Mismatch"),
  },

  EventName.canError: {
    ET.IMMEDIATE_DISABLE: ImmediateDisableAlert("CAN 오류: CAN 신호를 확인하세요"),
    ET.PERMANENT: Alert(
      "CAN 오류: CAN 신호를 확인하세요",
      "",
      AlertStatus.normal, AlertSize.small,
      Priority.LOW, VisualAlert.none, AudibleAlert.none, 0., 0., .2, creation_delay=1.),
    ET.NO_ENTRY: NoEntryAlert("CAN 오류: CAN 신호를 확인하세요"),
  },

  EventName.steerUnavailable: {
    ET.IMMEDIATE_DISABLE: ImmediateDisableAlert("LKAS 오류: 차량을 재시작하세요"),
    ET.PERMANENT: Alert(
      "LKAS 오류: 시작을 위해 차량을 재시작하세요",
      "",
      AlertStatus.normal, AlertSize.small,
      Priority.LOWER, VisualAlert.none, AudibleAlert.none, 0., 0., .2),
    ET.NO_ENTRY: NoEntryAlert("LKAS 오류: 차량을 재시작하세요"),
  },

  EventName.brakeUnavailable: {
    ET.IMMEDIATE_DISABLE: ImmediateDisableAlert("크루즈 오류: 차량을 재시작하세요"),
    ET.PERMANENT: Alert(
      "크루즈 오류: 시작을 위해 차량을 재시작하세요",
      "",
      AlertStatus.normal, AlertSize.small,
      Priority.LOWER, VisualAlert.none, AudibleAlert.none, 0., 0., .2),
    ET.NO_ENTRY: NoEntryAlert("크루즈 오류: 차량을 재시작하세요"),
  },

  EventName.gasUnavailable: {
    ET.IMMEDIATE_DISABLE: ImmediateDisableAlert("가속페달 오류: 차량을 재시작하세요"),
    ET.NO_ENTRY: NoEntryAlert("가속페달 오류: 차량을 재시작하세요"),
  },

  EventName.reverseGear: {
    ET.USER_DISABLE: EngagementAlert(AudibleAlert.none),
    ET.NO_ENTRY: NoEntryAlert("후진 기어"),
  },

  EventName.cruiseDisabled: {
    ET.IMMEDIATE_DISABLE: ImmediateDisableAlert("크루즈 꺼짐"),
  },

  EventName.plannerError: {
    ET.IMMEDIATE_DISABLE: ImmediateDisableAlert("Planner Solution Error"),
    ET.NO_ENTRY: NoEntryAlert("Planner Solution Error"),
  },

  EventName.relayMalfunction: {
    ET.IMMEDIATE_DISABLE: ImmediateDisableAlert("하네스 오작동"),
    ET.PERMANENT: Alert(
      "하네스 오작동",
      "장치를 점검하세요",
      AlertStatus.normal, AlertSize.mid,
      Priority.LOWER, VisualAlert.none, AudibleAlert.none, 0., 0., .2),
    ET.NO_ENTRY: NoEntryAlert("하네스 오작동"),
  },

  EventName.noTarget: {
    ET.IMMEDIATE_DISABLE: Alert(
      "오픈파일럿 시작불가",
      "선행차량이 없습니다",
      AlertStatus.normal, AlertSize.mid,
      Priority.HIGH, VisualAlert.none, AudibleAlert.none, .4, 2., 3.),
    ET.NO_ENTRY : NoEntryAlert("선행차량이 없습니다"),
  },

  EventName.speedTooLow: {
    ET.IMMEDIATE_DISABLE: Alert(
      "오픈파일럿 시작불가",
      "선행차량이 없습니다",
      AlertStatus.normal, AlertSize.mid,
      Priority.HIGH, VisualAlert.none, AudibleAlert.none, .4, 2., 3.),
  },

  EventName.speedTooHigh: {
    ET.WARNING: Alert(
      "속도가 너무 높습니다",
      "재 작동을 위해 차량의 속도를 낮추세요",
      AlertStatus.normal, AlertSize.mid,
      Priority.HIGH, VisualAlert.none, AudibleAlert.chimeWarning2Repeat, 2.2, 3., 4.),
    ET.NO_ENTRY: Alert(
      "속도가 너무 높습니다",
      "시작을 위해 차량의 속도를 낮추세요",
      AlertStatus.normal, AlertSize.mid,
      Priority.LOW, VisualAlert.none, AudibleAlert.chimeError, .4, 2., 3.),
  },

  EventName.internetConnectivityNeeded: {
    ET.PERMANENT: Alert(
      "인터넷에 연결하세요",
      "시작을 위해 업데이트를 확인해야 합니다",
      AlertStatus.normal, AlertSize.mid,
      Priority.LOWER, VisualAlert.none, AudibleAlert.none, 0., 0., .2),
    ET.NO_ENTRY: NoEntryAlert("인터넷에 연결하세요",
                              audible_alert=AudibleAlert.none),
  },

  EventName.lowSpeedLockout: {
    ET.PERMANENT: Alert(
      "크루즈 오류: 시작을 위해 차량을 재시작하세요",
      "",
      AlertStatus.normal, AlertSize.small,
      Priority.LOWER, VisualAlert.none, AudibleAlert.none, 0., 0., .2),
    ET.NO_ENTRY: NoEntryAlert("크루즈 오류: 차량을 재시작하세요"),
  },

}
