#!/usr/bin/env bash
echo "-------"
pwd
echo "-------"
ls
echo "-------"
set -e -x
apt-get install --fix-broken /tmp/petclinic.deb -y

wget -q -O /usr/share/app/codeguru-profiler-java-agent-standalone-0.3.2.jar https://d1osg35nybn3tt.cloudfront.net/com/amazonaws/codeguru-profiler-java-agent-standalone/0.3.2/codeguru-profiler-java-agent-standalone-0.3.2.jar
systemctl restart petclinic
