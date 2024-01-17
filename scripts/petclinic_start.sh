#!/usr/bin/env bash

set -e -x

APP="petclinic"

# Getting the environment name via meta data and ASG tag.
# shellcheck disable=SC2046
#ENV=$(aws ec2 describe-tags --filters "Name=resource-id,Values=$(curl -s https://169.254.169.254/latest/meta-data/instance-id)" --region $(curl -s https://169.254.169.254/latest/dynamic/instance-identity/document | jq -r .region) --query "Tags[?Key=='aws:autoscaling:groupName'].Value" --output text | cut -f2 -d"-")

# Running app with appropriate profiling group name.
/usr/bin/java  -jar /usr/share/petclinic/petclinic.jar
