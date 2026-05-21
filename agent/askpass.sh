#!/usr/bin/env bash
# SUDO_ASKPASS helper — prompts on the controlling terminal,
# prints password to stdout for sudo to consume.
# The password is never written to disk or logged.
printf '%s' "${1:-[sudo] password: }" > /dev/tty
IFS= read -r -s password < /dev/tty
printf '\n' > /dev/tty
printf '%s\n' "$password"
