#! /usr/local/bin/stackless2.6

"""A demo for enforcing a timeout on multiple read operations.

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.
"""

import stackless
import sys

from syncless import coio
from syncless import patch


def Asker(timeout, age_answer_channel):
  print 'You have %s seconds altogether to tell me your age.' % timeout
  while True:
    sys.stdout.write('How old are you? ')
    sys.stdout.flush()
    answer = sys.stdin.readline()
    assert answer
    answer = answer.strip()
    try:
      age = int(answer)
    except ValueError:
      print 'Please enter an integer.'
      continue
    if age < 3:
      print 'That would be too young. Please enter a valid age'
      continue
    age_answer_channel.send(age)
    return


def TimeoutReceive(timeout, receive_channel, default_value=None):
  """Receive from receive_channel with a timeout."""
  # TODO(pts): Speed: refactor w/o propagation_channel and rewrite in Pyrex if
  # needed.
  assert timeout > 0
  propagation_channel = stackless.channel()
  propagation_channel.preference = 1  # Prefer the sender.
  def Propagator():
    received_value = receive_channel.receive()
    if sleeper_tasklet.alive:
      sleeper_tasklet.tempval = False
      sleeper_tasklet.insert()
    propagation_channel.send(received_value)
  def Sleeper():
    if coio.sleep(timeout):  # If timeout has been reached:
      propagation_channel.send(default_value)
      if propagator_tasklet.alive:
        # This is the only way to reliably kill a tasklet blocked on a channel.
        propagator_tasklet.kill()
  propagator_tasklet = stackless.tasklet(Propagator)()
  sleeper_tasklet = stackless.tasklet(Sleeper)()
  return propagation_channel.receive()


if __name__ == '__main__':
  patch.patch_stdin_and_stdout()  # sets sys.stdin = sys.stdout = ...
  patch.patch_stderr()  # For fair exeption reporting.
  age_answer_channel = stackless.channel()
  age_answer_channel.preference = 1  # Prefer the sender.
  timeout = 3
  asker_tasklet = stackless.tasklet(Asker)(timeout, age_answer_channel)
  age = TimeoutReceive(timeout, age_answer_channel)
  if age is None:  # Timed out.
    if asker_tasklet.alive:
      asker_tasklet.tempval = stackless.bomb(TaskletExit)
      asker_tasklet.run()
    print 'You were too slow entering your age.'
  else:
    print 'Got age: %r.' % age
