#!/usr/bin/env bash

apt purge openjdk-11* -y
apt-get install openjdk-17-jre -y
apt-get install /opt/application/petclinic.deb -y
