#!/bin/sh

### BEGIN INIT INFO
# Provides: labradcontrol
# Required-Start: $network
# Required-Stop: $network
# Default-Start: 3 4 5
# Default-Stop: 0 1 2 6
# Short-Description: Allows to start and stop servers in a LabRAD network.
# Description: Allows to start and stop servers in a LabRAD network.
### END INIT INFO

## Environment Variables
#export PYTHONPATH=
#export LABRADHOST=localhost
#export LABRADPORT=7682
#export LABRADNODE=
#export LABRADPASSWORD=
USER=root

LOGDIR=/var/log/labrad
RUNDIR=/var/run/labrad
LOGFILE=node.log
PIDFILE=node.pid
CMD=labradnode
UID=`id -u $USER`
GID=`id -g $USER`

d_start()
{
    if [ ! -d $LOGDIR ]; then
        mkdir $LOGDIR
    fi
    if [ ! -d $RUNDIR ]; then
        mkdir $RUNDIR
    fi
    twistd --pidfile $RUNDIR/$PIDFILE \
           --logfile $LOGDIR/$LOGFILE \
           --uid $UID --gid $GID $CMD
}

d_stop()
{
    if [ -f $RUNDIR/$PIDFILE ]; then
        kill `cat $RUNDIR/$PIDFILE`
    fi
}

case "$1" in
    start)
        echo -n "Starting $CMD..."
        d_start
        echo "done."
        ;;
        
    stop)
        echo -n "Stopping $CMD..."
        d_stop
        echo "done."
        ;;
        
    restart|force-reload)
        echo -n "Restarting $CMD..."
        d_stop
        sleep 1
        d_start
        echo "done."
        ;;
        
    *)
        echo "Usage: $CMD { start | stop | restart | force-reload }"
        exit 3
        ;;
esac

# TODO: add status, try-restart, reload

exit 0