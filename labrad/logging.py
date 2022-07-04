"""
labrad.logging

Contains functions to set up logging.
"""

import os
import sys
import logging

__all__ = ["labradLogFormatter", "_LoggerWriter", "setupLogging"]


labradLogFormatter = logging.Formatter(
    "%(asctime)s [%(name)-15.15s] [%(sender_host)-15.15s] [%(sender_name)-25.25s] [%(levelname)-10.10s]  %(message)s"
)


class _LoggerWriter:
    """
    Redirects stdout to logger.
    """
    encoding = 'utf-8'

    def __init__(self, level):
        self.level = level

    def write(self, message):
        if message != '\n':
            self.level(message)

    def flush(self):
        self.level(sys.stderr)


def setupLogging(
        logger_name, sender=None, extraDict=None,
        logHandlers=[], log_level=logging.DEBUG,
        logfile=None,
        syslog=True, syslog_rfc='5424',
        syslog_socket=(os.environ['LABRADHOST'], os.environ['EGGS_LABRAD_SYSLOG_PORT'])
    ):
    """
    Sets up the logger.
    Arguments:
        logger_name     : the name of the logger to set up.
        sender          : the sender.
        extraDict       : the logging dict to send with each log.
        logHandlers     : extra handlers to send the logger.
        log_level       : the default logging level.
        logfile         : the directory to create a logfile in.
        syslog          : whether to create syslog handlers.
        syslog_rfc      : the RFC standard for syslog.
        syslog_socket   : the syslog socket to log to if syslog is True.
    """
    from socket import SOCK_STREAM, gethostname

    # ensure we can create a custom loghandler with labels specific to each sender
    if (sender is None) and (extraDict is None):
        raise Exception("Either sender or extraDict must be specified.")
    elif extraDict is None:
        extraDict = {
            'sender_host': gethostname(),
            'sender_name': sender.__class__.__name__,
        }

    # create and configure logger
    logging.basicConfig(level=log_level, handlers=None)
    logger = logging.getLogger(logger_name)
    logger.propagate = False

    # remove any existing loggers, keeping only those related to labrad
    handlers = []
    for name, logger_obj in logging.Logger.manager.loggerDict.items():
        # check log handlers have already been specified
        if isinstance(logger_obj, logging.Logger) and (name == logger_name):
            for log_handler in logger_obj.handlers:
                handlers.append(log_handler)
        # otherwise, turn off any loggers that aren't labrad related
        elif isinstance(logger_obj, logging.Logger) and ('labrad' not in name):
            logger_obj.disabled = True

    # add extra log handlers
    for log_handler in logHandlers:
        try:
            logger.addHandler(log_handler)
        except Exception as e:
            print(e)
            print("Error: unable to add log_handler {}.".format(log_handler))

    # only add core handlers if they don't already exist
    # this prevents the duplication of log messages
    if len(handlers) == 0:

        # create console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(labradLogFormatter)
        logger.addHandler(console_handler)

        # create logfile
        if logfile is not None:
            from logging.handlers import FileHandler
            logfile_handler = FileHandler(logfile)
            logfile_handler.setFormatter(labradLogFormatter)
            logger.addHandler(logfile_handler)

        if syslog:
            # create syslog handler for RFC3164
            if syslog_rfc == '3164':
                # todo: add extradict to this syslog handler
                from logging.handlers import SysLogHandler
                syslog_handler = SysLogHandler(address=syslog_socket)
                syslog_handler.setFormatter(labradLogFormatter)
                logger.addHandler(syslog_handler)

            # create syslog handler for RFC5424
            elif syslog_rfc == '5424':
                try:
                    from rfc5424logging import Rfc5424SysLogHandler
                    syslog5424_handler = Rfc5424SysLogHandler(
                        address=syslog_socket,
                        socktype=SOCK_STREAM,
                        enterprise_id=88888
                    )
                    logger.addHandler(syslog5424_handler)
                except ImportError:
                    print("Error: RFC5424 syslog handler module is not installed.")
                except Exception as e:
                    print(e)
                    print("Error: unable to create RFC5424 syslog handler.")

    # adapt logger and return
    if syslog and (syslog_rfc == '5424'):
        try:
            from rfc5424logging.adapter import Rfc5424SysLogAdapter
            logger_adapter = Rfc5424SysLogAdapter(logger, extraDict)
            return logger_adapter
        except ImportError:
            print("Error: RFC5424 syslog handler module is not installed.")
        except Exception as e:
            print("Error: unable to create RFC5424 syslog handler.")
    else:
        return logger
