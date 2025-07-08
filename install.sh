#!/bin/sh

# set permissions
chmod -R 777 /data/VenusOS-DbusLogger/

# create a symlink to the service directory to make it start automatically by the daemon manager
ln -s /data/VenusOS-DbusLogger/service /service/VenusOS-DbusLogger
ln -s /data/VenusOS-DbusLogger/service /opt/victronenergy/service/VenusOS-DbusLogger

echo "Service symlink created"

# start service
svc -t /service/VenusOS-DbusLogger
echo "Service started"