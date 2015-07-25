#!/bin/sh

export LABRADHOST=localhost
export LABRADPASSWORD=testpass
export LABRADPORT=7777

# start labrad manager
labrad 1>.labrad.log 2>.labrad.err.log &
sleep 20

# start python test server
python labrad/servers/test_server.py 1>.test_server.log 2>.test_server.err.log &
sleep 20

# run the tests
python $(dirname $0)/test.py -v . && coverage run --source=labrad $(dirname $0)/test.py -v .
STATUS=$?

echo "=== .labrad.log ===" && cat .labrad.log && echo
echo "=== .test_server.log ===" && cat .test_server.log && echo

exit $STATUS
