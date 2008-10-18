#!/bin/sh

### BEGIN INIT INFO
# Provides: labradnode
# Required-Start: $network
# Required-Stop: $network
# Default-Start: 3 4 5
# Default-Stop: 0 1 2 6
# Short-Description: Allows you to start and stop servers in a LabRAD network.
# Description: Allows you to start and stop servers in a LabRAD network.
### END INIT INFO

case "$1" in
    'start')
        echo "Starting labradnode..."
        mkdir /var/run/labrad
        mkdir /var/log/labrad
        twistd --pidfile /var/run/labrad/node.pid --logfile /var/log/labrad/node.log labradnode
        ;;
        
    'stop')
        echo "Stopping labradnode..."
        kill `cat /var/run/labrad/node.pid`
        ;;
        
    'restart')
        $0 stop
        $0 start
        ;;
        
    *)
        echo "Usage: $0 { start | stop }"
        ;;
esac

# TODO: add status, try-restart, reload, force-reload

exit 0