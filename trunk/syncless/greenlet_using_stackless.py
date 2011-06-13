#! /usr/local/bin/stackless2.6

"""A greenlet emulator using Stackless Python.

Please use syncless.best_greenlet instead of this module
(syncless.greenlet_using_stackless) for convenience, since best_greenlet can
use the existing greenlet module, it also creates the top-level greenlet
module to be imported by other modules, and it also provides the
gevent_hub_main() convenience function.

Please note that this emulator has been tested only with native Syncless. It
most probably doesn't work with enumated Stackless (e.g. stacklesss.py in
Eventlet, greenstackless.py in Syncless and PyPy's Stackless emulation).
This emulator doesn't do any checks if it's using native Stackless.

To use this module, replace the first occurrence of your imports:

  # Old module import: import greenlet
  from syncless import greenlet_using_stackless as greenlet
  
  # Old class import: from greenlet import greenlet
  from syncless.greenlet_using_stackless import greenlet

A minimalistic fake stackless module which lets the greenlet_using_stackless
module be imported without exceptions (but it wouldn't work):

  class FakeTasklet(object):
    def __init__(self, function):
      pass
    def __call__(self, *args, **kwargs):
      return self
    def remove(self):
      pass
  stackless = sys.modules['stackless'] = type(sys)('stackless')
  stackless.tasklet = FakeTasklet
  stackless.current = FakeTasklet(None)
"""

import stackless
import sys

current = None

def getcurrent():
  return current

class GreenletExit(BaseException):  # Just like in real greenlet.
  pass

def _ignore(*args, **kwargs):
  pass

def _cleanup_at_process_exit(greenlet_obj):
  core = __import__('sys').modules.get('gevent.core')
  if core and core.sys:
    # Make the hub greenlet exit from our Dispatch() (see below).
    core.goon = False
    if core.traceback.print_exc is not _ignore:
      core.traceback = type(core.traceback)('fake_traceback')
      core.traceback.print_exc = _ignore
      core.traceback.print_exception = _ignore
    # Disable sys.stderr.write in greenlet.core.__event_handler.
    core.sys = None
  if getattr(greenlet_obj, '_report_error', None):
    greenlet_obj._report_error = lambda *args, **kwargs: None

def _finish_helper():
  """Helper tasklet for inserting a tasklet after stackless.current.

  See the code of the users of _finish_helper_tasklet for more information.    
  """
  while True:
    stackless.current.next.next.remove().run()

_finish_helper_tasklet = stackless.tasklet(_finish_helper)().remove()

def _insert_after_current_tasklet(tasklet_obj):
  """Like tasklet_obj.insert(), but forcibly insert _after_ current."""
  if stackless.current.next is stackless.current:
    tasklet_obj.insert()
  elif stackless.current.next is not tasklet_obj:
    # Use a trick to insert tasklet_obj right after us (as
    # stackless.current.next), so it gets scheduled as soon as this
    # _wrapper returns.
    #DEBUG assert not _finish_helper_tasklet.scheduled
    tasklet_obj.remove()
    _finish_helper_tasklet.insert()
    tasklet_obj.insert()
    _finish_helper_tasklet.run()
    #DEBUG assert stackless.current.next is _finish_helper_tasklet
    #DEBUG assert stackless.current.next.next is tasklet_obj
    _finish_helper_tasklet.remove()
  #DEBUG assert stackless.current.next is tasklet_obj

def _wrapper(greenlet_obj, run, args, kwargs):
  """Wrapper to run `run' as the callable of a greenlet--tasklet."""
  global current
  try:
    current._tasklet.remove()
    current = greenlet_obj
    #prevt = None  # Save memory.
    run(*args, **kwargs)
    target = greenlet_obj.parent
    while target.dead:
      target = target.parent
    if target._tasklet is None:
      target._first_switch(*args, **kwargs)
    target._tasklet.tempval = None
  except GreenletExit:
    target = greenlet_obj.parent
    while target.dead:
      target = target.parent
    if target._tasklet is None:
      target._first_switch(*args, **kwargs)
    target._tasklet.tempval = None
  except TaskletExit:
    # This doesn't happen with gevent in a worker greenlet, because the
    # exception handler in the hub (gevent.core.__event_handler) stops the
    # TaskletExit from propagating.
    target = greenlet_obj.parent
    while target.dead:
      target = target.parent
    if target._tasklet is None:
      target._first_switch(*args, **kwargs)
    target._tasklet.tempval = None
  except:
    bomb_obj = stackless.bomb(*sys.exc_info())
    target = greenlet_obj.parent
    while True:  # This logic is tested in GreenletTest.testThrow.
      if not target.dead:
        if target._tasklet:
          break
        target.dead = True
        target.__dict__.pop('run', None)  # Keep methods of subclasses.
      target = target.parent
    target._tasklet.tempval = bomb_obj
    del bomb_obj  # Save memory.
  assert target._tasklet
  greenlet_obj.dead = True
  # We don't clear greenlet_obj._tasklet, because it might call
  # `current._tasklet.remove()' on us.
  #greenlet_obj._tasklet = False
  # As a final action, we'd like to have
  # greenlet_obj.parent.switch(value). However, we don't call that method
  # directly, because we want to return from this _wrapper, and thus free
  # stackless.current early. So we just arrange arrange that
  # greenlet_obj.parent._tasklet will be the next tasklet in turn.
  _insert_after_current_tasklet(target._tasklet)

