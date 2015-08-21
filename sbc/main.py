"""Main Server Logic"""

import logging
import logging.config
# from datetime import datetime
from time import sleep

LOG_SETTINGS = {
    'version': 1,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'level': logging.DEBUG,
            'formatter': 'detailed',
        },
    },
    'formatters': {
        'detailed': {
            'format': ('%(asctime)s %(module)-8s line:%(lineno)-4d '
                       '%(levelname)-8s %(message)s'),
        },
    },
    'loggers': {
        'sbc': {
            'level': logging.INFO,
            'handlers': ['console']
        },
    }
}
logging.config.dictConfig(LOG_SETTINGS)

LOAD_SETTINGS = {
    'deferrable': {
    },
    'sheddable': {
    },
}


from . import frequency
from . import loads

logger = logging.getLogger(name='sbc')


def get_frequency(meter):
    """this function will someday keep a few minutes
    worth of historical data
    """
    return meter.get_data()


NOMINAL = 75.0
DELTA = 6.0


# priority 10 gets shed at 59.995
def run():
    # load config file
    # TODO ^^^^^^^
    loads.SBCDIOSheddableLoad(priority=9, dio=76)
    loads.SBCDIOSheddableLoad(priority=10, dio=77)
    loads.SBCDIOSheddableLoad(priority=10, dio=78)
    loads.SBCDIOSheddableLoad(priority=10, dio=79)
    d = loads.ArduinoDeferrableWaterHeater(
        priority=10,
        setpoint=45,
        deferOffset=40,
        advanceOffset=0
    )
    # initialize

    try:
        logger.debug("Starting frequency meter")
        f_meter = frequency.ArduinoFrequencyMeter()

        previouslyShed = None
        # TODO the following should be encapsulated in the arduino
        # frequency meter class
        logger.debug("Entering short delay to allow arduino startup")
        sleep(2)
        # last_action_time = datetime.now()
        while True:
            logger.debug("Initiating F measurement")
            f = get_frequency(f_meter)
            logger.info("F measurement: {}".format(f))
            # needs to be functionalized
            if f <= (NOMINAL-1*DELTA):
                if previouslyShed is None:
                    loads.SheddableLoad.shedByPriority(10)
                    previouslyShed = 10
                    logger.info("CONTINGENCY: loads of priority=10 are shed.")
                if (f <= (NOMINAL-2*DELTA)) and (previouslyShed > 9):
                    loads.SheddableLoad.shedByPriority(9)
                    previouslyShed = 9
                    logger.info("CONTINGENCY: loads of priority>=9 are shed.")
                elif (f > (NOMINAL-2*DELTA)) and (previouslyShed <= 9):
                    loads.SheddableLoad.restoreByPriority(9)
                    previouslyShed = 10
                    logger.info("RESTORE: loads of priority<=9 are restored.")
                if (f <= (NOMINAL-3*DELTA)) and (previouslyShed > 8):
                    loads.SheddableLoad.shedByPriority(8)
                    previouslyShed = 8
                    logger.info("CONTINGENCY: loads of priority>=8 are shed.")
                elif (f > (NOMINAL-3*DELTA)) and (previouslyShed <= 8):
                    loads.SheddableLoad.restoreByPriority(8)
                    previouslyShed = 9
                    logger.info("RESTORE: loads of priority<=8 are restored.")
                if (f <= (NOMINAL-4*DELTA)) and (previouslyShed > 7):
                    loads.SheddableLoad.shedByPriority(7)
                    previouslyShed = 7
                    logger.info("CONTINGENCY: loads of priority>=7 are shed.")
                elif (f > (NOMINAL-4*DELTA)) and (previouslyShed <= 7):
                    loads.SheddableLoad.restoreByPriority(7)
                    previouslyShed = 8
                    logger.info("RESTORE: loads of priority <=7 are restored.")
            else:
                if previouslyShed:
                    loads.SheddableLoad.restoreByPriority(10)
                    logger.info(
                        "RESTORE: loads of priority=10 restored" +
                        " contingency over."
                    )
                    previouslyShed = None

            sleep(2)
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt recieved... exiting.")

if __name__ == "__main__":
    run()
