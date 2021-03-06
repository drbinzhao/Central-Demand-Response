import atexit
from serial import Serial
from xbee import XBee
from time import sleep
from ts7250v2 import dio


class LoadBase(object):
    ''' Virtual parent class for loads '''
    def __init__(self):
        pass


# priority (0 highest ------- lowest 10)
class SheddableLoad(LoadBase):
    '''Virtual base class for sheddable loads'''
    LoadList = []

    def __init__(self, priority):
        self.priority = priority
        self.shed = False
        SheddableLoad.LoadList.append(self)
        super(SheddableLoad, self).__init__()

    def isShed(self):
        return self.shed

    def shedLoad(self):
        raise NotImplementedError

    def restoreLoad(self):
        raise NotImplementedError

    @classmethod
    def shedByPriority(cls, priority):
        for load in cls.LoadList:
            if load.priority >= priority:
                load.shedLoad()

    @classmethod
    def restoreByPriority(cls, priority):
        for load in cls.LoadList:
            if load.priority <= priority:
                load.restoreLoad()


class DummySheddableLoad(SheddableLoad):
    '''Stub class for sheddable loads'''
    def __init__(self, priority):
        super(DummySheddableLoad, self).__init__(priority)

    def shedLoad(self):
        if not self.isShed():
            self.shed = True
            return True

        return False

    def restoreLoad(self):
        if self.isShed():
            self.shed = False
            return True

        return False


class SBCDIOSheddableLoad(SheddableLoad):
    def __init__(self, priority, dio_pin, evgpio='/usr/local/bin/evgpioctl'):
        if dio_pin not in dio.DIO_MAP.keys():
            raise TypeError("dio_pin not a key in dio.DIO_MAP.")

        self.dio_pin = dio_pin
        self.evgpio = dio.DIO()
        self.evgpio.DIO_set_output(self.dio_pin)
        self.evgpio.DIO_set_high(self.dio_pin)
        super(SBCDIOSheddableLoad, self).__init__(priority)
        # the following is a hack to ensure that the gpio is set back to
        # default when the program exits

        atexit.register(self._cleanup)

    def _cleanup(self):
        self.evgpio.DIO_set_low(self.dio_pin)
        self.evgpio.DIO_set_input(self.dio_pin)

    def _evgpioOff(self):
        self.evgpio.DIO_set_low(self.dio_pin)

    def _evgpioOn(self):
        self.evgpio.DIO_set_high(self.dio_pin)

    def shedLoad(self):
        if not self.isShed():
            # run SBC specific command
            self._evgpioOff()
            self.shed = True
            return True

        return False

    def restoreLoad(self):
        if self.isShed():
            # run SBC specific command
            self._evgpioOn()
            self.shed = False
            return True

        return False


class DeferrableLoad(LoadBase):
    LoadList = []

    def __init__(self, priority, advanceable=False):
        self.priority = priority
        self.deferred = False
        self.advanced = False
        self.advanceable = advanceable
        DeferrableLoad.LoadList.append(self)
        super(DeferrableLoad, self).__init__()

    def isDeferred(self):
        return self.deferred

    def isAdvanced(self):
        return self.advanced

    def defer(self):
        raise NotImplementedError

    @classmethod
    def deferByPriority(cls, priority):
        for load in cls.LoadList:
            if load.priority >= priority:
                load.defer()

    @classmethod
    def restoreByPriority(cls, priority):
        for load in cls.LoadList:
            if load.priority <= priority:
                load.restore()

    def restore(self):
        raise NotImplementedError

    def advance(self):
        raise NotImplementedError


# TODO: try accept blocks for timeouts
class ArduinoDeferrableWaterHeater(DeferrableLoad):
    # this is written with only one device connected in mind
    # we send messages to the PAN broadcast address instead of
    # to individual water heaters at specific addresses
    # should be changed later
    # TODO ^^^^^^^^^^
    def __init__(self, priority, setpoint, deferOffset, advanceOffset,
                 serial='/dev/ttyUSB0', baud=9600):
        self.serial = Serial(serial, baud)
        self.xbee = XBee(self.serial)
        self.setpoint = None
        self.nominalsetpoint = setpoint
        self.deferOffset = deferOffset
        self.advanceOffset = advanceOffset
        self.enabled = False
        super(ArduinoDeferrableWaterHeater, self).__init__(
            priority=priority,
            advanceable=True
        )
        sleep(2)
        self._setTemperature(self.nominalsetpoint)

    def _setTemperature(self, temperature):
        self.xbee.tx(dest_addr=b'\xFF\xFF',
                     data='SetPoint: {}!'.format(temperature))
        # we should get something back, no dropped packets
        d = self.xbee.wait_read_frame()
        if self._checkPacket(
                d,
                'Set Point Recieved {:.2f}'.format(temperature)):
            self.setpoint = temperature
            return True
        else:
            return False

    def _checkPacket(self, packet, phrase):
        if packet['rf_data'].strip() == phrase:
            return True
        else:
            return False

    def enable(self):
        # do a check if setpoint is none and throw an exception
        self.xbee.tx(dest_addr=b'\xFF\xFF', data='ON!')
        d = self.xbee.wait_read_frame()
        # if it times out we need to check the status if it's enabled
        if self._checkPacket(d, 'Water Heater Enabled'):
            self.enabled = True

    def defer(self):
        if self.isAdvanced():
            # return to nominal to defer
            x = self._setTemperature(self.nominalsetpoint)
            self.advanced = not x
        elif not self.isDeferred():
            # defer
            x = self._setTemperature(self.nominalsetpoint - self.deferOffset)
            self.deferred = x

    def advance(self):
        if self.isDeferred():
            # return to nominal to advance
            x = self._setTemperature(self.nominalsetpoint)
            self.deferred = not x
        if not self.isAdvanced():
            # advance
            x = self._setTemperature(self.nominalsetpoint + self.deferOffset)
            self.advanced = x

    def restore(self):
        if self.isDeferred():
            x = self._setTemperature(self.nominalsetpoint)
            self.deferred = not x
        elif self.isAdvanced():
            x = self._setTemperature(self.nominalsetpoint)
            self.advnaced = not x

    def disable(self):
        self.xbee.tx(dest_addr=b'\xFF\xFF', data='OFF!')
        d = self.xbee.wait_read_frame()
        # if it times out we need to check the status if it's enabled
        if self._checkPacket(d, 'Water Heater Disabled'):
            self.enabled = False