class greenlet(object):
  def __init__(self, run=None, parent=None):
    self._tasklet = None
    self.dead = False
    # TODO(pts): Support greenlet.gr_frame.
    # TODO(pts): Detect cycle of parents when setting the parent attribute.
    if parent is None:
      parent = getcurrent()
    self.parent = parent
    if run is not None:
      self.run = run

  def _first_switch(self, *args, **kwargs):
    global current
    run = self.run
    self.__dict__.pop('run', None)  # Keep methods of subclasses.
    # Create the tasklet that late.
    self._tasklet = stackless.tasklet(_wrapper)(
        self, run, args, kwargs).remove()
    run = args = kwargs = None  # Save memory.
    if (type(self) != greenlet and
        repr(type(self)) == "<class 'gevent.hub.Hub'>"):
      # TODO(pts): Revisit our strategy here.
      # We have to do a little monkey-patching here to make the program
      # exit when the main tasklet exits. Without this monkey-patching,
      # upon stackless.main exit, Stackless raises TaskletExit in the hub
      # tasklet, which an exception handler prints and ignores, and the
      # main loop in core.dispatch() continues running forever. With this
      # monkey-patching (and with `except TaskletExit:' later) we create
      # an abortable main loop, and abort it when stackless.main exits.
      self.is_gevent_hub = True
      core = __import__('gevent.core').core
      if not hasattr(core, 'goon'):
        core.goon = True
        def Dispatch():
          result = 0
          while core.goon and not result:
            result = core.loop()
          return result
        core.dispatch = Dispatch

  def run(self):
    """Can be overridden in subclasses to do useful work in the greenlet."""

  def switch(self, *args, **kwargs):
    global current
    target = self
    while target.dead:
      target = target.parent
    if target._tasklet is None:
      target._first_switch(*args, **kwargs)
    else:
      assert not kwargs
      if args:
        assert len(args) <= 1
        if target is current:
          return args[0]
        target._tasklet.tempval = args[0]
      else:
        if target is current:
          return ()
        target._tasklet.tempval = ()
    del args    # Save memory.
    del kwargs  # Save memory.
    caller = current
    caller._tasklet = stackless.current  # Needed for the Syncless main loop.
    try:
      return target._tasklet.run()
    except TaskletExit:
      # See the comments for this TaskletExit logic in the throw method.
      if not stackless.main.alive:
        _cleanup_at_process_exit(caller)
      raise  # So the rest of the tasklet code won't get executed.
    finally:
      current._tasklet.remove()  # SUXX: Segfault even without this.
      current = caller

  def __len__(self):
    """Implements bool(self).

    Returns:
      A true value (1) iff self has been started but not finished yet.
    """
    return int(not (not self._tasklet or self.dead))

  def throw(self, typ=None, val=None, tb=None):
    global current
    if not typ:
      typ = GreenletExit
    target = self
    while True:  # This logic is tested in GreenletTest.testThrow.
      if not target.dead:
        if target._tasklet:
          break
        target.dead = True
        target.__dict__.pop('run', None)  # Keep methods of subclasses.
      target = target.parent
    if target._tasklet.is_main:
      if typ is GreenletExit and not val:
        # Exit finally.
        typ = TaskletExit
    if target is current:
      raise typ, val, tb
    # Don't call target.switch, it might be overridden in a subclass.
    caller = current
    caller._tasklet = stackless.current
    target._tasklet.tempval = stackless.bomb(typ, val, tb)
    try:
      return target._tasklet.run()
    except TaskletExit:
      # TaskletExit should not happen here, except when the whole Stackless
      # process exits, and Stackless sends all tasklets a TaskletExit.
      # stackless.main.alive is False in this case, and instance attributes
      # (i.e. non-class-attributes) of caller are gone (!).
      if not stackless.main.alive:
        _cleanup_at_process_exit(caller)
      raise  # So the rest of the tasklet code won't get executed.
    finally:
      current._tasklet.remove()
      current = caller

  getcurrent = staticmethod(globals()['getcurrent'])
  GreenletExit = staticmethod(globals()['GreenletExit'])
  is_pts_greenlet_emulated = True

is_pts_greenlet_emulated = True
# Sets current.parent = None, because current was None.
current = greenlet()
current._tasklet = stackless.current
