#!/bin/sh

export LABRADHOST=localhost
export LABRADPASSWORD=testpass
export LABRADPORT=7777

TEST_SCRIPT=$(dirname $0)/test.py
ROOT_DIR=$(dirname $0)/../..
SOURCE_DIR=$ROOT_DIR/labrad

# start labrad manager
labrad --password ${LABRADPASSWORD} --port ${LABRADPORT} 1>.labrad.log 2>.labrad.err.log &
sleep 20

# start python test server
python $ROOT_DIR/labrad/servers/test_server.py 1>.test_server.log 2>.test_server.err.log &
sleep 20

# run tests to get code coverage
coverage run --source=$SOURCE_DIR $TEST_SCRIPT -v --pyargs labrad

# run tests again for real, since coverage swallows error codes
python $TEST_SCRIPT -v --pyargs labrad
