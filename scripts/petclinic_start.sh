#!/usr/bin/env bash

set -e -x

APP="petclinic"

# Getting the environment name via meta data and ASG tag.
ENV=$(aws ec2 describe-tags --filters "Name=resource-id,Values=$(curl -s https://169.254.169.254/latest/meta-data/instance-id)" --region `curl --silent https://169.254.169.254/latest/dynamic/instance-identity/document | jq -r .region` --query "Tags[?Key=='aws:autoscaling:groupName'].Value" --output text | cut -f2 -d"-")

# Running app with appropriate profiling group name.
/usr/bin/java -javaagent:/usr/share/petclinic/codeguru-profiler-java-agent-standalone-0.3.2.jar="profilingGroupName:${APP}-${ENV}" -jar /usr/share/petclinic/petclinic.jar