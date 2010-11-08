#
# core.py
#
# Copyright (C) 2010 Sam Lai <sam@edgylogic.com>
# Copyright (C) 2009 Andrew Resch <andrewresch@gmail.com>
#
# Basic plugin template created by:
# Copyright (C) 2008 Martijn Voncken <mvoncken@gmail.com>
# Copyright (C) 2007-2009 Andrew Resch <andrewresch@gmail.com>
#
# Deluge is free software.
#
# You may redistribute it and/or modify it under the terms of the
# GNU General Public License, as published by the Free Software
# Foundation; either version 3 of the License, or (at your option)
# any later version.
#
# deluge is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with deluge.    If not, write to:
# 	The Free Software Foundation, Inc.,
# 	51 Franklin Street, Fifth Floor
# 	Boston, MA  02110-1301, USA.
#
#    In addition, as a special exception, the copyright holders give
#    permission to link the code of portions of this program with the OpenSSL
#    library.
#    You must obey the GNU General Public License in all respects for all of
#    the code used other than OpenSSL. If you modify file(s) with this
#    exception, you may extend this exception to your version of the file(s),
#    but you are not obligated to do so. If you do not wish to do so, delete
#    this exception statement from your version. If you delete this exception
#    statement from all source files in the program, then also delete it here.
#

import time

from deluge.log import LOG as log
from deluge.plugins.pluginbase import CorePluginBase
import deluge.component as component
import deluge.configmanager
from deluge.core.rpcserver import export
from deluge.event import DelugeEvent

from twisted.internet import reactor

DEFAULT_PREFS = {
    "button_state": [[0] * 7 for dummy in xrange(24)],
    "ignore_seeding": False
}

STATES = {
    0: "Green",
    2: "Red"
}

class ScheduleEvent(DelugeEvent):
    """
    Emitted when a schedule state changes.
    """
    def __init__(self, colour):
        """
        :param colour: str, the current scheduler state
        """
        self._args = [colour]

class Core(CorePluginBase):
    def enable(self):
        self.config = deluge.configmanager.ConfigManager("managedpause.conf", DEFAULT_PREFS)

        self.state = self.get_state()

        # Register to apply scheduling rules once session has started, i.e. torrents loaded.
        component.get("EventManager").register_event_handler("SessionStartedEvent", self.on_session_started)

        # Also when session is resuming...
        component.get("EventManager").register_event_handler("SessionResumedEvent", self.on_session_resumed)

    def disable(self):
        try:
            self.timer.cancel()
        except:
            pass
        component.get("EventManager").deregister_event_handler("SessionStartedEvent", self.on_session_started)
        component.get("EventManager").deregister_event_handler("TorrentAddedEvent", self.on_torrent_added)
        component.get("EventManager").deregister_event_handler("SessionResumedEvent", self.on_session_resumed)

    def update(self):
        pass

    def on_session_started(self):
        # Apply the scheduling rules
        self.do_schedule(False)

        # Schedule the next do_schedule() call for on the next hour
        now = time.localtime(time.time())
        secs_to_next_hour = ((60 - now[4]) * 60) + (60 - now[5])
        self.timer = reactor.callLater(secs_to_next_hour, self.do_schedule)
        log.debug("MANAGEDPAUSE: scheduling next check in %d seconds." % (secs_to_next_hour))

        # Apply rules to newly added torrents too
        # add event here to avoid processing the event for each torrent when session is restoring
        component.get("EventManager").register_event_handler("TorrentAddedEvent", self.on_torrent_added)

    def on_torrent_added(self, torrent_id):
        # Apply current scheduling rule to new torrent
        state = self.get_state()
        torrent = component.get("TorrentManager").torrents[torrent_id]
        
        # only apply the pause action to avoid interfering with the user option
        # 'add torrent as paused'
        if state == "Red":
            log.debug("MANAGEDPAUSE [TORRENT ADDED]: paused new torrent, %s" % torrent.get_status(["name"]).get("name", "NO NAME"))
            torrent.pause()

    def on_session_resumed(self):
        # Apply the scheduling rules
        self.do_schedule(False)

    def _set_managed_torrents_state(self, active):
        """
        Sets all auto-managed torrents to the state specfied in active, i.e. either running, or paused.
        """

        torrents = component.get("TorrentManager").torrents
        log.debug("MANAGEDPAUSE [SET STATE]: currently have %d torrents." % len(torrents))
        for t in torrents.values():
            log.debug("MANAGEDPAUSE [SET STATE]: %s, auto-managed %s, currently %s" % (t.filename, t.options["auto_managed"], t.state))
            if t.options["auto_managed"]:
                # if we're not ignoring seeding, OR we are ignoring seeding and not ...
                if not self.config["ignore_seeding"] or not (
                    # seeding
                    t.state == "Seeding" or
                    # queued and completed, so just waiting to seed
                    (t.state == "Queued" and t.get_status(["progress"]).get("progress", 0) >= 100)):
                    if active: 
                        t.resume()
                    else:
                        t.pause()

    def do_schedule(self, timer=True):
        """
        This is where we apply schedule rules.
        """

        log.debug("MANAGEDPAUSE: applying schedule rules")

        state = self.get_state()
        log.debug("MANAGEDPAUSE: the current state is %s" % state)

        # if this isn't timer triggered, run processing regardless to ensure it 
        # is applied and consistent.
        if (state != self.state) or not timer:
            if state == "Green":
                # This is Green (Normal) so we just resume all auto-managed torrents
                log.debug("MANAGEDPAUSE: resuming all auto-managed torrents")
                self._set_managed_torrents_state(True)
                # Resume the session if necessary
                component.get("Core").session.resume()
            elif state == "Red":
                # This is Red, so pause all auto-managed torrents
                log.debug("MANAGEDPAUSE: pausing all auto-managed torrents")
                self._set_managed_torrents_state(False)
                
            if state != self.state:
                # The state has changed since last update so we need to emit an event
                self.state = state
                component.get("EventManager").emit(ScheduleEvent(self.state))

        if timer:
            # Call this again in 1 hour
            self.timer = reactor.callLater(3600, self.do_schedule)

    @export()
    def set_config(self, config):
        "sets the config dictionary"
        for key in config.keys():
            self.config[key] = config[key]
        self.config.save()
        self.do_schedule(False)

    @export()
    def get_config(self):
        "returns the config dictionary"
        return self.config.config

    @export()
    def get_state(self):
        now = time.localtime(time.time())
        level = self.config["button_state"][now[3]][now[6]]
        return STATES[level]
